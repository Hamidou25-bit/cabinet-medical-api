"""Utilitaires stock partagés entre stock.py et achats.py (Phase 2.5-B).

Isolés dans ce module pour éviter qu'un module de routes en importe un autre.
"""
from fastapi import HTTPException

# Doit rester aligné avec la contrainte stock_categorie_check
# (migration 2026_07_10_stock_categorie_3_valeurs_unites_par_boite.sql)
CATEGORIES_VALIDES = ("medicament", "consommable", "equipement")


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
