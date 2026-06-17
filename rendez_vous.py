from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user
from validation import require_fields

router = APIRouter(prefix="/rendez-vous", tags=["Rendez-vous"])

STATUTS_VALIDES = {"en_attente", "confirme", "arrive", "annule", "reporte"}


@router.get("/")
def get_rendez_vous(date: str = None, statut: str = None, patient_id: int = None,
                     db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    conditions = []
    params = {}
    if date:
        conditions.append("r.date_heure_rdv LIKE %(date)s")
        params["date"] = f"{date}%"
    if statut:
        conditions.append("r.statut = %(statut)s")
        params["statut"] = statut
    if patient_id:
        conditions.append("r.patient_id = %(patient_id)s")
        params["patient_id"] = patient_id
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    cursor.execute(f"""
        SELECT r.id, r.patient_id, r.medecin_id, r.date_heure_rdv, r.motif, r.statut, r.notes,
               p.nom, p.prenom, m.nom AS medecin_nom
        FROM rendez_vous r
        LEFT JOIN patients p ON r.patient_id = p.id
        LEFT JOIN medecin m ON r.medecin_id = m.id
        {where}
        ORDER BY r.date_heure_rdv
    """, params)
    return cursor.fetchall()


@router.get("/{rdv_id}")
def get_rendez_vous_detail(rdv_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT r.id, r.patient_id, r.medecin_id, r.date_heure_rdv, r.motif, r.statut, r.notes,
               p.nom, p.prenom, m.nom AS medecin_nom
        FROM rendez_vous r
        LEFT JOIN patients p ON r.patient_id = p.id
        LEFT JOIN medecin m ON r.medecin_id = m.id
        WHERE r.id = %s
    """, (rdv_id,))
    rdv = cursor.fetchone()
    if not rdv:
        raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")
    return rdv


@router.post("/")
def create_rendez_vous(data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["patient_id", "date_heure_rdv"])
    statut = data.get("statut", "en_attente")
    if statut not in STATUTS_VALIDES:
        raise HTTPException(status_code=400, detail=f"Statut invalide. Valeurs autorisées : {', '.join(STATUTS_VALIDES)}")
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
        "statut": statut,
        "notes": data.get("notes"),
        "date_creation": datetime.utcnow().isoformat(),
    })
    db.commit()
    return {"message": "Rendez-vous créé", "id": cursor.fetchone()["id"]}


@router.put("/{rdv_id}")
def update_rendez_vous(rdv_id: int, data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["patient_id", "date_heure_rdv"])
    statut = data.get("statut", "en_attente")
    if statut not in STATUTS_VALIDES:
        raise HTTPException(status_code=400, detail=f"Statut invalide. Valeurs autorisées : {', '.join(STATUTS_VALIDES)}")
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
        "patient_id": data["patient_id"],
        "medecin_id": data.get("medecin_id"),
        "date_heure_rdv": data["date_heure_rdv"],
        "motif": data.get("motif"),
        "statut": statut,
        "notes": data.get("notes"),
        "id": rdv_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")
    db.commit()
    return {"message": "Rendez-vous mis à jour"}


@router.patch("/{rdv_id}/statut")
def update_statut_rendez_vous(rdv_id: int, data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["statut"])
    if data["statut"] not in STATUTS_VALIDES:
        raise HTTPException(status_code=400, detail=f"Statut invalide. Valeurs autorisées : {', '.join(STATUTS_VALIDES)}")
    cursor = db.cursor()
    cursor.execute("UPDATE rendez_vous SET statut = %s WHERE id = %s", (data["statut"], rdv_id))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")
    db.commit()
    return {"message": "Statut mis à jour"}


@router.delete("/{rdv_id}")
def delete_rendez_vous(rdv_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM rendez_vous WHERE id = %s", (rdv_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")
    db.commit()
    return {"message": "Rendez-vous supprimé"}
