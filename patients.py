from fastapi import APIRouter, Depends
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/patients", tags=["Patients"])

@router.get("/")
def get_patients(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, nom, prenom, age, sexe, telephone, adresse,
               date_enregistrement, profession, ethnie
        FROM patients
        WHERE supprime = 0 OR supprime IS NULL
        ORDER BY nom, prenom
    """)
    return cursor.fetchall()

@router.get("/{patient_id}")
def get_patient(patient_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM patients WHERE id = %s", (patient_id,))
    return cursor.fetchone()

@router.post("/")
def create_patient(patient: dict, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO patients (date_enregistrement, nom, prenom, age, sexe,
                             telephone, adresse, profession, ethnie)
        VALUES (%(date_enregistrement)s, %(nom)s, %(prenom)s, %(age)s, %(sexe)s,
                %(telephone)s, %(adresse)s, %(profession)s, %(ethnie)s)
        RETURNING id
    """, patient)
    db.commit()
    return {"message": "Patient créé", "id": cursor.fetchone()["id"]}
