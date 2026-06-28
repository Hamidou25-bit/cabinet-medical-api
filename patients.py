from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from auth import get_current_user
from validation import require_fields
from audit_log import log_audit

router = APIRouter(prefix="/patients", tags=["Patients"])

def _generer_numero_dossier(cursor):
    """Calcule le prochain numero_dossier au format PAT-AAAA-NNNN (séquence par année,
    poursuit la numérotation déjà en place plutôt que d'en démarrer une nouvelle)."""
    annee = datetime.utcnow().year
    prefixe = f"PAT-{annee}-"
    cursor.execute(
        "SELECT numero_dossier FROM patients WHERE numero_dossier LIKE %s ORDER BY numero_dossier DESC LIMIT 1",
        (prefixe + "%",)
    )
    row = cursor.fetchone()
    dernier_numero = int(row["numero_dossier"][len(prefixe):]) if row else 0
    return f"{prefixe}{dernier_numero + 1:04d}"

@router.get("/")
def get_patients(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT p.id, p.nom, p.prenom, p.age, p.sexe, p.telephone, p.adresse,
               p.date_enregistrement, p.profession, p.ethnie, p.numero_dossier,
               COUNT(c.id) AS nb_consultations,
               EXISTS(SELECT 1 FROM dossier_patients dp WHERE dp.patient_id = p.id) AS a_dossier
        FROM patients p
        LEFT JOIN consultations c ON c.patient_id = p.id
        WHERE p.supprime = 0 OR p.supprime IS NULL
        GROUP BY p.id
        ORDER BY p.date_enregistrement DESC, p.id DESC
    """)
    return cursor.fetchall()

@router.get("/{patient_id}")
def get_patient(patient_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM patients WHERE id = %s", (patient_id,))
    return cursor.fetchone()

@router.post("/")
def create_patient(patient: dict, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(patient, ["nom", "prenom", "age", "sexe"])
    cursor = db.cursor()
    numero_dossier = _generer_numero_dossier(cursor)
    cursor.execute("""
        INSERT INTO patients (date_enregistrement, nom, prenom, age, sexe,
                             telephone, adresse, profession, ethnie,
                             numero_dossier)
        VALUES (%(date_enregistrement)s, %(nom)s, %(prenom)s, %(age)s, %(sexe)s,
                %(telephone)s, %(adresse)s, %(profession)s, %(ethnie)s,
                %(numero_dossier)s)
        RETURNING id
    """, {**patient, "numero_dossier": numero_dossier})
    db.commit()
    new_id = cursor.fetchone()["id"]
    log_audit(db, request, user, "CREATE", "patients", new_id, {**patient, "numero_dossier": numero_dossier})
    return {"message": "Patient créé", "id": new_id, "numero_dossier": numero_dossier}


@router.put("/{patient_id}")
def update_patient(patient_id: int, patient: dict, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
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
            ethnie = %(ethnie)s
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
        "id": patient_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Patient non trouvé")
    db.commit()
    log_audit(db, request, user, "UPDATE", "patients", patient_id, patient)
    return {"message": "Patient mis à jour"}


@router.delete("/{patient_id}")
def delete_patient(patient_id: int, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("UPDATE patients SET supprime = 1 WHERE id = %s", (patient_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Patient non trouvé")
    db.commit()
    log_audit(db, request, user, "DELETE", "patients", patient_id, None)
    return {"message": "Patient supprimé"}
