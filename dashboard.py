import calendar
from datetime import date, timedelta
from fastapi import APIRouter, Depends
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _recettes_periode(cursor, debut, fin):
    cursor.execute("""
        SELECT
            (SELECT COALESCE(SUM(montant_total), 0) FROM consultations WHERE date_consult BETWEEN %(debut)s AND %(fin)s) +
            (SELECT COALESCE(SUM(lo.montant), 0) FROM ligne_ordonnance lo
                JOIN ordonnance o ON o.id = lo.ordonnance_id
                WHERE o.type_beneficiaire IN ('patient', 'tiers') AND o.est_validee = 1
                  AND lo.stock_id IS NOT NULL AND o.date_ordonnance BETWEEN %(debut)s AND %(fin)s) +
            (SELECT COALESCE(SUM(prix_applique), 0) FROM soins WHERE date_soin BETWEEN %(debut)s AND %(fin)s) +
            (SELECT COALESCE(SUM(prix), 0) FROM examens_complementaires WHERE date_examen BETWEEN %(debut)s AND %(fin)s)
            AS total
    """, {"debut": debut, "fin": fin})
    return float(cursor.fetchone()["total"] or 0)


@router.get("/statistiques")
def get_statistiques(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    today = date.today()

    debut_mois = date(today.year, today.month, 1)
    fin_mois = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    jour_avant = debut_mois - timedelta(days=1)
    debut_mois_prec = date(jour_avant.year, jour_avant.month, 1)
    fin_mois_prec = date(jour_avant.year, jour_avant.month, calendar.monthrange(jour_avant.year, jour_avant.month)[1])

    revenus_mois = _recettes_periode(cursor, debut_mois.isoformat(), fin_mois.isoformat())
    revenus_mois_precedent = _recettes_periode(cursor, debut_mois_prec.isoformat(), fin_mois_prec.isoformat())
    variation_pct = (
        round((revenus_mois - revenus_mois_precedent) / revenus_mois_precedent * 100, 1)
        if revenus_mois_precedent else None
    )

    cursor.execute("""
        SELECT diagnostic, COUNT(*) AS nb
        FROM consultations
        WHERE diagnostic IS NOT NULL AND diagnostic <> ''
        GROUP BY diagnostic
        ORDER BY nb DESC
        LIMIT 5
    """)
    top_pathologies = cursor.fetchall()

    cursor.execute("""
        SELECT designation, SUM(quantite) AS quantite_totale
        FROM ligne_ordonnance
        WHERE designation IS NOT NULL AND designation <> ''
        GROUP BY designation
        ORDER BY quantite_totale DESC
        LIMIT 5
    """)
    top_medicaments = cursor.fetchall()

    cursor.execute("""
        SELECT COUNT(*) AS nb
        FROM patients
        WHERE date_enregistrement BETWEEN %(debut)s AND %(fin)s
          AND (supprime = 0 OR supprime IS NULL)
    """, {"debut": debut_mois.isoformat(), "fin": fin_mois.isoformat()})
    nouveaux_patients = cursor.fetchone()["nb"]

    cursor.execute("""
        SELECT date_trunc('week', date_consult::date) AS semaine, COUNT(*) AS nb
        FROM consultations
        WHERE date_consult::date >= CURRENT_DATE - INTERVAL '28 days'
        GROUP BY semaine
        ORDER BY semaine
    """)
    consultations_par_semaine = [
        {"semaine": row["semaine"].date().isoformat(), "nb": row["nb"]}
        for row in cursor.fetchall()
    ]

    return {
        "revenus": {
            "mois_courant": revenus_mois,
            "mois_precedent": revenus_mois_precedent,
            "variation_pct": variation_pct,
        },
        "nouveaux_patients_mois": nouveaux_patients,
        "top_pathologies": top_pathologies,
        "top_medicaments": top_medicaments,
        "consultations_par_semaine": consultations_par_semaine,
    }


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
