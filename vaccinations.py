from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user
from validation import require_fields

router = APIRouter(prefix="/vaccinations", tags=["Vaccinations"])


@router.get("/")
def get_vaccinations(patient_id: int = None, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    if patient_id:
        cursor.execute("""
            SELECT id, patient_id, vaccin, date_administration, dose, prochain_rappel, observations
            FROM vaccinations
            WHERE patient_id = %s
            ORDER BY date_administration DESC, id DESC
        """, (patient_id,))
    else:
        cursor.execute("""
            SELECT v.id, v.patient_id, v.vaccin, v.date_administration, v.dose, v.prochain_rappel, v.observations,
                   p.nom, p.prenom
            FROM vaccinations v
            LEFT JOIN patients p ON v.patient_id = p.id
            ORDER BY v.date_administration DESC, v.id DESC
        """)
    return cursor.fetchall()


@router.post("/")
def create_vaccination(data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["patient_id", "vaccin", "date_administration"])
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO vaccinations (patient_id, vaccin, date_administration, dose, prochain_rappel, observations)
        VALUES (%(patient_id)s, %(vaccin)s, %(date_administration)s, %(dose)s, %(prochain_rappel)s, %(observations)s)
        RETURNING id
    """, {
        "patient_id": data["patient_id"],
        "vaccin": data["vaccin"],
        "date_administration": data["date_administration"],
        "dose": data.get("dose"),
        "prochain_rappel": data.get("prochain_rappel"),
        "observations": data.get("observations"),
    })
    db.commit()
    return {"message": "Vaccination enregistrée", "id": cursor.fetchone()["id"]}


@router.put("/{vaccination_id}")
def update_vaccination(vaccination_id: int, data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["patient_id", "vaccin", "date_administration"])
    cursor = db.cursor()
    cursor.execute("""
        UPDATE vaccinations
        SET patient_id = %(patient_id)s,
            vaccin = %(vaccin)s,
            date_administration = %(date_administration)s,
            dose = %(dose)s,
            prochain_rappel = %(prochain_rappel)s,
            observations = %(observations)s
        WHERE id = %(id)s
    """, {
        "patient_id": data["patient_id"],
        "vaccin": data["vaccin"],
        "date_administration": data["date_administration"],
        "dose": data.get("dose"),
        "prochain_rappel": data.get("prochain_rappel"),
        "observations": data.get("observations"),
        "id": vaccination_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Vaccination non trouvée")
    db.commit()
    return {"message": "Vaccination mise à jour"}


@router.delete("/{vaccination_id}")
def delete_vaccination(vaccination_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM vaccinations WHERE id = %s", (vaccination_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Vaccination non trouvée")
    db.commit()
    return {"message": "Vaccination supprimée"}
