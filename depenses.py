from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from auth import get_current_user, require_role
from validation import require_fields, require_positive
from audit_log import log_audit

router = APIRouter(prefix="/depenses", tags=["Dépenses"])


@router.get("/")
def get_depenses(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT id_depense, date_depense, type_depense, montant, description, achat_id
        FROM depense
        ORDER BY date_depense DESC, id_depense DESC
    """)
    return cursor.fetchall()


@router.post("/")
def create_depense(data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["date_depense", "type_depense", "montant"])
    require_positive(data, ["montant"])
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO depense (date_depense, type_depense, montant, description)
        VALUES (%(date_depense)s, %(type_depense)s, %(montant)s, %(description)s)
        RETURNING id_depense
    """, {
        "date_depense": data["date_depense"],
        "type_depense": data["type_depense"],
        "montant": data["montant"],
        "description": data.get("description"),
    })
    db.commit()
    new_id = cursor.fetchone()["id_depense"]
    log_audit(db, request, user, "CREATE", "depense", new_id, data)
    return {"message": "Dépense créée", "id_depense": new_id}


@router.put("/{depense_id}")
def update_depense(depense_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["date_depense", "type_depense", "montant"])
    require_positive(data, ["montant"])
    cursor = db.cursor()
    cursor.execute("SELECT achat_id FROM depense WHERE id_depense = %s", (depense_id,))
    existing = cursor.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Dépense non trouvée")
    if existing["achat_id"] is not None:
        raise HTTPException(status_code=400, detail="Cette dépense est générée automatiquement depuis un achat. Modifiez l'achat correspondant.")
    cursor.execute("""
        UPDATE depense
        SET date_depense = %(date_depense)s,
            type_depense = %(type_depense)s,
            montant = %(montant)s,
            description = %(description)s
        WHERE id_depense = %(id)s
    """, {
        "date_depense": data["date_depense"],
        "type_depense": data["type_depense"],
        "montant": data["montant"],
        "description": data.get("description"),
        "id": depense_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Dépense non trouvée")
    db.commit()
    log_audit(db, request, user, "UPDATE", "depense", depense_id, data)
    return {"message": "Dépense mise à jour"}


@router.delete("/{depense_id}")
def delete_depense(depense_id: int, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("SELECT achat_id FROM depense WHERE id_depense = %s", (depense_id,))
    existing = cursor.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Dépense non trouvée")
    if existing["achat_id"] is not None:
        raise HTTPException(status_code=400, detail="Cette dépense est générée automatiquement depuis un achat. Supprimez l'achat correspondant pour la supprimer.")
    cursor.execute("DELETE FROM depense WHERE id_depense = %s", (depense_id,))
    db.commit()
    log_audit(db, request, user, "DELETE", "depense", depense_id, None)
    return {"message": "Dépense supprimée"}
