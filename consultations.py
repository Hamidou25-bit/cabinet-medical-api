from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from auth import get_current_user
from validation import require_fields
from audit_log import log_audit

router = APIRouter(prefix="/consultations", tags=["Consultations"])

@router.get("/")
def get_consultations(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT c.id, c.date_consult, c.prix_unitaire, c.montant_total,
               c.motif, c.diagnostic, c.observation,
               c.patient_id, c.medecin_id, c.mode_paiement, c.mutuelle_id,
               p.nom, p.prenom,
               m.nom AS medecin_nom,
               mu.nom AS mutuelle_nom
        FROM consultations c
        LEFT JOIN patients p ON c.patient_id = p.id
        LEFT JOIN medecin m ON c.medecin_id = m.id
        LEFT JOIN mutuelles mu ON c.mutuelle_id = mu.id
        ORDER BY c.date_consult DESC, c.id DESC
    """)
    return cursor.fetchall()

@router.get("/{consultation_id}")
def get_consultation(consultation_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT c.*, p.nom, p.prenom, m.nom AS medecin_nom, mu.nom AS mutuelle_nom
        FROM consultations c
        LEFT JOIN patients p ON c.patient_id = p.id
        LEFT JOIN medecin m ON c.medecin_id = m.id
        LEFT JOIN mutuelles mu ON c.mutuelle_id = mu.id
        WHERE c.id = %s
    """, (consultation_id,))
    consultation = cursor.fetchone()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation non trouvée")
    return consultation

@router.post("/")
def create_consultation(consultation: dict, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(consultation, ["patient_id", "date_consult", "motif"])
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO consultations (date_consult, prix_unitaire, montant_total,
                                  patient_id, medecin_id, motif, diagnostic, observation,
                                  mode_paiement, mutuelle_id)
        VALUES (%(date_consult)s, %(prix_unitaire)s, %(montant_total)s,
                %(patient_id)s, %(medecin_id)s, %(motif)s, %(diagnostic)s, %(observation)s,
                %(mode_paiement)s, %(mutuelle_id)s)
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
        "mode_paiement": consultation.get("mode_paiement", "especes"),
        "mutuelle_id": consultation.get("mutuelle_id"),
    })
    db.commit()
    new_id = cursor.fetchone()["id"]
    log_audit(db, request, user, "CREATE", "consultations", new_id, consultation)
    return {"message": "Consultation créée", "id": new_id}


@router.put("/{consultation_id}")
def update_consultation(consultation_id: int, consultation: dict, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(consultation, ["patient_id", "date_consult", "motif"])
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
            mode_paiement = %(mode_paiement)s,
            mutuelle_id = %(mutuelle_id)s
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
        "mode_paiement": consultation.get("mode_paiement", "especes"),
        "mutuelle_id": consultation.get("mutuelle_id"),
        "id": consultation_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Consultation non trouvée")
    db.commit()
    log_audit(db, request, user, "UPDATE", "consultations", consultation_id, consultation)
    return {"message": "Consultation mise à jour"}


@router.delete("/{consultation_id}")
def delete_consultation(consultation_id: int, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM consultations WHERE id = %s", (consultation_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Consultation non trouvée")
    db.commit()
    log_audit(db, request, user, "DELETE", "consultations", consultation_id, None)
    return {"message": "Consultation supprimée"}
