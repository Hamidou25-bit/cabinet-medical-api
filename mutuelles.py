from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user, require_role
from validation import require_fields

router = APIRouter(prefix="/mutuelles", tags=["Mutuelles"])


@router.get("/")
def get_mutuelles(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT id, nom FROM mutuelles ORDER BY nom")
    return cursor.fetchall()


@router.post("/")
def create_mutuelle(data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["nom"])
    cursor = db.cursor()
    cursor.execute("INSERT INTO mutuelles (nom) VALUES (%(nom)s) RETURNING id", {"nom": data["nom"]})
    db.commit()
    return {"message": "Mutuelle créée", "id": cursor.fetchone()["id"]}


@router.put("/{mutuelle_id}")
def update_mutuelle(mutuelle_id: int, data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["nom"])
    cursor = db.cursor()
    cursor.execute("UPDATE mutuelles SET nom = %(nom)s WHERE id = %(id)s", {"nom": data["nom"], "id": mutuelle_id})
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Mutuelle non trouvée")
    db.commit()
    return {"message": "Mutuelle mise à jour"}


@router.delete("/{mutuelle_id}")
def delete_mutuelle(mutuelle_id: int, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) AS n FROM consultations WHERE mutuelle_id = %s", (mutuelle_id,))
    if cursor.fetchone()["n"] > 0:
        raise HTTPException(status_code=409, detail="Cette mutuelle est utilisée par des consultations existantes")
    cursor.execute("SELECT COUNT(*) AS n FROM ordonnance WHERE mutuelle_id = %s", (mutuelle_id,))
    if cursor.fetchone()["n"] > 0:
        raise HTTPException(status_code=409, detail="Cette mutuelle est utilisée par des ordonnances existantes")
    cursor.execute("DELETE FROM mutuelles WHERE id = %s", (mutuelle_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Mutuelle non trouvée")
    db.commit()
    return {"message": "Mutuelle supprimée"}
