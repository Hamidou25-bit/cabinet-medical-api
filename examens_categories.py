from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user, require_role
from validation import require_fields

router = APIRouter(prefix="/examens-categories", tags=["Examens - Catégories"])


@router.get("/")
def get_categories(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT id, nom FROM type_examen ORDER BY nom")
    return cursor.fetchall()


@router.get("/{categorie_id}")
def get_categorie(categorie_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT id, nom FROM type_examen WHERE id = %s", (categorie_id,))
    categorie = cursor.fetchone()
    if not categorie:
        raise HTTPException(status_code=404, detail="Catégorie non trouvée")
    return categorie


@router.post("/")
def create_categorie(data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["nom"])
    cursor = db.cursor()
    cursor.execute("INSERT INTO type_examen (nom) VALUES (%(nom)s) RETURNING id", {"nom": data["nom"]})
    db.commit()
    return {"message": "Catégorie créée", "id": cursor.fetchone()["id"]}


@router.put("/{categorie_id}")
def update_categorie(categorie_id: int, data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["nom"])
    cursor = db.cursor()
    cursor.execute("UPDATE type_examen SET nom = %(nom)s WHERE id = %(id)s", {"nom": data["nom"], "id": categorie_id})
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Catégorie non trouvée")
    db.commit()
    return {"message": "Catégorie mise à jour"}


@router.delete("/{categorie_id}")
def delete_categorie(categorie_id: int, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) AS total FROM sous_type_examen WHERE type_examen_id = %s", (categorie_id,))
    if cursor.fetchone()["total"] > 0:
        raise HTTPException(status_code=409, detail="Cette catégorie contient des types d'examens et ne peut pas être supprimée")
    cursor.execute("DELETE FROM type_examen WHERE id = %s", (categorie_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Catégorie non trouvée")
    db.commit()
    return {"message": "Catégorie supprimée"}
