from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from auth import get_current_user, require_role
from validation import require_fields
from audit_log import log_audit
from repartition import calculer_et_enregistrer_repartition

router = APIRouter(prefix="/soins", tags=["Soins"])


def inserer_soin(cursor, soin_data, ordonnance_id=None):
    """Insère une ligne dans la table soins et retourne son id.
    Réutilisé par la création directe (POST /soins) et par la saisie groupée
    depuis le formulaire Ordonnance (api/ordonnances.py)."""
    cursor.execute("""
        INSERT INTO soins (type_soin_id, patient_id, nom_patient_externe, prix_applique, date_soin, notes, ordonnance_id, type_de_soins, montant_total)
        VALUES (%(type_soin_id)s, %(patient_id)s, %(nom_patient_externe)s, %(prix_applique)s, %(date_soin)s, %(notes)s, %(ordonnance_id)s, '', 0)
        RETURNING id
    """, {
        "type_soin_id": soin_data["type_soin_id"],
        "patient_id": soin_data.get("patient_id"),
        "nom_patient_externe": soin_data.get("nom_patient_externe"),
        "prix_applique": soin_data["prix_applique"],
        "date_soin": soin_data["date_soin"],
        "notes": soin_data.get("notes"),
        "ordonnance_id": ordonnance_id,
    })
    return cursor.fetchone()["id"]


@router.get("/")
def get_soins(
    type_patient: str = None,
    date_debut: str = None,
    date_fin: str = None,
    ordonnance_id: int = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Retourne tous les soins avec filtres optionnels.
    type_patient : 'enregistre' | 'externe' | None (tous)
    """
    cursor = db.cursor()
    conditions = []
    params = {}
    if type_patient == "enregistre":
        conditions.append("s.patient_id IS NOT NULL")
    elif type_patient == "externe":
        conditions.append("s.patient_id IS NULL")
    if date_debut:
        conditions.append("s.date_soin >= %(date_debut)s")
        params["date_debut"] = date_debut
    if date_fin:
        conditions.append("s.date_soin <= %(date_fin)s")
        params["date_fin"] = date_fin
    if ordonnance_id:
        conditions.append("s.ordonnance_id = %(ordonnance_id)s")
        params["ordonnance_id"] = ordonnance_id
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    cursor.execute(f"""
        SELECT s.id, s.date_soin, s.prix_applique, s.notes, s.paye,
               s.patient_id, s.nom_patient_externe, s.ordonnance_id,
               p.nom AS patient_nom, p.prenom AS patient_prenom,
               ts.id AS type_soin_id, ts.nom AS type_soin_nom, ts.prix_defaut
        FROM soins s
        LEFT JOIN patients p ON s.patient_id = p.id
        LEFT JOIN type_soin ts ON s.type_soin_id = ts.id
        {where}
        ORDER BY s.date_soin DESC, s.id DESC
    """, params)
    return cursor.fetchall()


@router.get("/{soin_id}")
def get_soin(soin_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT s.id, s.date_soin, s.prix_applique, s.notes,
               s.patient_id, s.nom_patient_externe,
               p.nom AS patient_nom, p.prenom AS patient_prenom,
               ts.id AS type_soin_id, ts.nom AS type_soin_nom, ts.prix_defaut
        FROM soins s
        LEFT JOIN patients p ON s.patient_id = p.id
        LEFT JOIN type_soin ts ON s.type_soin_id = ts.id
        WHERE s.id = %s
    """, (soin_id,))
    soin = cursor.fetchone()
    if not soin:
        raise HTTPException(status_code=404, detail="Soin non trouvé")
    return soin


@router.post("/")
def create_soin(data: dict, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["type_soin_id", "date_soin", "prix_applique"])
    patient_id = data.get("patient_id")
    nom_patient_externe = data.get("nom_patient_externe")
    if not patient_id and not nom_patient_externe:
        raise HTTPException(status_code=400, detail="Patient enregistré ou nom du patient externe requis")
    cursor = db.cursor()
    new_id = inserer_soin(cursor, data)
    db.commit()
    log_audit(db, request, user, "CREATE", "soins", new_id, data)
    return {"message": "Soin enregistré", "id": new_id}


@router.put("/{soin_id}")
def update_soin(soin_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["type_soin_id", "date_soin", "prix_applique"])
    patient_id = data.get("patient_id")
    nom_patient_externe = data.get("nom_patient_externe")
    if not patient_id and not nom_patient_externe:
        raise HTTPException(status_code=400, detail="Patient enregistré ou nom du patient externe requis")
    cursor = db.cursor()
    cursor.execute("""
        UPDATE soins
        SET type_soin_id = %(type_soin_id)s,
            patient_id = %(patient_id)s,
            nom_patient_externe = %(nom_patient_externe)s,
            prix_applique = %(prix_applique)s,
            date_soin = %(date_soin)s,
            notes = %(notes)s
        WHERE id = %(id)s
    """, {
        "type_soin_id": data["type_soin_id"],
        "patient_id": patient_id,
        "nom_patient_externe": nom_patient_externe,
        "prix_applique": data["prix_applique"],
        "date_soin": data["date_soin"],
        "notes": data.get("notes"),
        "id": soin_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Soin non trouvé")
    db.commit()
    log_audit(db, request, user, "UPDATE", "soins", soin_id, data)
    return {"message": "Soin mis à jour"}


@router.delete("/{soin_id}")
def delete_soin(soin_id: int, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM soins WHERE id = %s", (soin_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Soin non trouvé")
    db.commit()
    log_audit(db, request, user, "DELETE", "soins", soin_id, None)
    return {"message": "Soin supprimé"}


@router.post("/{soin_id}/encaisser")
def encaisser_soin(soin_id: int, request: Request, db=Depends(get_db), user=Depends(require_role("admin", "secretaire"))):
    cursor = db.cursor()
    cursor.execute("""
        SELECT s.id, s.prix_applique, s.paye, s.nom_patient_externe, s.date_soin,
               p.nom, p.prenom, ts.nom AS type_soin_nom
        FROM soins s
        LEFT JOIN patients p ON s.patient_id = p.id
        LEFT JOIN type_soin ts ON s.type_soin_id = ts.id
        WHERE s.id = %s
    """, (soin_id,))
    soin = cursor.fetchone()
    if not soin:
        raise HTTPException(status_code=404, detail="Soin non trouvé")
    if soin["paye"]:
        raise HTTPException(status_code=400, detail="Soin déjà encaissé")
    cursor.execute("UPDATE soins SET paye = true WHERE id = %s", (soin_id,))
    calculer_et_enregistrer_repartition(db, "soin", soin_id, float(soin["prix_applique"]), soin["date_soin"])
    db.commit()
    log_audit(db, request, user, "ENCAISSER", "soins", soin_id, None)
    patient_nom = f"{soin['nom'] or ''} {soin['prenom'] or ''}".strip() or soin["nom_patient_externe"] or "-"
    return {
        "message": "Soin encaissé",
        "montant": float(soin["prix_applique"]),
        "soin": {"id": soin["id"], "patient_nom": patient_nom, "libelle": soin["type_soin_nom"] or "Soin"},
    }
