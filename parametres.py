from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user, require_role
from stock_utils import valider_marge_pourcentage

router = APIRouter(prefix="/parametres", tags=["Paramètres"])


@router.get("/marges")
def get_marges(db=Depends(get_db), user=Depends(get_current_user)):
    cur = db.cursor()
    cur.execute("SELECT categorie, marge_pourcentage FROM marges_categorie ORDER BY categorie")
    return cur.fetchall()


@router.put("/marges/{categorie}")
def update_marge(categorie: str, data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    marge = valider_marge_pourcentage(data.get("marge_pourcentage"))
    cur = db.cursor()
    cur.execute(
        "UPDATE marges_categorie SET marge_pourcentage = %s WHERE categorie = %s",
        (marge, categorie),
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Catégorie inconnue : {categorie}")
    db.commit()
    return {"message": "Marge mise à jour", "categorie": categorie, "marge_pourcentage": marge}


@router.get("/")
def get_parametres(db=Depends(get_db), user=Depends(get_current_user)):
    cur = db.cursor()
    cur.execute("SELECT cle, valeur, description FROM parametres_cabinet ORDER BY id")
    rows = cur.fetchall()
    return {row["cle"]: {"valeur": row["valeur"], "description": row["description"]} for row in rows}


@router.get("/public")
def get_parametres_public(db=Depends(get_db)):
    cur = db.cursor()
    cur.execute("""
        SELECT cle, valeur FROM parametres_cabinet
        WHERE cle IN ('nom_cabinet', 'adresse_cabinet', 'telephone_cabinet', 'logo_cabinet')
    """)
    rows = cur.fetchall()
    return {row["cle"]: row["valeur"] for row in rows}


@router.put("/")
def update_parametres(data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    cur = db.cursor()
    for cle, valeur in data.items():
        cur.execute("""
            UPDATE parametres_cabinet SET valeur = %s, updated_at = CURRENT_TIMESTAMP
            WHERE cle = %s
        """, (str(valeur), cle))
    db.commit()
    return {"message": "Paramètres mis à jour"}
