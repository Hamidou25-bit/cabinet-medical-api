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


@router.put("/{consultation_id}")
def update_consultation(consultation_id: int, consultation: dict, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        UPDATE consultations
        SET date_consult = %(date_consult)s,
            prix_unitaire = %(prix_unitaire)s,
            montant_total = %(montant_total)s,
            patient_id = %(patient_id)s,
            motif = %(motif)s,
            diagnostic = %(diagnostic)s,
            observation = %(observation)s,
            traitement_apres_diagnostic = %(traitement_apres_diagnostic)s
        WHERE id = %s
    """, (
        consultation.get("date_consult"),
        consultation.get("prix_unitaire"),
        consultation.get("montant_total"),
        consultation.get("patient_id"),
        consultation.get("motif"),
        consultation.get("diagnostic"),
        consultation.get("observation"),
        consultation.get("traitement_apres_diagnostic"),
        consultation_id
    ))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Consultation non trouvée")
    db.commit()
    return {"message": "Consultation mise à jour"}


@router.delete("/{consultation_id}")
def delete_consultation(consultation_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM consultations WHERE id = %s", (consultation_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Consultation non trouvée")
    db.commit()
    return {"message": "Consultation supprimée"}
