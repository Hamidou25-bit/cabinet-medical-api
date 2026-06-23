from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import require_role
from validation import require_fields

router = APIRouter(prefix="/type-stock", tags=["Type Stock"])


@router.get("/")
def get_types_stock(db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("SELECT id, libelle, categorie FROM type_stock ORDER BY libelle")
    return cursor.fetchall()


@router.post("/")
def create_type_stock(data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["libelle", "categorie"])
    if data["categorie"] not in ("medicament", "materiel"):
        raise HTTPException(status_code=400, detail="Catégorie invalide (medicament ou materiel attendu)")
    cursor = db.cursor()
    cursor.execute("SELECT id FROM type_stock WHERE libelle = %s", (data["libelle"],))
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail="Ce type existe déjà")
    cursor.execute(
        "INSERT INTO type_stock (libelle, categorie) VALUES (%(libelle)s, %(categorie)s) RETURNING id",
        {"libelle": data["libelle"], "categorie": data["categorie"]},
    )
    db.commit()
    return {"message": "Type créé", "id": cursor.fetchone()["id"]}


@router.delete("/{type_stock_id}")
def delete_type_stock(type_stock_id: int, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("SELECT libelle FROM type_stock WHERE id = %s", (type_stock_id,))
    type_stock = cursor.fetchone()
    if not type_stock:
        raise HTTPException(status_code=404, detail="Type non trouvé")

    # Comparaison insensible à la casse/aux accents : le champ "Type" historique contient des
    # variantes orthographiques du même libellé (ex. "Medicament" sans accent, cf. Phase 16) qui
    # ne correspondraient pas à une égalité stricte et laisseraient passer une suppression à tort.
    cursor.execute(
        'SELECT COUNT(*) AS n FROM stock WHERE unaccent(LOWER("Type")) = unaccent(LOWER(%s))',
        (type_stock["libelle"],),
    )
    if cursor.fetchone()["n"] > 0:
        raise HTTPException(status_code=409, detail="Ce type est utilisé par des articles de stock existants")
    cursor.execute(
        "SELECT COUNT(*) AS n FROM lignes_achat WHERE unaccent(LOWER(type_article)) = unaccent(LOWER(%s))",
        (type_stock["libelle"],),
    )
    if cursor.fetchone()["n"] > 0:
        raise HTTPException(status_code=409, detail="Ce type est utilisé par des lignes d'achat existantes")

    cursor.execute("DELETE FROM type_stock WHERE id = %s", (type_stock_id,))
    db.commit()
    return {"message": "Type supprimé"}
