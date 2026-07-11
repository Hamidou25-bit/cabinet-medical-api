from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from auth import require_role, get_current_user
from validation import require_fields, require_positive
from audit_log import log_audit
from stock_utils import (
    valider_categorie_et_unites,
    convertir_en_unites,
    arrondir_prix_fcfa,
    valider_marge_pourcentage,
)

router = APIRouter(prefix="/stock", tags=["Stock"])

@router.get("/")
def get_stock(categorie: str = None, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    where_clause = ""
    params = {}
    if categorie:
        where_clause = 'WHERE categorie = %(categorie)s'
        params["categorie"] = categorie
    cursor.execute(f"""
        SELECT "idStock", "DateEntree", "Type", "Designation", "Fournisseur",
               "Quantite", "SeuilAlerte", "PrixVente", "PrixAchat",
               "Dosage", "Forme", "DatePeremption", categorie, unites_par_boite,
               marge_personnalisee
        FROM stock
        {where_clause}
        ORDER BY "Designation"
    """, params)
    return cursor.fetchall()

@router.get("/designations")
def get_designations(db=Depends(get_db), user=Depends(require_role("admin", "medecin", "secretaire"))):
    """Liste allégée du stock (sans alertes/fournisseur) pour l'autocomplete des lignes d'ordonnance.
    Filtrée sur les médicaments uniquement : le matériel médical n'a pas vocation à être prescrit."""
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "Designation", "Quantite", "PrixVente", "PrixAchat",
               "Dosage", "Forme"
        FROM stock
        WHERE categorie = 'medicament'
        ORDER BY "Designation"
    """)
    return cursor.fetchall()

@router.get("/disponibilite")
def get_stock_disponibilite(q: str = "", db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock" as id, "Designation" as designation,
               "Dosage" as dosage, "Forme" as forme,
               "Quantite" as quantite, "SeuilAlerte" as seuil_alerte,
               "PrixVente" as prix_vente, "PrixAchat" as prix_achat,
               categorie
        FROM stock
        WHERE LOWER("Designation") LIKE LOWER(%s)
          AND "Quantite" > 0
          AND categorie = 'medicament'
        ORDER BY "Designation" ASC
        LIMIT 15
    """, (f'%{q}%',))
    return cursor.fetchall()

@router.get("/alertes")
def get_alertes(db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "Designation", "Quantite", "SeuilAlerte", categorie
        FROM stock
        WHERE "Quantite" <= "SeuilAlerte"
          AND categorie <> 'equipement'
        ORDER BY "Quantite"
    """)
    return cursor.fetchall()

@router.get("/alertes-peremption")
def get_alertes_peremption(db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "Designation", "DatePeremption"
        FROM stock
        WHERE "DatePeremption" IS NOT NULL
          AND "DatePeremption" <> ''
          AND "DatePeremption"::date <= CURRENT_DATE + INTERVAL '30 days'
        ORDER BY "DatePeremption"
    """)
    return cursor.fetchall()

def _calculer_recalcul_prix(cursor):
    """Calcule le recalcul des prix de vente à partir des marges (catégorie ou
    personnalisée par article). Lecture seule — utilisé par l'aperçu et
    l'application réelle pour garantir un résultat strictement identique.

    Retourne (a_modifier, ignores) :
    - a_modifier : articles dont le nouveau prix diffère du PrixVente actuel
    - ignores : articles à PrixAchat NULL ou <= 0, exclus du calcul (signalés
      plutôt que recalculés en silence vers un prix aberrant à 0 FCFA)
    """
    cursor.execute("""
        SELECT s."idStock", s."Designation", s.categorie,
               s."PrixAchat", s."PrixVente",
               s.marge_personnalisee, m.marge_pourcentage
        FROM stock s
        JOIN marges_categorie m ON m.categorie = s.categorie
        WHERE s.categorie <> 'equipement'
        ORDER BY s."Designation"
    """)
    a_modifier, ignores = [], []
    for row in cursor.fetchall():
        prix_achat = row["PrixAchat"]
        if prix_achat is None or float(prix_achat) <= 0:
            ignores.append({
                "id": row["idStock"],
                "designation": row["Designation"],
                "categorie": row["categorie"],
                "PrixAchat": prix_achat,
                "raison": "PrixAchat nul ou manquant",
            })
            continue
        # NUMERIC -> Decimal via psycopg2 : conversion float obligatoire avant
        # de mélanger avec PrixAchat (REAL -> float), cf. bug Phase 15
        marge = row["marge_personnalisee"] if row["marge_personnalisee"] is not None else row["marge_pourcentage"]
        marge = float(marge)
        nouveau_prix = arrondir_prix_fcfa(float(prix_achat) * (1 + marge / 100))
        ancien_prix = row["PrixVente"]
        if ancien_prix is None or float(ancien_prix) != float(nouveau_prix):
            a_modifier.append({
                "id": row["idStock"],
                "designation": row["Designation"],
                "categorie": row["categorie"],
                "PrixAchat": float(prix_achat),
                "ancien_prix_vente": float(ancien_prix) if ancien_prix is not None else None,
                "nouveau_prix_vente": nouveau_prix,
                "marge_appliquee": marge,
                "marge_source": "personnalisee" if row["marge_personnalisee"] is not None else "categorie",
            })
    return a_modifier, ignores


@router.get("/recalculer-prix/apercu")
def apercu_recalcul_prix(db=Depends(get_db), user=Depends(require_role("admin"))):
    """Aperçu du recalcul des prix de vente — ne modifie rien en base."""
    a_modifier, ignores = _calculer_recalcul_prix(db.cursor())
    return {
        "nb_articles_a_modifier": len(a_modifier),
        "articles": a_modifier,
        "articles_ignores": ignores,
    }


@router.post("/recalculer-prix/appliquer")
def appliquer_recalcul_prix(request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    """Applique réellement le recalcul des prix de vente (même calcul que l'aperçu)."""
    cursor = db.cursor()
    a_modifier, ignores = _calculer_recalcul_prix(cursor)
    for ligne in a_modifier:
        cursor.execute(
            'UPDATE stock SET "PrixVente" = %s WHERE "idStock" = %s',
            (ligne["nouveau_prix_vente"], ligne["id"]),
        )
    db.commit()
    log_audit(db, request, user, "RECALCUL_PRIX", "stock", None, {
        "nb_articles_modifies": len(a_modifier),
        "articles": a_modifier,
        "articles_ignores": ignores,
    })
    return {
        "message": f"{len(a_modifier)} article(s) mis à jour",
        "nb_articles_modifies": len(a_modifier),
        "articles": a_modifier,
        "articles_ignores": ignores,
    }


@router.post("/")
def create_article(article: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(article, ["Designation", "Quantite", "PrixVente"])
    unites_par_boite = valider_categorie_et_unites(article)
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO stock ("DateEntree", "Type", "Designation", "Fournisseur",
                          "Quantite", "SeuilAlerte", "PrixVente", "PrixAchat",
                          "Dosage", "Forme", "DatePeremption", categorie, unites_par_boite)
        VALUES (%(DateEntree)s, %(Type)s, %(Designation)s, %(Fournisseur)s,
                %(Quantite)s, %(SeuilAlerte)s, %(PrixVente)s, %(PrixAchat)s,
                %(Dosage)s, %(Forme)s, %(DatePeremption)s, %(categorie)s, %(unites_par_boite)s)
        RETURNING "idStock"
    """, {
        "DateEntree": article.get("DateEntree"),
        "Type": article.get("Type"),
        "Designation": article.get("Designation"),
        "Fournisseur": article.get("Fournisseur"),
        "Quantite": article.get("Quantite"),
        "SeuilAlerte": article.get("SeuilAlerte"),
        "PrixVente": article.get("PrixVente"),
        "PrixAchat": article.get("PrixAchat"),
        "Dosage": article.get("Dosage"),
        "Forme": article.get("Forme"),
        "DatePeremption": article.get("DatePeremption"),
        "categorie": article.get("categorie", "medicament"),
        "unites_par_boite": unites_par_boite,
    })
    db.commit()
    new_id = cursor.fetchone()["idStock"]
    log_audit(db, request, user, "CREATE", "stock", new_id, article)
    return {"message": "Article créé", "id": new_id}


@router.put("/{stock_id}")
def update_article(stock_id: int, article: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(article, ["Designation", "Quantite", "PrixVente"])
    unites_par_boite = valider_categorie_et_unites(article)

    # marge_personnalisee : mise à jour uniquement si la clé est présente dans le
    # payload (NULL explicite = revenir à la marge de catégorie). Un payload sans
    # la clé ne doit pas effacer une marge existante.
    set_marge = ""
    params_marge = {}
    if "marge_personnalisee" in article:
        marge = article["marge_personnalisee"]
        if marge is not None:
            marge = valider_marge_pourcentage(marge, "marge_personnalisee")
        set_marge = ", marge_personnalisee = %(marge_personnalisee)s"
        params_marge = {"marge_personnalisee": marge}

    cursor = db.cursor()
    cursor.execute(f"""
        UPDATE stock
        SET "DateEntree" = %(DateEntree)s,
            "Type" = %(Type)s,
            "Designation" = %(Designation)s,
            "Fournisseur" = %(Fournisseur)s,
            "Quantite" = %(Quantite)s,
            "SeuilAlerte" = %(SeuilAlerte)s,
            "PrixVente" = %(PrixVente)s,
            "PrixAchat" = %(PrixAchat)s,
            "Dosage" = %(Dosage)s,
            "Forme" = %(Forme)s,
            "DatePeremption" = %(DatePeremption)s,
            categorie = %(categorie)s,
            unites_par_boite = %(unites_par_boite)s
            {set_marge}
        WHERE "idStock" = %(idStock)s
    """, {
        **params_marge,
        "DateEntree": article.get("DateEntree"),
        "Type": article.get("Type"),
        "Designation": article.get("Designation"),
        "Fournisseur": article.get("Fournisseur"),
        "Quantite": article.get("Quantite"),
        "SeuilAlerte": article.get("SeuilAlerte"),
        "PrixVente": article.get("PrixVente"),
        "PrixAchat": article.get("PrixAchat"),
        "Dosage": article.get("Dosage"),
        "Forme": article.get("Forme"),
        "DatePeremption": article.get("DatePeremption"),
        "categorie": article.get("categorie", "medicament"),
        "unites_par_boite": unites_par_boite,
        "idStock": stock_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    db.commit()
    log_audit(db, request, user, "UPDATE", "stock", stock_id, article)
    return {"message": "Article mis à jour"}


@router.post("/{stock_id}/reapprovisionner")
def reapprovisionner_article(stock_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    """Ajoute du stock à un article existant, soit en unités directes
    (quantite_unites), soit en boîtes (nombre_boites × unites_par_boite).
    Exactement un des deux champs doit être fourni."""
    quantite_unites = data.get("quantite_unites")
    nombre_boites = data.get("nombre_boites")
    cursor = db.cursor()
    unites_ajoutees = convertir_en_unites(cursor, stock_id, quantite_unites, nombre_boites)

    cursor.execute(
        'UPDATE stock SET "Quantite" = "Quantite" + %s WHERE "idStock" = %s RETURNING "Quantite"',
        (unites_ajoutees, stock_id),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    nouvelle_quantite = row["Quantite"]
    db.commit()
    champ = "quantite_unites" if quantite_unites is not None else "nombre_boites"
    log_audit(db, request, user, "UPDATE", "stock", stock_id, {
        "action": "reapprovisionnement",
        champ: int(quantite_unites if quantite_unites is not None else nombre_boites),
        "unites_ajoutees": unites_ajoutees,
        "nouvelle_quantite": nouvelle_quantite,
    })
    return {
        "message": "Stock réapprovisionné",
        "unites_ajoutees": unites_ajoutees,
        "nouvelle_quantite": nouvelle_quantite,
    }


@router.post("/sortie")
def create_sortie(data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["Designation", "QuantiteSortie"])
    require_positive(data, ["QuantiteSortie"])
    cursor = db.cursor()
    cursor.execute('SELECT "PrixVente", "PrixAchat", "Quantite" FROM stock WHERE "Designation" = %s', (data["Designation"],))
    article = cursor.fetchone()
    if not article:
        raise HTTPException(status_code=404, detail="Article non trouvé dans le stock")

    quantite_sortie = data["QuantiteSortie"]
    prix_vente = data.get("PrixVente", article["PrixVente"])
    prix_achat = data.get("PrixAchat", article["PrixAchat"])

    cursor.execute("""
        INSERT INTO sortie ("DateSortie", "Designation", "QuantiteSortie", "PrixVente",
                            "Montant", "Patient", "idOrdonnance", "PrixAchat")
        VALUES (%(DateSortie)s, %(Designation)s, %(QuantiteSortie)s, %(PrixVente)s,
                %(Montant)s, %(Patient)s, %(idOrdonnance)s, %(PrixAchat)s)
        RETURNING "idSortie"
    """, {
        "DateSortie": data.get("DateSortie") or datetime.utcnow().strftime("%Y-%m-%d"),
        "Designation": data["Designation"],
        "QuantiteSortie": quantite_sortie,
        "PrixVente": prix_vente,
        "Montant": quantite_sortie * prix_vente,
        "Patient": data.get("Patient", ""),
        "idOrdonnance": data.get("idOrdonnance"),
        "PrixAchat": prix_achat,
    })
    sortie_id = cursor.fetchone()["idSortie"]

    cursor.execute('UPDATE stock SET "Quantite" = "Quantite" - %s WHERE "Designation" = %s', (quantite_sortie, data["Designation"]))

    db.commit()
    log_audit(db, request, user, "CREATE", "sortie", sortie_id, data)
    return {"message": "Sortie enregistrée", "id": sortie_id}


@router.delete("/{stock_id}")
def delete_article(stock_id: int, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("DELETE FROM stock WHERE \"idStock\" = %s", (stock_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    db.commit()
    log_audit(db, request, user, "DELETE", "stock", stock_id, None)
    return {"message": "Article supprimé"}
