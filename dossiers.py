from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from auth import get_current_user
from audit_log import log_audit

router = APIRouter(prefix="/dossiers", tags=["Dossiers"])

NB_CONSULTATIONS_MIN = 2


@router.post("/")
def create_dossier(payload: dict, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    patient_id = payload.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=400, detail="patient_id requis")
    cursor = db.cursor()

    cursor.execute("SELECT id FROM patients WHERE id = %s AND (supprime = 0 OR supprime IS NULL)", (patient_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Patient non trouvé")

    cursor.execute("SELECT 1 FROM dossier_patients WHERE patient_id = %s", (patient_id,))
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail="Dossier déjà créé pour ce patient")

    cursor.execute("SELECT COUNT(*) AS n FROM consultations WHERE patient_id = %s", (patient_id,))
    nb_consultations = cursor.fetchone()["n"]
    if nb_consultations < NB_CONSULTATIONS_MIN:
        raise HTTPException(
            status_code=400,
            detail=f"Le dossier ne peut être créé qu'à partir de {NB_CONSULTATIONS_MIN} consultations"
        )

    cursor.execute("""
        INSERT INTO dossier_patients (patient_id, date_dossier, is_suivi)
        VALUES (%s, %s, 0)
        RETURNING id
    """, (patient_id, date.today().isoformat()))
    new_id = cursor.fetchone()["id"]
    db.commit()
    log_audit(db, request, user, "CREATE", "dossier_patients", new_id, {"patient_id": patient_id})
    return {"message": "Dossier créé", "id": new_id}
