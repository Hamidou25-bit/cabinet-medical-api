"""Utilitaires stock partagés entre stock.py et achats.py (Phase 2.5-B).

Isolés dans ce module pour éviter qu'un module de routes en importe un autre.
"""
import math

from fastapi import HTTPException

# Doit rester aligné avec la contrainte stock_categorie_check
# (migration 2026_07_12_consommables_scindes_mouvements.sql — 'consommable' scindé
# en 'consommable_laboratoire'/'consommable_medical' ; l'ancienne valeur reste
# acceptée par la contrainte en base à titre transitoire mais n'est plus valide ici)
CATEGORIES_CONSOMMABLES = ("consommable_laboratoire", "consommable_medical")
CATEGORIES_VALIDES = ("medicament",) + CATEGORIES_CONSOMMABLES + ("equipement",)

# Doit rester aligné avec la contrainte CHECK de stock.statut_equipement
# (migration 2026_07_12_stock_statut_equipement.sql). Pertinent uniquement
# pour categorie='equipement' — NULL pour toutes les autres catégories.
STATUTS_EQUIPEMENT = ("bon_etat", "en_utilisation", "a_remplacer")


def valider_statut_equipement(statut):
    """Valide un statut d'équipement non nul (la contrainte CHECK renverrait un
    500 illisible). Le contrôle categorie='equipement' est fait par l'appelant."""
    if statut not in STATUTS_EQUIPEMENT:
        raise HTTPException(
            status_code=400,
            detail=f"statut_equipement invalide : {statut} (valeurs possibles : {', '.join(STATUTS_EQUIPEMENT)})",
        )
    return statut


def valider_categorie_et_unites(article):
    """Valide categorie et unites_par_boite avant écriture (sinon la contrainte
    CHECK renverrait un 500 illisible). Retourne unites_par_boite normalisé."""
    categorie = article.get("categorie", "medicament")
    if categorie not in CATEGORIES_VALIDES:
        raise HTTPException(
            status_code=400,
            detail=f"categorie invalide : {categorie} (valeurs possibles : {', '.join(CATEGORIES_VALIDES)})",
        )
    unites = article.get("unites_par_boite", 1)
    if unites is None or unites == "":
        unites = 1
    try:
        unites = int(unites)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="unites_par_boite doit être un entier")
    if unites < 1:
        raise HTTPException(status_code=400, detail="unites_par_boite doit être >= 1")
    return unites


def arrondir_prix_fcfa(valeur):
    """Arrondit un prix au multiple de 5 FCFA le plus proche.

    Les demi-cas (x2,5 / x7,5) arrondissent vers le haut — round() natif ferait
    un arrondi bancaire (round(2.5) == 2) imprévisible pour des prix.
    """
    return int(math.floor(float(valeur) / 5 + 0.5)) * 5


def valider_marge_pourcentage(valeur, champ="marge_pourcentage"):
    """Valide une marge en pourcentage (0 à 500 inclus). Retourne un float."""
    try:
        valeur = float(valeur)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{champ} doit être un nombre")
    if not 0 <= valeur <= 500:
        raise HTTPException(status_code=400, detail=f"{champ} doit être compris entre 0 et 500")
    return valeur


def consommer_stock(cursor, stock_id, quantite, type_sortie, utilisateur_id,
                    patient_id=None, examen_id=None, motif=None):
    """Sortie de consommable tracée dans mouvements_consommable (cœur partagé entre
    POST /stock/{id}/consommer et la consommation automatique à la création d'un
    examen). Verrouille la ligne (FOR UPDATE), contrôle catégorie et stock suffisant,
    décrémente et insère le mouvement. Ne commit PAS — à la charge de l'appelant.
    Retourne (article, mouvement, nouvelle_quantite). Lève HTTPException (404/400)
    en cas d'article inconnu, catégorie non consommable ou stock insuffisant."""
    cursor.execute(
        'SELECT "Designation", "Quantite", categorie FROM stock WHERE "idStock" = %s FOR UPDATE',
        (stock_id,),
    )
    article = cursor.fetchone()
    if not article:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    if article["categorie"] not in CATEGORIES_CONSOMMABLES:
        raise HTTPException(
            status_code=400,
            detail=f"Cette opération est réservée aux consommables (laboratoire/médical) — "
                   f"'{article['Designation']}' est en catégorie '{article['categorie']}'",
        )
    if article["Quantite"] < quantite:
        raise HTTPException(
            status_code=400,
            detail=f"Stock insuffisant pour '{article['Designation']}' : "
                   f"{article['Quantite']} unité(s) disponible(s), {quantite} demandée(s)",
        )

    cursor.execute(
        'UPDATE stock SET "Quantite" = "Quantite" - %s WHERE "idStock" = %s RETURNING "Quantite"',
        (quantite, stock_id),
    )
    nouvelle_quantite = cursor.fetchone()["Quantite"]

    cursor.execute("""
        INSERT INTO mouvements_consommable (stock_id, designation, quantite, type_sortie,
                                            utilisateur_id, patient_id, examen_id, motif)
        VALUES (%(stock_id)s, %(designation)s, %(quantite)s, %(type_sortie)s,
                %(utilisateur_id)s, %(patient_id)s, %(examen_id)s, %(motif)s)
        RETURNING id, stock_id, designation, quantite, type_sortie,
                  utilisateur_id, patient_id, examen_id, motif, date_mouvement
    """, {
        "stock_id": stock_id,
        "designation": article["Designation"],
        "quantite": quantite,
        "type_sortie": type_sortie,
        "utilisateur_id": utilisateur_id,
        "patient_id": patient_id,
        "examen_id": examen_id,
        "motif": motif,
    })
    mouvement = cursor.fetchone()
    return article, mouvement, nouvelle_quantite


def convertir_en_unites(cursor, stock_id, quantite_unites, nombre_boites, unites_par_boite=None):
    """Convertit une saisie en unités canoniques de stock.

    - quantite_unites fourni : retourné tel quel (après validation entier >= 1).
    - nombre_boites fourni : multiplié par le unites_par_boite de l'article
      (lu en base via stock_id — 404 si l'article n'existe pas/plus), ou par le
      paramètre unites_par_boite si stock_id est None (ligne d'achat créant un
      nouvel article, dont la fiche stock n'existe pas encore).
    - Exactement un des deux (quantite_unites / nombre_boites) doit être fourni,
      sinon 400.
    """
    if (quantite_unites is None) == (nombre_boites is None):
        raise HTTPException(
            status_code=400,
            detail="Fournir soit quantite_unites, soit nombre_boites (exactement un des deux)",
        )

    champ = "quantite_unites" if quantite_unites is not None else "nombre_boites"
    valeur = quantite_unites if quantite_unites is not None else nombre_boites
    try:
        valeur = int(valeur)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{champ} doit être un entier")
    if valeur < 1:
        raise HTTPException(status_code=400, detail=f"{champ} doit être >= 1")

    if quantite_unites is not None:
        return valeur

    if stock_id is not None:
        cursor.execute('SELECT unites_par_boite FROM stock WHERE "idStock" = %s', (stock_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Article de stock {stock_id} non trouvé")
        par_boite = row["unites_par_boite"]
    else:
        par_boite = valider_categorie_et_unites({"unites_par_boite": unites_par_boite})

    return valeur * par_boite
