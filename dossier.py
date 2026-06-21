from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/patients", tags=["Dossier patient"])


@router.get("/{patient_id}/dossier")
def get_dossier_patient(patient_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()

    cursor.execute("""
        SELECT id, nom, prenom, age, sexe, telephone, adresse,
               date_enregistrement, profession, ethnie, numero_dossier, email
        FROM patients
        WHERE id = %s AND (supprime = 0 OR supprime IS NULL)
    """, (patient_id,))
    patient = cursor.fetchone()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient non trouvé")

    cursor.execute("""
        SELECT c.id, c.date_consult, c.motif, c.diagnostic, c.observation,
               c.montant_total, m.nom AS medecin_nom
        FROM consultations c
        LEFT JOIN medecin m ON c.medecin_id = m.id
        WHERE c.patient_id = %s
        ORDER BY c.date_consult DESC, c.id DESC
    """, (patient_id,))
    consultations = cursor.fetchall()

    cursor.execute("""
        SELECT o.id, o.date_ordonnance, o.type_beneficiaire, o.est_validee
        FROM ordonnance o
        WHERE o.patient_id = %s
        ORDER BY o.date_ordonnance DESC, o.id DESC
    """, (patient_id,))
    ordonnances = cursor.fetchall()
    if ordonnances:
        ids = [o["id"] for o in ordonnances]
        cursor.execute("""
            SELECT ordonnance_id, designation, quantite, posologie, dosage, forme, montant
            FROM ligne_ordonnance
            WHERE ordonnance_id = ANY(%(ids)s)
            ORDER BY id
        """, {"ids": ids})
        lignes_par_ordonnance = {}
        for ligne in cursor.fetchall():
            lignes_par_ordonnance.setdefault(ligne["ordonnance_id"], []).append({
                "medicament": ligne["designation"],
                "quantite": ligne["quantite"],
                "posologie": ligne["posologie"],
                "dosage": ligne["dosage"],
                "forme": ligne["forme"],
                "prix_unitaire": ligne["montant"],
            })
        for o in ordonnances:
            o["lignes"] = lignes_par_ordonnance.get(o["id"], [])
            o["total"] = sum((l["prix_unitaire"] or 0) for l in o["lignes"])

    cursor.execute("""
        SELECT s.id, s.date_soin, s.prix_applique, s.notes, ts.nom AS type_soin_nom
        FROM soins s
        LEFT JOIN type_soin ts ON s.type_soin_id = ts.id
        WHERE s.patient_id = %s
        ORDER BY s.date_soin DESC, s.id DESC
    """, (patient_id,))
    soins = cursor.fetchall()

    cursor.execute("""
        SELECT e.id, e.date_examen, e.resultat, e.prix,
               ste.nom AS type_examen_nom, te.nom AS categorie_nom
        FROM examens_complementaires e
        LEFT JOIN sous_type_examen ste ON e.sous_type_examen_id = ste.id
        LEFT JOIN type_examen te ON ste.type_examen_id = te.id
        WHERE e.patient_id = %s
        ORDER BY e.date_examen DESC, e.id DESC
    """, (patient_id,))
    examens = cursor.fetchall()

    cursor.execute("""
        SELECT id, vaccin, date_administration, dose, prochain_rappel, observations
        FROM vaccinations
        WHERE patient_id = %s
        ORDER BY date_administration DESC, id DESC
    """, (patient_id,))
    vaccinations = cursor.fetchall()
    rappels_en_retard = sum(
        1 for v in vaccinations if v["prochain_rappel"] and v["prochain_rappel"] < date.today()
    )

    total_consultations = sum((c["montant_total"] or 0) for c in consultations)
    total_ordonnances = sum((o["total"] or 0) for o in ordonnances)
    total_soins = sum((s["prix_applique"] or 0) for s in soins)
    total_examens = sum((e["prix"] or 0) for e in examens)

    dates = (
        [c["date_consult"] for c in consultations]
        + [o["date_ordonnance"] for o in ordonnances]
        + [s["date_soin"] for s in soins]
        + [e["date_examen"] for e in examens]
    )
    derniere_visite = max(dates) if dates else None

    return {
        "patient": patient,
        "consultations": consultations,
        "ordonnances": ordonnances,
        "soins": soins,
        "examens": examens,
        "vaccinations": vaccinations,
        "resume": {
            "nb_consultations": len(consultations),
            "nb_ordonnances": len(ordonnances),
            "nb_soins": len(soins),
            "nb_examens": len(examens),
            "nb_vaccinations": len(vaccinations),
            "rappels_vaccination_en_retard": rappels_en_retard,
            "total_depense_patient": total_consultations + total_ordonnances + total_soins + total_examens,
            "derniere_visite": derniere_visite,
        },
    }
