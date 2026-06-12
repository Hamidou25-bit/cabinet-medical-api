from fastapi import APIRouter, Depends
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/consultations", tags=["Consultations"])

@router.get("/")
def get_consultations(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT c.id, c.date_consult, c.prix_unitaire, c.montant_total,
               c.motif, c.diagnostic, c.observation, c.traitement_apres_diagnostic,
               p.nom, p.prenom
        FROM consultations c
        LEFT JOIN patients p ON c.patient_id = p.id
        ORDER BY c.date_consult DESC
    """)
    return cursor.fetchall()

@router.get("/{consultation_id}")
def get_consultation(consultation_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT c.*, p.nom, p.prenom
        FROM consultations c
        LEFT JOIN patients p ON c.patient_id = p.id
        WHERE c.id = %s
    """, (consultation_id,))
    return cursor.fetchone()

@router.post("/")
def create_consultation(consultation: dict, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO consultations (date_consult, prix_unitaire, montant_total,
                                  patient_id, motif, diagnostic, observation,
                                  traitement_apres_diagnostic)
        VALUES (%(date_consult)s, %(prix_unitaire)s, %(montant_total)s,
                %(patient_id)s, %(motif)s, %(diagnostic)s, %(observation)s,
                %(traitement_apres_diagnostic)s)
        RETURNING id
    """, consultation)
    db.commit()
    return {"message": "Consultation créée", "id": cursor.fetchone()["id"]}
