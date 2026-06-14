from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/consultations", tags=["Consultations"])

@router.get("/")
def get_consultations(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT c.id, c.date_consult, c.prix_unitaire, c.montant_total,
               c.motif, c.diagnostic, c.observation, c.traitement_apres_diagnostic,
               c.patient_id, c.medecin_id,
               p.nom, p.prenom,
               m.nom AS medecin_nom
        FROM consultations c
        LEFT JOIN patients p ON c.patient_id = p.id
        LEFT JOIN medecin m ON c.medecin_id = m.id
        ORDER BY c.date_consult DESC, c.id DESC
    """)
    return cursor.fetchall()

@router.get("/{consultation_id}")
def get_consultation(consultation_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT c.*, p.nom, p.prenom, m.nom AS medecin_nom
        FROM consultations c
        LEFT JOIN patients p ON c.patient_id = p.id
        LEFT JOIN medecin m ON c.medecin_id = m.id
        WHERE c.id = %s
    """, (consultation_id,))
    consultation = cursor.fetchone()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation non trouvée")
    return consultation

@router.post("/")
def create_consultation(consultation: dict, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO consultations (date_consult, prix_unitaire, montant_total,
                                  patient_id, medecin_id, motif, diagnostic, observation,
                                  traitement_apres_diagnostic)
        VALUES (%(date_consult)s, %(prix_unitaire)s, %(montant_total)s,
                %(patient_id)s, %(medecin_id)s, %(motif)s, %(diagnostic)s, %(observation)s,
                %(traitement_apres_diagnostic)s)
        RETURNING id
    """, {
        "date_consult": consultation["date_consult"],
        "prix_unitaire": consultation.get("prix_unitaire", 0),
        "montant_total": consultation.get("montant_total", 0),
        "patient_id": consultation["patient_id"],
        "medecin_id": consultation.get("medecin_id"),
        "motif": consultation.get("motif"),
        "diagnostic": consultation.get("diagnostic"),
        "observation": consultation.get("observation"),
        "traitement_apres_diagnostic": consultation.get("traitement_apres_diagnostic"),
    })
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
            medecin_id = %(medecin_id)s,
            motif = %(motif)s,
            diagnostic = %(diagnostic)s,
            observation = %(observation)s,
            traitement_apres_diagnostic = %(traitement_apres_diagnostic)s
        WHERE id = %(id)s
    """, {
        "date_consult": consultation["date_consult"],
        "prix_unitaire": consultation.get("prix_unitaire", 0),
        "montant_total": consultation.get("montant_total", 0),
        "patient_id": consultation["patient_id"],
        "medecin_id": consultation.get("medecin_id"),
        "motif": consultation.get("motif"),
        "diagnostic": consultation.get("diagnostic"),
        "observation": consultation.get("observation"),
        "traitement_apres_diagnostic": consultation.get("traitement_apres_diagnostic"),
        "id": consultation_id,
    })
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
