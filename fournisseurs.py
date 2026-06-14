from fastapi import APIRouter, Depends, HTTPException
import psycopg2
from database import get_db
from auth import get_current_user, require_role

router = APIRouter(prefix="/fournisseurs", tags=["Fournisseurs"])


@router.get("/")
def get_fournisseurs(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, nom, type_article, telephone, adresse
        FROM fournisseur
        ORDER BY nom
    """)
    return cursor.fetchall()


@router.get("/{fournisseur_id}")
def get_fournisseur(fournisseur_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, nom, type_article, telephone, adresse
        FROM fournisseur
        WHERE id = %s
    """, (fournisseur_id,))
    fournisseur = cursor.fetchone()
    if not fournisseur:
        raise HTTPException(status_code=404, detail="Fournisseur non trouvé")
    return fournisseur


@router.post("/")
def create_fournisseur(data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO fournisseur (nom, type_article, telephone, adresse)
        VALUES (%(nom)s, %(type_article)s, %(telephone)s, %(adresse)s)
        RETURNING id
    """, {
        "nom": data["nom"],
        "type_article": data.get("type_article"),
        "telephone": data.get("telephone"),
        "adresse": data.get("adresse"),
    })
    db.commit()
    return {"message": "Fournisseur créé", "id": cursor.fetchone()["id"]}


@router.put("/{fournisseur_id}")
def update_fournisseur(fournisseur_id: int, data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        UPDATE fournisseur
        SET nom = %(nom)s,
            type_article = %(type_article)s,
            telephone = %(telephone)s,
            adresse = %(adresse)s
        WHERE id = %(id)s
    """, {
        "nom": data["nom"],
        "type_article": data.get("type_article"),
        "telephone": data.get("telephone"),
        "adresse": data.get("adresse"),
        "id": fournisseur_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Fournisseur non trouvé")
    db.commit()
    return {"message": "Fournisseur mis à jour"}


@router.delete("/{fournisseur_id}")
def delete_fournisseur(fournisseur_id: int, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM fournisseur WHERE id = %s", (fournisseur_id,))
    except psycopg2.errors.ForeignKeyViolation:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ce fournisseur est référencé par des achats et ne peut pas être supprimé")
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Fournisseur non trouvé")
    db.commit()
    return {"message": "Fournisseur supprimé"}
