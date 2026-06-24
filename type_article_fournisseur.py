from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user, require_role
from validation import require_fields

router = APIRouter(prefix="/type-article-fournisseur", tags=["Type Article Fournisseur"])


@router.get("/")
def get_types(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT id, libelle FROM type_article_fournisseur ORDER BY libelle")
    return cursor.fetchall()


@router.post("/")
def create_type(data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["libelle"])
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO type_article_fournisseur (libelle)
        VALUES (%(libelle)s)
        RETURNING id
    """, {"libelle": data["libelle"]})
    db.commit()
    return {"message": "Type créé", "id": cursor.fetchone()["id"]}


@router.delete("/{type_id}")
def delete_type(type_id: int, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("SELECT libelle FROM type_article_fournisseur WHERE id = %s", (type_id,))
    type_row = cursor.fetchone()
    if not type_row:
        raise HTTPException(status_code=404, detail="Type non trouvé")

    cursor.execute("SELECT COUNT(*) AS n FROM fournisseur WHERE type_article = %s", (type_row["libelle"],))
    if cursor.fetchone()["n"] > 0:
        raise HTTPException(status_code=409, detail="Ce type est utilisé par des fournisseurs existants")

    cursor.execute("DELETE FROM type_article_fournisseur WHERE id = %s", (type_id,))
    db.commit()
    return {"message": "Type supprimé"}
