import calendar
from datetime import date
from fastapi import APIRouter, Depends
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/comptabilite", tags=["Comptabilité"])


@router.get("/synthese")
def get_synthese(date_debut: str = None, date_fin: str = None, db=Depends(get_db), user=Depends(get_current_user)):
    if not date_debut or not date_fin:
        today = date.today()
        date_debut = date(today.year, today.month, 1).isoformat()
        dernier_jour = calendar.monthrange(today.year, today.month)[1]
        date_fin = date(today.year, today.month, dernier_jour).isoformat()

    cursor = db.cursor()
    params = {"debut": date_debut, "fin": date_fin}

    cursor.execute("""
        SELECT COALESCE(SUM(montant_total), 0) AS total
        FROM consultations
        WHERE date_consult BETWEEN %(debut)s AND %(fin)s
    """, params)
    recettes_consultations = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COALESCE(SUM(lo.montant), 0) AS total
        FROM ligne_ordonnance lo
        JOIN ordonnance o ON o.id = lo.ordonnance_id
        WHERE o.type_beneficiaire IN ('patient', 'tiers')
          AND o.est_validee = 1
          AND lo.stock_id IS NOT NULL
          AND lo.date_ordonnance BETWEEN %(debut)s AND %(fin)s
    """, params)
    recettes_ordonnances = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COALESCE(SUM(montant_total), 0) AS total
        FROM soins
        WHERE date_soin BETWEEN %(debut)s AND %(fin)s
    """, params)
    recettes_soins = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COALESCE(SUM(prix), 0) AS total
        FROM examens_complementaires
        WHERE date_examen BETWEEN %(debut)s AND %(fin)s
    """, params)
    recettes_examens = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COALESCE(SUM(montant), 0) AS total
        FROM depense
        WHERE date_depense BETWEEN %(debut)s AND %(fin)s
          AND type_depense = 'Achats Fournisseurs'
    """, params)
    depenses_achats_fournisseurs = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COALESCE(SUM(montant), 0) AS total
        FROM depense
        WHERE date_depense BETWEEN %(debut)s AND %(fin)s
          AND type_depense != 'Achats Fournisseurs'
    """, params)
    depenses_autres = cursor.fetchone()["total"]

    depenses_total = depenses_achats_fournisseurs + depenses_autres
    recettes_total = recettes_consultations + recettes_ordonnances + recettes_soins + recettes_examens

    cursor.execute("""
        SELECT mois, SUM(montant) AS recettes
        FROM (
            SELECT SUBSTRING(date_consult, 1, 7) AS mois, montant_total AS montant
            FROM consultations
            WHERE date_consult BETWEEN %(debut)s AND %(fin)s
            UNION ALL
            SELECT SUBSTRING(lo.date_ordonnance, 1, 7), lo.montant
            FROM ligne_ordonnance lo
            JOIN ordonnance o ON o.id = lo.ordonnance_id
            WHERE o.type_beneficiaire IN ('patient', 'tiers')
              AND o.est_validee = 1
              AND lo.stock_id IS NOT NULL
              AND lo.date_ordonnance BETWEEN %(debut)s AND %(fin)s
            UNION ALL
            SELECT SUBSTRING(date_soin, 1, 7), montant_total
            FROM soins
            WHERE date_soin BETWEEN %(debut)s AND %(fin)s
            UNION ALL
            SELECT SUBSTRING(date_examen, 1, 7), prix
            FROM examens_complementaires
            WHERE date_examen BETWEEN %(debut)s AND %(fin)s
        ) recettes_par_mois
        GROUP BY mois
    """, params)
    recettes_par_mois = {row["mois"]: row["recettes"] for row in cursor.fetchall()}

    cursor.execute("""
        SELECT SUBSTRING(date_depense, 1, 7) AS mois, SUM(montant) AS depenses
        FROM depense
        WHERE date_depense BETWEEN %(debut)s AND %(fin)s
        GROUP BY mois
    """, params)
    depenses_par_mois = {row["mois"]: row["depenses"] for row in cursor.fetchall()}

    mois = sorted(set(recettes_par_mois) | set(depenses_par_mois))
    evolution = [
        {
            "mois": m,
            "recettes": recettes_par_mois.get(m, 0),
            "depenses": depenses_par_mois.get(m, 0),
            "profit": recettes_par_mois.get(m, 0) - depenses_par_mois.get(m, 0),
        }
        for m in mois
    ]

    return {
        "periode": {"date_debut": date_debut, "date_fin": date_fin},
        "recettes": {
            "total": recettes_total,
            "detail": {
                "consultations": recettes_consultations,
                "ordonnances": recettes_ordonnances,
                "soins": recettes_soins,
                "examens": recettes_examens,
            },
        },
        "depenses": {
            "total": depenses_total,
            "detail": {
                "achats_fournisseurs": depenses_achats_fournisseurs,
                "autres": depenses_autres,
            },
        },
        "profit": recettes_total - depenses_total,
        "evolution": evolution,
    }
