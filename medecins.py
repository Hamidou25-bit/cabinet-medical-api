from fastapi import APIRouter, Depends, HTTPException
import psycopg2
from database import get_db
from auth import get_current_user, require_role
from validation import require_fields

router = APIRouter(prefix="/medecins", tags=["Prescripteurs"])


@router.get("/")
def get_medecins(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT id, nom FROM medecin ORDER BY nom")
    return cursor.fetchall()


@router.get("/{medecin_id}")
def get_medecin(medecin_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT id, nom FROM medecin WHERE id = %s", (medecin_id,))
    medecin = cursor.fetchone()
    if not medecin:
        raise HTTPException(status_code=404, detail="Prescripteur non trouvé")
    return medecin


@router.post("/")
def create_medecin(data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["nom"])
    cursor = db.cursor()
    cursor.execute("INSERT INTO medecin (nom) VALUES (%(nom)s) RETURNING id", {"nom": data["nom"]})
    db.commit()
    return {"message": "Prescripteur créé", "id": cursor.fetchone()["id"]}


@router.put("/{medecin_id}")
def update_medecin(medecin_id: int, data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["nom"])
    cursor = db.cursor()
    cursor.execute("UPDATE medecin SET nom = %(nom)s WHERE id = %(id)s", {"nom": data["nom"], "id": medecin_id})
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Prescripteur non trouvé")
    db.commit()
    return {"message": "Prescripteur mis à jour"}


@router.delete("/{medecin_id}")
def delete_medecin(medecin_id: int, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM medecin WHERE id = %s", (medecin_id,))
    except psycopg2.errors.ForeignKeyViolation:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ce prescripteur est référencé par des rendez-vous, consultations ou examens et ne peut pas être supprimé")
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Prescripteur non trouvé")
    db.commit()
    return {"message": "Prescripteur supprimé"}
