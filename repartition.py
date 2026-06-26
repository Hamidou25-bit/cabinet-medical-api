import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import get_current_user, require_role
from database import get_db
from validation import require_fields

router = APIRouter(prefix="/repartition", tags=["Répartition"])

TYPES_ACTE_PERSONNALISABLES = ("consultation", "examen")


def calculer_et_enregistrer_repartition(
    db,
    reference_type: str,
    reference_id: int,
    montant_total: float,
    date_acte,
    medecin_id: int | None = None,
    laborantin_id: int | None = None,
):
    """Calcule la répartition cabinet/médecin/laborantin d'un encaissement et
    l'enregistre dans repartition_recettes (snapshot des taux appliqués).
    Doit être appelée avant db.commit() de la route d'encaissement appelante,
    pour que la répartition soit annulée si l'encaissement échoue."""
    cur = db.cursor()

    if reference_type in ("soin", "ordonnance"):
        # Décision produit : soins et ordonnances reviennent intégralement au
        # cabinet (pas de medecin_id sur soins ; marge ordonnances suivie à part).
        taux_cabinet, taux_medecin, taux_laborantin = 100, 0, 0
    elif reference_type == "consultation":
        # Sans medecin_id, personne n'a droit à une part : tout revient au cabinet
        # plutôt que de figer une part "médecin" orpheline, impossible à verser.
        taux_medecin = 0
        if medecin_id:
            cur.execute("""
                SELECT cle, valeur FROM parametres_cabinet WHERE cle = 'taux_medecin_consultation'
            """)
            row = cur.fetchone()
            taux_medecin = float(row["valeur"]) if row else 50
            cur.execute("""
                SELECT taux_personnel FROM taux_personnalises
                WHERE type_acte = 'consultation' AND cible_id = %s AND actif = TRUE
            """, (medecin_id,))
            perso = cur.fetchone()
            if perso:
                taux_medecin = float(perso["taux_personnel"])
        taux_cabinet = 100 - taux_medecin
        taux_laborantin = 0
    elif reference_type == "examen":
        taux_medecin = 0
        if medecin_id:
            cur.execute("""
                SELECT valeur FROM parametres_cabinet WHERE cle = 'taux_medecin_examen'
            """)
            row = cur.fetchone()
            taux_medecin = float(row["valeur"]) if row else 20

        taux_laborantin = 0
        if laborantin_id:
            cur.execute("""
                SELECT valeur FROM parametres_cabinet WHERE cle = 'taux_laborantin_examen'
            """)
            row = cur.fetchone()
            taux_laborantin = float(row["valeur"]) if row else 30
            cur.execute("""
                SELECT taux_personnel FROM taux_personnalises
                WHERE type_acte = 'examen' AND cible_id = %s AND actif = TRUE
            """, (laborantin_id,))
            perso = cur.fetchone()
            if perso:
                taux_laborantin = float(perso["taux_personnel"])
        taux_cabinet = 100 - taux_medecin - taux_laborantin
    else:
        raise ValueError(f"reference_type inconnu: {reference_type}")

    part_cabinet = round(montant_total * taux_cabinet / 100, 2)
    part_medecin = round(montant_total * taux_medecin / 100, 2)
    part_laborantin = round(montant_total * taux_laborantin / 100, 2)

    cur.execute("""
        INSERT INTO repartition_recettes (
            reference_type, reference_id, montant_total,
            part_cabinet, part_medecin, part_laborantin,
            taux_cabinet, taux_medecin, taux_laborantin,
            medecin_id, laborantin_id, date_acte
        ) VALUES (
            %(reference_type)s, %(reference_id)s, %(montant_total)s,
            %(part_cabinet)s, %(part_medecin)s, %(part_laborantin)s,
            %(taux_cabinet)s, %(taux_medecin)s, %(taux_laborantin)s,
            %(medecin_id)s, %(laborantin_id)s, %(date_acte)s
        )
        ON CONFLICT (reference_type, reference_id) DO NOTHING
    """, {
        "reference_type": reference_type, "reference_id": reference_id, "montant_total": montant_total,
        "part_cabinet": part_cabinet, "part_medecin": part_medecin, "part_laborantin": part_laborantin,
        "taux_cabinet": taux_cabinet, "taux_medecin": taux_medecin, "taux_laborantin": taux_laborantin,
        "medecin_id": medecin_id, "laborantin_id": laborantin_id, "date_acte": date_acte,
    })

    return {
        "part_cabinet": part_cabinet,
        "part_medecin": part_medecin,
        "part_laborantin": part_laborantin,
    }


@router.get("/bilan-garde")
def get_bilan_garde(
    medecin_id: int,
    date_debut: str,
    date_fin: str,
    db=Depends(get_db),
    user=Depends(require_role("admin")),
):
    cur = db.cursor()
    cur.execute("SELECT nom FROM medecin WHERE id = %s", (medecin_id,))
    medecin = cur.fetchone()
    if not medecin:
        raise HTTPException(status_code=404, detail="Médecin non trouvé")

    cur.execute("""
        SELECT reference_type, reference_id, montant_total, part_medecin, part_cabinet,
               medecin_verse, medecin_verse_le, date_acte
        FROM repartition_recettes
        WHERE medecin_id = %s AND date_acte BETWEEN %s AND %s
        ORDER BY date_acte DESC, id DESC
    """, (medecin_id, date_debut, date_fin))
    lignes = cur.fetchall()

    par_type = {}
    for l in lignes:
        t = par_type.setdefault(l["reference_type"], {"count": 0, "total": 0.0, "part_medecin": 0.0})
        t["count"] += 1
        t["total"] += float(l["montant_total"])
        t["part_medecin"] += float(l["part_medecin"])

    return {
        "medecin_id": medecin_id,
        "medecin_nom": medecin["nom"],
        "date_debut": date_debut,
        "date_fin": date_fin,
        "total_actes": len(lignes),
        "total_encaisse": sum(float(l["montant_total"]) for l in lignes),
        "total_medecin": sum(float(l["part_medecin"]) for l in lignes),
        "total_cabinet": sum(float(l["part_cabinet"]) for l in lignes),
        "par_type": par_type,
        "lignes": lignes,
    }


@router.get("/synthese")
def get_synthese_repartition(
    date_debut: str,
    date_fin: str,
    db=Depends(get_db),
    user=Depends(require_role("admin")),
):
    cur = db.cursor()
    cur.execute("""
        SELECT reference_type, COUNT(*) AS nb_actes,
               SUM(montant_total) AS total_brut, SUM(part_cabinet) AS total_cabinet,
               SUM(part_medecin) AS total_medecins, SUM(part_laborantin) AS total_laborantins
        FROM repartition_recettes
        WHERE date_acte BETWEEN %s AND %s
        GROUP BY reference_type ORDER BY reference_type
    """, (date_debut, date_fin))
    par_type = cur.fetchall()

    cur.execute("""
        SELECT m.nom AS medecin_nom, r.medecin_id, COUNT(*) AS nb_actes,
               SUM(r.part_medecin) AS total_part, BOOL_AND(r.medecin_verse) AS tout_verse
        FROM repartition_recettes r
        JOIN medecin m ON m.id = r.medecin_id
        WHERE r.date_acte BETWEEN %s AND %s AND r.part_medecin > 0
        GROUP BY r.medecin_id, m.nom ORDER BY total_part DESC
    """, (date_debut, date_fin))
    par_medecin = cur.fetchall()

    cur.execute("""
        SELECT u.nom_complet AS laborantin_nom, r.laborantin_id, COUNT(*) AS nb_actes,
               SUM(r.part_laborantin) AS total_part, BOOL_AND(r.laborantin_verse) AS tout_verse
        FROM repartition_recettes r
        JOIN utilisateurs u ON u.id = r.laborantin_id
        WHERE r.date_acte BETWEEN %s AND %s AND r.part_laborantin > 0
        GROUP BY r.laborantin_id, u.nom_complet ORDER BY total_part DESC
    """, (date_debut, date_fin))
    par_laborantin = cur.fetchall()

    return {
        "periode": {"debut": date_debut, "fin": date_fin},
        "par_type": par_type,
        "par_medecin": par_medecin,
        "par_laborantin": par_laborantin,
    }


@router.post("/marquer-verse")
def marquer_verse(data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["type_beneficiaire", "date_debut", "date_fin"])
    beneficiaire = data["type_beneficiaire"]
    if beneficiaire not in ("medecin", "laborantin"):
        raise HTTPException(status_code=422, detail="type_beneficiaire invalide")

    cur = db.cursor()
    now = datetime.datetime.now()
    if beneficiaire == "medecin":
        require_fields(data, ["medecin_id"])
        cur.execute("""
            UPDATE repartition_recettes SET medecin_verse = TRUE, medecin_verse_le = %s
            WHERE medecin_id = %s AND date_acte BETWEEN %s AND %s AND medecin_verse = FALSE
        """, (now, data["medecin_id"], data["date_debut"], data["date_fin"]))
    else:
        require_fields(data, ["laborantin_id"])
        cur.execute("""
            UPDATE repartition_recettes SET laborantin_verse = TRUE, laborantin_verse_le = %s
            WHERE laborantin_id = %s AND date_acte BETWEEN %s AND %s AND laborantin_verse = FALSE
        """, (now, data["laborantin_id"], data["date_debut"], data["date_fin"]))

    db.commit()
    from audit_log import log_audit
    log_audit(db, request, user, "MARQUER_VERSE", "repartition_recettes", None, data)
    return {"message": "Versement enregistré", "lignes_mises_a_jour": cur.rowcount}


@router.get("/taux-personnalises")
def get_taux_personnalises(db=Depends(get_db), user=Depends(require_role("admin"))):
    cur = db.cursor()
    cur.execute("""
        SELECT t.id, t.type_acte, t.cible_id, t.taux_personnel,
               COALESCE(m.nom, u.nom_complet, u.nom_utilisateur) AS cible_nom
        FROM taux_personnalises t
        LEFT JOIN medecin m ON t.type_acte = 'consultation' AND m.id = t.cible_id
        LEFT JOIN utilisateurs u ON t.type_acte = 'examen' AND u.id = t.cible_id
        WHERE t.actif = TRUE
        ORDER BY t.type_acte, cible_nom
    """)
    return cur.fetchall()


@router.post("/taux-personnalises")
def set_taux_personnalise(data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["type_acte", "cible_id", "taux_personnel"])
    if data["type_acte"] not in TYPES_ACTE_PERSONNALISABLES:
        raise HTTPException(status_code=422, detail="type_acte invalide")
    cur = db.cursor()
    cur.execute("""
        INSERT INTO taux_personnalises (type_acte, cible_id, taux_personnel)
        VALUES (%(type_acte)s, %(cible_id)s, %(taux_personnel)s)
        ON CONFLICT (type_acte, cible_id)
        DO UPDATE SET taux_personnel = EXCLUDED.taux_personnel, actif = TRUE
    """, data)
    db.commit()
    return {"message": "Taux personnalisé enregistré"}


@router.delete("/taux-personnalises/{type_acte}/{cible_id}")
def delete_taux_personnalise(type_acte: str, cible_id: int, db=Depends(get_db), user=Depends(require_role("admin"))):
    cur = db.cursor()
    cur.execute("""
        UPDATE taux_personnalises SET actif = FALSE WHERE type_acte = %s AND cible_id = %s
    """, (type_acte, cible_id))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Taux personnalisé non trouvé")
    db.commit()
    return {"message": "Taux personnalisé supprimé"}
