from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/rendez-vous", tags=["Rendez-vous"])


@router.get("/")
def get_rendez_vous(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT r.id, r.date_heure_rdv, r.motif, r.statut, r.notes,
               r.patient_id, r.medecin_id,
               p.nom, p.prenom, m.nom AS medecin_nom
        FROM rendez_vous r
        LEFT JOIN patients p ON r.patient_id = p.id
        LEFT JOIN medecin m ON r.medecin_id = m.id
        ORDER BY r.date_heure_rdv ASC, r.id ASC
    """)
    return cursor.fetchall()


@router.get("/{rendez_vous_id}")
def get_rendez_vous_by_id(rendez_vous_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT r.*, p.nom, p.prenom, m.nom AS medecin_nom
        FROM rendez_vous r
        LEFT JOIN patients p ON r.patient_id = p.id
        LEFT JOIN medecin m ON r.medecin_id = m.id
        WHERE r.id = %s
    """, (rendez_vous_id,))
    rendez_vous = cursor.fetchone()
    if not rendez_vous:
        raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")
    return rendez_vous


@router.post("/")
def create_rendez_vous(data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO rendez_vous (patient_id, medecin_id, date_heure_rdv, motif, statut, notes, date_creation)
        VALUES (%(patient_id)s, %(medecin_id)s, %(date_heure_rdv)s, %(motif)s, %(statut)s, %(notes)s, %(date_creation)s)
        RETURNING id
    """, {
        "patient_id": data["patient_id"],
        "medecin_id": data.get("medecin_id"),
        "date_heure_rdv": data["date_heure_rdv"],
        "motif": data.get("motif"),
        "statut": data.get("statut", "planifié"),
        "notes": data.get("notes"),
        "date_creation": datetime.utcnow().isoformat(),
    })
    db.commit()
    return {"message": "Rendez-vous créé", "id": cursor.fetchone()["id"]}


@router.put("/{rendez_vous_id}")
def update_rendez_vous(rendez_vous_id: int, data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        UPDATE rendez_vous
        SET patient_id = %(patient_id)s,
            medecin_id = %(medecin_id)s,
            date_heure_rdv = %(date_heure_rdv)s,
            motif = %(motif)s,
            statut = %(statut)s,
            notes = %(notes)s
        WHERE id = %(id)s
    """, {
        "patient_id": data.get("patient_id"),
        "medecin_id": data.get("medecin_id"),
        "date_heure_rdv": data.get("date_heure_rdv"),
        "motif": data.get("motif"),
        "statut": data.get("statut"),
        "notes": data.get("notes"),
        "id": rendez_vous_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")
    db.commit()
    return {"message": "Rendez-vous mis à jour"}


@router.delete("/{rendez_vous_id}")
def delete_rendez_vous(rendez_vous_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM rendez_vous WHERE id = %s", (rendez_vous_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")
    db.commit()
    return {"message": "Rendez-vous supprimé"}
