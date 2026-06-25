from fastapi import APIRouter, Depends
from database import get_db
from auth import get_current_user, require_role

router = APIRouter(prefix="/parametres", tags=["Paramètres"])


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
