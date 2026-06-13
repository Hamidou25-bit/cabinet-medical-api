from fastapi import APIRouter, Depends
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/stock", tags=["Stock"])

@router.get("/")
def get_stock(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "DateEntree", "Type", "Designation", "Fournisseur",
               "Quantite", "SeuilAlerte", "PrixVente", "PrixAchat"
        FROM stock
        ORDER BY "Designation"
    """)
    return cursor.fetchall()

@router.get("/alertes")
def get_alertes(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "Designation", "Quantite", "SeuilAlerte"
        FROM stock
        WHERE "Quantite" <= "SeuilAlerte"
        ORDER BY "Quantite"
    """)
    return cursor.fetchall()

@router.post("/")
def create_article(article: dict, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO stock ("DateEntree", "Type", "Designation", "Fournisseur",
                          "Quantite", "SeuilAlerte", "PrixVente", "PrixAchat")
        VALUES (%(DateEntree)s, %(Type)s, %(Designation)s, %(Fournisseur)s,
                %(Quantite)s, %(SeuilAlerte)s, %(PrixVente)s, %(PrixAchat)s)
        RETURNING "idStock"
    """, article)
    db.commit()
    return {"message": "Article créé", "id": cursor.fetchone()["idStock"]}


@router.put("/{stock_id}")
def update_article(stock_id: int, article: dict, db=Depends(get_db), user=Depends(get_current_user)):
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
            "PrixAchat" = %(PrixAchat)s
        WHERE "idStock" = %s
    """, (
        article.get("DateEntree"),
        article.get("Type"),
        article.get("Designation"),
        article.get("Fournisseur"),
        article.get("Quantite"),
        article.get("SeuilAlerte"),
        article.get("PrixVente"),
        article.get("PrixAchat"),
        stock_id
    ))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    db.commit()
    return {"message": "Article mis à jour"}


@router.delete("/{stock_id}")
def delete_article(stock_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM stock WHERE \"idStock\" = %s", (stock_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    db.commit()
    return {"message": "Article supprimé"}
