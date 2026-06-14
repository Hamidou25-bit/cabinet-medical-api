from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user
from validation import require_fields

router = APIRouter(prefix="/patients", tags=["Patients"])

@router.get("/")
def get_patients(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, nom, prenom, age, sexe, telephone, adresse,
               date_enregistrement, profession, ethnie, numero_dossier, email
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
    require_fields(patient, ["nom", "prenom", "age", "sexe"])
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO patients (date_enregistrement, nom, prenom, age, sexe,
                             telephone, adresse, profession, ethnie,
                             numero_dossier, email)
        VALUES (%(date_enregistrement)s, %(nom)s, %(prenom)s, %(age)s, %(sexe)s,
                %(telephone)s, %(adresse)s, %(profession)s, %(ethnie)s,
                %(numero_dossier)s, %(email)s)
        RETURNING id
    """, patient)
    db.commit()
    return {"message": "Patient créé", "id": cursor.fetchone()["id"]}


@router.put("/{patient_id}")
def update_patient(patient_id: int, patient: dict, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(patient, ["nom", "prenom", "age", "sexe"])
    cursor = db.cursor()
    cursor.execute("""
        UPDATE patients
        SET nom = %(nom)s,
            prenom = %(prenom)s,
            age = %(age)s,
            sexe = %(sexe)s,
            telephone = %(telephone)s,
            adresse = %(adresse)s,
            profession = %(profession)s,
            ethnie = %(ethnie)s,
            numero_dossier = %(numero_dossier)s,
            email = %(email)s
        WHERE id = %(id)s
    """, {
        "nom": patient["nom"],
        "prenom": patient["prenom"],
        "age": patient["age"],
        "sexe": patient["sexe"],
        "telephone": patient.get("telephone"),
        "adresse": patient.get("adresse"),
        "profession": patient.get("profession"),
        "ethnie": patient.get("ethnie"),
        "numero_dossier": patient.get("numero_dossier"),
        "email": patient.get("email"),
        "id": patient_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Patient non trouvé")
    db.commit()
    return {"message": "Patient mis à jour"}


@router.delete("/{patient_id}")
def delete_patient(patient_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("UPDATE patients SET supprime = 1 WHERE id = %s", (patient_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Patient non trouvé")
    db.commit()
    return {"message": "Patient supprimé"}
