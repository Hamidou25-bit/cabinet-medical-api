from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user
from validation import require_fields

router = APIRouter(prefix="/examens-complementaires", tags=["Examens complémentaires"])


@router.get("/")
def get_examens(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT e.id, e.date_examen, e.resultat, e.prix, e.patient_id,
               e.nom_patient_externe,
               e.sous_type_examen_id, e.medecin_id, e.date_creation,
               e.renseignement_clinique,
               p.nom, p.prenom,
               ste.nom AS examen_nom, te.nom AS type_nom,
               m.nom AS medecin_nom
        FROM examens_complementaires e
        LEFT JOIN patients p ON e.patient_id = p.id
        LEFT JOIN sous_type_examen ste ON e.sous_type_examen_id = ste.id
        LEFT JOIN type_examen te ON ste.type_examen_id = te.id
        LEFT JOIN medecin m ON e.medecin_id = m.id
        ORDER BY e.date_examen DESC, e.id DESC
    """)
    return cursor.fetchall()


@router.get("/{examen_id}")
def get_examen(examen_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT e.*, p.nom, p.prenom,
               ste.nom AS examen_nom, te.nom AS type_nom,
               m.nom AS medecin_nom
        FROM examens_complementaires e
        LEFT JOIN patients p ON e.patient_id = p.id
        LEFT JOIN sous_type_examen ste ON e.sous_type_examen_id = ste.id
        LEFT JOIN type_examen te ON ste.type_examen_id = te.id
        LEFT JOIN medecin m ON e.medecin_id = m.id
        WHERE e.id = %s
    """, (examen_id,))
    examen = cursor.fetchone()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen non trouvé")
    return examen


@router.post("/")
def create_examen(data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["sous_type_examen_id", "date_examen"])
    patient_id = data.get("patient_id")
    nom_patient_externe = data.get("nom_patient_externe")
    if not patient_id and not nom_patient_externe:
        raise HTTPException(status_code=400, detail="Patient enregistré ou nom du patient externe requis")
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO examens_complementaires (patient_id, nom_patient_externe, sous_type_examen_id,
                                              date_examen, resultat, prix, medecin_id, date_creation,
                                              renseignement_clinique)
        VALUES (%(patient_id)s, %(nom_patient_externe)s, %(sous_type_examen_id)s, %(date_examen)s,
                %(resultat)s, %(prix)s, %(medecin_id)s, %(date_creation)s,
                %(renseignement_clinique)s)
        RETURNING id
    """, {
        "patient_id": patient_id,
        "nom_patient_externe": nom_patient_externe,
        "sous_type_examen_id": data["sous_type_examen_id"],
        "date_examen": data["date_examen"],
        "resultat": data.get("resultat"),
        "prix": data.get("prix", 0),
        "medecin_id": data.get("medecin_id"),
        "date_creation": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "renseignement_clinique": data.get("renseignement_clinique"),
    })
    db.commit()
    return {"message": "Examen créé", "id": cursor.fetchone()["id"]}


@router.put("/{examen_id}")
def update_examen(examen_id: int, data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["sous_type_examen_id", "date_examen"])
    patient_id = data.get("patient_id")
    nom_patient_externe = data.get("nom_patient_externe")
    if not patient_id and not nom_patient_externe:
        raise HTTPException(status_code=400, detail="Patient enregistré ou nom du patient externe requis")
    cursor = db.cursor()
    cursor.execute("""
        UPDATE examens_complementaires
        SET patient_id = %(patient_id)s,
            nom_patient_externe = %(nom_patient_externe)s,
            sous_type_examen_id = %(sous_type_examen_id)s,
            date_examen = %(date_examen)s,
            resultat = %(resultat)s,
            prix = %(prix)s,
            medecin_id = %(medecin_id)s,
            renseignement_clinique = %(renseignement_clinique)s
        WHERE id = %(id)s
    """, {
        "patient_id": patient_id,
        "nom_patient_externe": nom_patient_externe,
        "sous_type_examen_id": data["sous_type_examen_id"],
        "date_examen": data["date_examen"],
        "resultat": data.get("resultat"),
        "prix": data.get("prix", 0),
        "medecin_id": data.get("medecin_id"),
        "renseignement_clinique": data.get("renseignement_clinique"),
        "id": examen_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Examen non trouvé")
    db.commit()
    return {"message": "Examen mis à jour"}


@router.delete("/{examen_id}")
def delete_examen(examen_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM examens_complementaires WHERE id = %s", (examen_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Examen non trouvé")
    db.commit()
    return {"message": "Examen supprimé"}
