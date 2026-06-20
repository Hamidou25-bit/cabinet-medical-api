from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from auth import require_role
from validation import require_fields, require_positive
from audit_log import log_audit

router = APIRouter(prefix="/stock", tags=["Stock"])

@router.get("/")
def get_stock(db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "DateEntree", "Type", "Designation", "Fournisseur",
               "Quantite", "SeuilAlerte", "PrixVente", "PrixAchat",
               "Dosage", "Forme", "DatePeremption"
        FROM stock
        ORDER BY "Designation"
    """)
    return cursor.fetchall()

@router.get("/designations")
def get_designations(db=Depends(get_db), user=Depends(require_role("admin", "medecin", "secretaire"))):
    """Liste allégée du stock (sans alertes/fournisseur) pour l'autocomplete des lignes d'ordonnance."""
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "Designation", "Quantite", "PrixVente", "PrixAchat",
               "Dosage", "Forme"
        FROM stock
        ORDER BY "Designation"
    """)
    return cursor.fetchall()

@router.get("/alertes")
def get_alertes(db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "Designation", "Quantite", "SeuilAlerte"
        FROM stock
        WHERE "Quantite" <= "SeuilAlerte"
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

@router.post("/")
def create_article(article: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(article, ["Designation", "Quantite", "PrixVente"])
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO stock ("DateEntree", "Type", "Designation", "Fournisseur",
                          "Quantite", "SeuilAlerte", "PrixVente", "PrixAchat",
                          "Dosage", "Forme", "DatePeremption")
        VALUES (%(DateEntree)s, %(Type)s, %(Designation)s, %(Fournisseur)s,
                %(Quantite)s, %(SeuilAlerte)s, %(PrixVente)s, %(PrixAchat)s,
                %(Dosage)s, %(Forme)s, %(DatePeremption)s)
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
    })
    db.commit()
    new_id = cursor.fetchone()["idStock"]
    log_audit(db, request, user, "CREATE", "stock", new_id, article)
    return {"message": "Article créé", "id": new_id}


@router.put("/{stock_id}")
def update_article(stock_id: int, article: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(article, ["Designation", "Quantite", "PrixVente"])
    cursor = db.cursor()
    cursor.execute("""
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
            "DatePeremption" = %(DatePeremption)s
        WHERE "idStock" = %(idStock)s
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
        "idStock": stock_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    db.commit()
    log_audit(db, request, user, "UPDATE", "stock", stock_id, article)
    return {"message": "Article mis à jour"}


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
