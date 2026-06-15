from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user, require_role
from validation import require_fields

router = APIRouter(prefix="/examens-types", tags=["Examens - Types"])


@router.get("/")
def get_types(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT ste.id, ste.nom, ste.tarif, ste.type_examen_id, te.nom AS type_nom
        FROM sous_type_examen ste
        LEFT JOIN type_examen te ON ste.type_examen_id = te.id
        ORDER BY te.nom, ste.nom
    """)
    return cursor.fetchall()


@router.get("/{type_id}")
def get_type(type_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT ste.id, ste.nom, ste.tarif, ste.type_examen_id, te.nom AS type_nom
        FROM sous_type_examen ste
        LEFT JOIN type_examen te ON ste.type_examen_id = te.id
        WHERE ste.id = %s
    """, (type_id,))
    type_examen = cursor.fetchone()
    if not type_examen:
        raise HTTPException(status_code=404, detail="Type d'examen non trouvé")
    return type_examen


@router.post("/")
def create_type(data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["nom", "type_examen_id"])
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO sous_type_examen (type_examen_id, nom, tarif)
        VALUES (%(type_examen_id)s, %(nom)s, %(tarif)s)
        RETURNING id
    """, {
        "type_examen_id": data["type_examen_id"],
        "nom": data["nom"],
        "tarif": data.get("tarif", 0),
    })
    db.commit()
    return {"message": "Type d'examen créé", "id": cursor.fetchone()["id"]}


@router.put("/{type_id}")
def update_type(type_id: int, data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["nom", "type_examen_id"])
    cursor = db.cursor()
    cursor.execute("""
        UPDATE sous_type_examen
        SET type_examen_id = %(type_examen_id)s, nom = %(nom)s, tarif = %(tarif)s
        WHERE id = %(id)s
    """, {
        "type_examen_id": data["type_examen_id"],
        "nom": data["nom"],
        "tarif": data.get("tarif", 0),
        "id": type_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Type d'examen non trouvé")
    db.commit()
    return {"message": "Type d'examen mis à jour"}


@router.delete("/{type_id}")
def delete_type(type_id: int, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) AS total FROM examens_complementaires WHERE sous_type_examen_id = %s", (type_id,))
    if cursor.fetchone()["total"] > 0:
        raise HTTPException(status_code=409, detail="Ce type d'examen est utilisé par des examens existants et ne peut pas être supprimé")
    cursor.execute("DELETE FROM sous_type_examen WHERE id = %s", (type_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Type d'examen non trouvé")
    db.commit()
    return {"message": "Type d'examen supprimé"}
