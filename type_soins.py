from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user
from validation import require_fields

router = APIRouter(prefix="/type-soins", tags=["Type Soins"])


@router.get("/")
def get_type_soins(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT id, nom, prix_defaut FROM type_soin ORDER BY nom")
    return cursor.fetchall()


@router.post("/")
def create_type_soin(data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["nom"])
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO type_soin (nom, prix_defaut) VALUES (%(nom)s, %(prix_defaut)s) RETURNING id",
        {"nom": data["nom"], "prix_defaut": data.get("prix_defaut", 0)},
    )
    db.commit()
    return {"message": "Type de soin créé", "id": cursor.fetchone()["id"]}


@router.put("/{type_soin_id}")
def update_type_soin(type_soin_id: int, data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["nom"])
    cursor = db.cursor()
    cursor.execute(
        "UPDATE type_soin SET nom = %(nom)s, prix_defaut = %(prix_defaut)s WHERE id = %(id)s",
        {"nom": data["nom"], "prix_defaut": data.get("prix_defaut", 0), "id": type_soin_id},
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Type de soin non trouvé")
    db.commit()
    return {"message": "Type de soin mis à jour"}


@router.delete("/{type_soin_id}")
def delete_type_soin(type_soin_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) AS n FROM soins WHERE type_soin_id = %s", (type_soin_id,))
    if cursor.fetchone()["n"] > 0:
        raise HTTPException(status_code=409, detail="Ce type de soin est utilisé par des soins existants")
    cursor.execute("DELETE FROM type_soin WHERE id = %s", (type_soin_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Type de soin non trouvé")
    db.commit()
    return {"message": "Type de soin supprimé"}
