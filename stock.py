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
