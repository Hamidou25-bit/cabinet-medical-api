from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from auth import get_current_user, require_role
from validation import require_fields
from audit_log import log_audit
from repartition import calculer_et_enregistrer_repartition
from stock_utils import consommer_stock

router = APIRouter(prefix="/examens-complementaires", tags=["Examens complémentaires"])


@router.get("/")
def get_examens(statut: str = None, db=Depends(get_db), user=Depends(get_current_user)):
    """Liste les examens. `statut` accepte une ou plusieurs valeurs séparées par des virgules
    (ex. ?statut=prescrit,en_cours), utile pour la liste de travail du laborantin."""
    cursor = db.cursor()
    where_clause = ""
    params = {}
    if statut:
        valeurs = [v.strip() for v in statut.split(",") if v.strip()]
        if valeurs:
            where_clause = "WHERE e.statut = ANY(%(statuts)s)"
            params["statuts"] = valeurs
    cursor.execute(f"""
        SELECT e.id, e.date_examen, e.resultat, e.prix, e.paye, e.patient_id,
               e.nom_patient_externe,
               e.sous_type_examen_id, e.article_stock_id, e.medecin_id, e.date_creation,
               e.renseignement_clinique,
               e.statut, e.prescripteur_id, e.date_resultat, e.fait_par_id,
               p.nom, p.prenom,
               COALESCE(ste.nom, sa."Designation") AS examen_nom,
               COALESCE(te.nom, CASE WHEN e.article_stock_id IS NOT NULL THEN 'Laboratoire' END) AS type_nom,
               m.nom AS medecin_nom
        FROM examens_complementaires e
        LEFT JOIN patients p ON e.patient_id = p.id
        LEFT JOIN sous_type_examen ste ON e.sous_type_examen_id = ste.id
        LEFT JOIN type_examen te ON ste.type_examen_id = te.id
        LEFT JOIN stock sa ON e.article_stock_id = sa."idStock"
        LEFT JOIN medecin m ON e.medecin_id = m.id
        {where_clause}
        ORDER BY e.date_examen DESC, e.id DESC
    """, params)
    return cursor.fetchall()


@router.get("/{examen_id}")
def get_examen(examen_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT e.*, p.nom, p.prenom,
               COALESCE(ste.nom, sa."Designation") AS examen_nom,
               COALESCE(te.nom, CASE WHEN e.article_stock_id IS NOT NULL THEN 'Laboratoire' END) AS type_nom,
               m.nom AS medecin_nom
        FROM examens_complementaires e
        LEFT JOIN patients p ON e.patient_id = p.id
        LEFT JOIN sous_type_examen ste ON e.sous_type_examen_id = ste.id
        LEFT JOIN type_examen te ON ste.type_examen_id = te.id
        LEFT JOIN stock sa ON e.article_stock_id = sa."idStock"
        LEFT JOIN medecin m ON e.medecin_id = m.id
        WHERE e.id = %s
    """, (examen_id,))
    examen = cursor.fetchone()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen non trouvé")
    return examen


@router.post("/")
def create_examen(data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin", "medecin", "secretaire", "laborantin"))):
    require_fields(data, ["date_examen"])
    patient_id = data.get("patient_id")
    nom_patient_externe = data.get("nom_patient_externe")
    if not patient_id and not nom_patient_externe:
        raise HTTPException(status_code=400, detail="Patient enregistré ou nom du patient externe requis")
    cursor = db.cursor()
    article_stock_id = _resoudre_type_examen(data, cursor)
    cursor.execute("""
        INSERT INTO examens_complementaires (patient_id, nom_patient_externe, sous_type_examen_id,
                                              article_stock_id, date_examen, prix, medecin_id, date_creation,
                                              renseignement_clinique, statut, prescripteur_id)
        VALUES (%(patient_id)s, %(nom_patient_externe)s, %(sous_type_examen_id)s, %(article_stock_id)s,
                %(date_examen)s, %(prix)s, %(medecin_id)s, %(date_creation)s,
                %(renseignement_clinique)s, 'prescrit', %(prescripteur_id)s)
        RETURNING id
    """, {
        "patient_id": patient_id,
        "nom_patient_externe": nom_patient_externe,
        "sous_type_examen_id": data.get("sous_type_examen_id"),
        "article_stock_id": article_stock_id,
        "date_examen": data["date_examen"],
        "prix": data.get("prix", 0),
        "medecin_id": data.get("medecin_id"),
        "date_creation": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "renseignement_clinique": data.get("renseignement_clinique"),
        "prescripteur_id": user["id"],
    })
    db.commit()
    new_id = cursor.fetchone()["id"]
    log_audit(db, request, user, "CREATE", "examens_complementaires", new_id, data)

    # Consommation automatique du stock labo : décrémente quantite_examen et trace
    # le mouvement. Un échec (ex: stock insuffisant) n'annule JAMAIS la création de
    # l'examen — signalé en avertissement uniquement (même philosophie que l'ancien
    # comportement frontend, où la sortie était un appel séparé après création).
    avertissements = _consommer_articles_lies(
        db, request, user, new_id, data.get("sous_type_examen_id"), patient_id,
        article_stock_id=article_stock_id,
    )
    return {"message": "Examen créé", "id": new_id, "avertissements": avertissements}


def _resoudre_type_examen(data, cursor):
    """Un examen référence son type soit par article_stock_id (Laboratoire : l'article
    du Services Laboratoire EST le type d'examen), soit par sous_type_examen_id
    (Imagerie, et anciens examens Laboratoire). Exactement l'un des deux est requis.
    Valide l'article et retourne article_stock_id (ou None si flux sous_type)."""
    article_stock_id = data.get("article_stock_id")
    if not article_stock_id and not data.get("sous_type_examen_id"):
        raise HTTPException(status_code=400, detail="Type d'examen requis (article_stock_id ou sous_type_examen_id)")
    if article_stock_id:
        try:
            article_stock_id = int(article_stock_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="article_stock_id doit être un entier")
        cursor.execute("""SELECT "idStock" FROM stock WHERE "idStock" = %s AND categorie = 'consommable_laboratoire'""",
                       (article_stock_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=400, detail="Article introuvable dans le Services Laboratoire")
    return article_stock_id


def _consommer_articles_lies(db, request, user, examen_id, sous_type_examen_id, patient_id, article_stock_id=None):
    """Sortie de stock automatique à la création d'un examen. Nouveau flux Laboratoire :
    l'article choisi comme type (article_stock_id) est directement l'article à décrémenter.
    Ancien flux (sous_type_examen_id) : articles liés via stock.sous_type_examen_id.
    Chaque article est consommé dans sa propre transaction : un échec sur l'un
    ne bloque pas les autres. Retourne la liste des avertissements (vide si OK)."""
    avertissements = []
    cursor = db.cursor()
    if article_stock_id:
        cursor.execute("""
            SELECT "idStock", "Designation", quantite_examen
            FROM stock WHERE "idStock" = %s
        """, (article_stock_id,))
    else:
        cursor.execute("""
            SELECT "idStock", "Designation", quantite_examen
            FROM stock
            WHERE sous_type_examen_id = %s AND categorie = 'consommable_laboratoire'
        """, (sous_type_examen_id,))
    articles = cursor.fetchall()
    for a in articles:
        quantite = max(1, round(float(a["quantite_examen"] or 1)))
        try:
            article, mouvement, nouvelle_quantite = consommer_stock(
                cursor, a["idStock"], quantite, "examen_patient", user["id"],
                patient_id=patient_id, examen_id=examen_id,
            )
            db.commit()
            log_audit(db, request, user, "CONSOMMER", "stock", a["idStock"], {
                "mouvement_id": mouvement["id"],
                "designation": article["Designation"],
                "quantite": quantite,
                "type_sortie": "examen_patient",
                "patient_id": patient_id,
                "examen_id": examen_id,
                "nouvelle_quantite": nouvelle_quantite,
                "origine": "creation_examen_auto",
            })
        except HTTPException as e:
            db.rollback()
            avertissements.append(f"Sortie de stock non appliquée pour '{a['Designation']}' : {e.detail}")
    return avertissements


@router.put("/{examen_id}")
def update_examen(examen_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin", "medecin", "secretaire"))):
    require_fields(data, ["date_examen"])
    patient_id = data.get("patient_id")
    nom_patient_externe = data.get("nom_patient_externe")
    if not patient_id and not nom_patient_externe:
        raise HTTPException(status_code=400, detail="Patient enregistré ou nom du patient externe requis")
    cursor = db.cursor()
    article_stock_id = _resoudre_type_examen(data, cursor)
    cursor.execute("""
        UPDATE examens_complementaires
        SET patient_id = %(patient_id)s,
            nom_patient_externe = %(nom_patient_externe)s,
            sous_type_examen_id = %(sous_type_examen_id)s,
            article_stock_id = %(article_stock_id)s,
            date_examen = %(date_examen)s,
            prix = %(prix)s,
            medecin_id = %(medecin_id)s,
            renseignement_clinique = %(renseignement_clinique)s
        WHERE id = %(id)s
    """, {
        "patient_id": patient_id,
        "nom_patient_externe": nom_patient_externe,
        "sous_type_examen_id": data.get("sous_type_examen_id") if not article_stock_id else None,
        "article_stock_id": article_stock_id,
        "date_examen": data["date_examen"],
        "prix": data.get("prix", 0),
        "medecin_id": data.get("medecin_id"),
        "renseignement_clinique": data.get("renseignement_clinique"),
        "id": examen_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Examen non trouvé")
    db.commit()
    log_audit(db, request, user, "UPDATE", "examens_complementaires", examen_id, data)
    return {"message": "Examen mis à jour"}


@router.delete("/{examen_id}")
def delete_examen(examen_id: int, request: Request, db=Depends(get_db), user=Depends(require_role("admin", "medecin", "secretaire"))):
    cursor = db.cursor()
    cursor.execute("DELETE FROM examens_complementaires WHERE id = %s", (examen_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Examen non trouvé")
    db.commit()
    log_audit(db, request, user, "DELETE", "examens_complementaires", examen_id, None)
    return {"message": "Examen supprimé"}


@router.patch("/{examen_id}/statut")
def update_statut_examen(examen_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin", "laborantin"))):
    require_fields(data, ["statut"])
    cursor = db.cursor()
    cursor.execute(
        "UPDATE examens_complementaires SET statut = %s WHERE id = %s",
        (data["statut"], examen_id)
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Examen non trouvé")
    db.commit()
    log_audit(db, request, user, "UPDATE_STATUT", "examens_complementaires", examen_id, {"statut": data["statut"]})
    return {"message": "Statut mis à jour"}


@router.patch("/{examen_id}/resultat")
def update_resultat_examen(examen_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin", "laborantin"))):
    require_fields(data, ["resultat"])
    cursor = db.cursor()
    cursor.execute("""
        UPDATE examens_complementaires
        SET resultat = %(resultat)s,
            date_resultat = %(date_resultat)s,
            fait_par_id = %(fait_par_id)s,
            statut = 'termine'
        WHERE id = %(id)s
    """, {
        "resultat": data["resultat"],
        "date_resultat": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "fait_par_id": user["id"],
        "id": examen_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Examen non trouvé")
    db.commit()
    log_audit(db, request, user, "UPDATE_RESULTAT", "examens_complementaires", examen_id, None)
    return {"message": "Résultat enregistré"}


@router.post("/{examen_id}/encaisser")
def encaisser_examen(examen_id: int, request: Request, db=Depends(get_db), user=Depends(require_role("admin", "secretaire"))):
    cursor = db.cursor()
    cursor.execute("""
        SELECT e.id, e.prix, e.paye, e.nom_patient_externe, e.medecin_id, e.fait_par_id, e.date_examen,
               p.nom, p.prenom, COALESCE(ste.nom, sa."Designation") AS examen_nom
        FROM examens_complementaires e
        LEFT JOIN patients p ON e.patient_id = p.id
        LEFT JOIN sous_type_examen ste ON e.sous_type_examen_id = ste.id
        LEFT JOIN stock sa ON e.article_stock_id = sa."idStock"
        WHERE e.id = %s
    """, (examen_id,))
    examen = cursor.fetchone()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen non trouvé")
    if examen["paye"]:
        raise HTTPException(status_code=400, detail="Examen déjà encaissé")
    cursor.execute("UPDATE examens_complementaires SET paye = true WHERE id = %s", (examen_id,))
    calculer_et_enregistrer_repartition(
        db, "examen", examen_id, float(examen["prix"]), examen["date_examen"],
        medecin_id=examen["medecin_id"], laborantin_id=examen["fait_par_id"],
    )
    db.commit()
    log_audit(db, request, user, "ENCAISSER", "examens_complementaires", examen_id, None)
    patient_nom = f"{examen['nom'] or ''} {examen['prenom'] or ''}".strip() or examen["nom_patient_externe"] or "-"
    return {
        "message": "Examen encaissé",
        "montant": examen["prix"],
        "examen": {"id": examen["id"], "patient_nom": patient_nom, "libelle": examen["examen_nom"] or "Examen"},
    }
