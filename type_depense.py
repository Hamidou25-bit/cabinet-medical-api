from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user, require_role

router = APIRouter(prefix="/type-depense", tags=["Type Dépense"])


@router.get("/")
def get_types_depense(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT id, nom FROM type_depense ORDER BY nom")
    return cursor.fetchall()


@router.get("/{type_depense_id}")
def get_type_depense(type_depense_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT id, nom FROM type_depense WHERE id = %s", (type_depense_id,))
    type_depense = cursor.fetchone()
    if not type_depense:
        raise HTTPException(status_code=404, detail="Type de dépense non trouvé")
    return type_depense


@router.post("/")
def create_type_depense(data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO type_depense (nom)
        VALUES (%(nom)s)
        RETURNING id
    """, {"nom": data["nom"]})
    db.commit()
    return {"message": "Type de dépense créé", "id": cursor.fetchone()["id"]}


@router.put("/{type_depense_id}")
def update_type_depense(type_depense_id: int, data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        UPDATE type_depense
        SET nom = %(nom)s
        WHERE id = %(id)s
    """, {"nom": data["nom"], "id": type_depense_id})
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Type de dépense non trouvé")
    db.commit()
    return {"message": "Type de dépense mis à jour"}


@router.delete("/{type_depense_id}")
def delete_type_depense(type_depense_id: int, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("DELETE FROM type_depense WHERE id = %s", (type_depense_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Type de dépense non trouvé")
    db.commit()
    return {"message": "Type de dépense supprimé"}
