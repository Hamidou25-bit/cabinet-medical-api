from datetime import date
from fastapi import APIRouter, Depends
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/rdv-aujourdhui")
def get_rdv_aujourdhui(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    today = date.today().isoformat()
    cursor.execute("""
        SELECT r.id, r.date_heure_rdv, r.motif, r.statut, r.patient_id,
               p.nom, p.prenom
        FROM rendez_vous r
        LEFT JOIN patients p ON r.patient_id = p.id
        WHERE r.date_heure_rdv LIKE %s AND r.statut <> 'annulé'
        ORDER BY r.date_heure_rdv
    """, (f"{today}%",))
    return cursor.fetchall()
