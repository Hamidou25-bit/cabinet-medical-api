from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from auth import get_current_user
from validation import require_fields
from audit_log import log_audit

router = APIRouter(prefix="/ordonnances", tags=["Ordonnances"])


def _resoudre_ligne_ordonnance(cursor, ligne, type_beneficiaire="patient"):
    """Résout designation, montant et prix_achat d'une ligne d'ordonnance.
    Si stock_id est renseigné, le montant et le prix d'achat sont calculés
    à partir des prix du stock. Pour l'usage interne, le montant (utilisé pour
    le total) est basé sur le prix d'achat plutôt que le prix de vente.
    Sinon (médicament externe), les valeurs envoyées par le frontend sont
    conservées telles quelles."""
    stock_id = ligne.get("stock_id")
    designation = ligne.get("designation")
    quantite = ligne.get("quantite", 1)
    montant = ligne.get("montant", 0)
    prix_achat = ligne.get("prix_achat", 0)

    if stock_id:
        cursor.execute('SELECT "Designation", "PrixVente", "PrixAchat" FROM stock WHERE "idStock" = %s', (stock_id,))
        article = cursor.fetchone()
        if not article:
            raise HTTPException(status_code=404, detail=f"Article de stock non trouvé (id {stock_id})")
        if not designation:
            designation = article["Designation"]
        prix_achat = quantite * (article["PrixAchat"] or 0)
        montant = prix_achat if type_beneficiaire == "interne" else quantite * (article["PrixVente"] or 0)

    if not designation:
        raise HTTPException(status_code=400, detail="Champ(s) obligatoire(s) manquant(s) : designation")

    return {
        "designation": designation,
        "montant": montant,
        "prix_achat": prix_achat,
        "stock_id": stock_id,
        "quantite": quantite,
    }


def _appliquer_mouvement_stock(cursor, stock_id, quantite, delta):
    """Ajoute delta * quantite a la quantite en stock de l'article stock_id."""
    if stock_id:
        cursor.execute(
            'UPDATE stock SET "Quantite" = "Quantite" + %s WHERE "idStock" = %s',
            (delta * quantite, stock_id)
        )


def _decrementer_stock(cursor, lignes_resolues):
    """Decremente le stock pour chaque ligne liee a un article (creation/modification d'ordonnance)."""
    for ligne in lignes_resolues:
        _appliquer_mouvement_stock(cursor, ligne["stock_id"], ligne["quantite"], -1)


def _restaurer_stock_ordonnance(cursor, ordonnance_id):
    """Reincremente le stock pour les lignes existantes d'une ordonnance (avant modification/suppression)."""
    cursor.execute("SELECT stock_id, quantite FROM ligne_ordonnance WHERE ordonnance_id = %s", (ordonnance_id,))
    for ligne in cursor.fetchall():
        _appliquer_mouvement_stock(cursor, ligne["stock_id"], ligne["quantite"], 1)


def _construire_filtres_ordonnances(type_beneficiaire, date_debut, date_fin):
    """Construit la clause WHERE et les paramètres pour filtrer les ordonnances
    par type de bénéficiaire et/ou période (date_ordonnance)."""
    conditions = []
    params = {}
    if type_beneficiaire:
        conditions.append("o.type_beneficiaire = %(type_beneficiaire)s")
        params["type_beneficiaire"] = type_beneficiaire
    if date_debut:
        conditions.append("o.date_ordonnance >= %(date_debut)s")
        params["date_debut"] = date_debut
    if date_fin:
        conditions.append("o.date_ordonnance <= %(date_fin)s")
        params["date_fin"] = date_fin
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where_clause, params


@router.get("/")
def get_ordonnances(type_beneficiaire: str = None, date_debut: str = None, date_fin: str = None,
                     db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    where_clause, params = _construire_filtres_ordonnances(type_beneficiaire, date_debut, date_fin)
    cursor.execute(f"""
        SELECT o.id, o.date_ordonnance, o.est_validee, o.type_beneficiaire,
               o.beneficiaire, o.patient_id, o.medecin_id, o.mode_paiement, o.mutuelle_id,
               p.nom, p.prenom, m.nom AS medecin_nom, mu.nom AS mutuelle_nom,
               COALESCE(SUM(lo.montant), 0) AS montant_total
        FROM ordonnance o
        LEFT JOIN patients p ON o.patient_id = p.id
        LEFT JOIN medecin m ON o.medecin_id = m.id
        LEFT JOIN mutuelles mu ON o.mutuelle_id = mu.id
        LEFT JOIN ligne_ordonnance lo ON lo.ordonnance_id = o.id
        {where_clause}
        GROUP BY o.id, o.date_ordonnance, o.est_validee, o.type_beneficiaire,
                 o.beneficiaire, o.patient_id, o.medecin_id, o.mode_paiement, o.mutuelle_id,
                 p.nom, p.prenom, m.nom, mu.nom
        ORDER BY o.date_ordonnance DESC, o.id DESC
    """, params)
    return cursor.fetchall()


@router.get("/export")
def export_ordonnances(type_beneficiaire: str = None, date_debut: str = None, date_fin: str = None,
                        db=Depends(get_db), user=Depends(get_current_user)):
    """Retourne les ordonnances (avec leurs lignes) correspondant aux filtres,
    pour permettre la génération d'un export Excel détaillé côté frontend."""
    cursor = db.cursor()
    where_clause, params = _construire_filtres_ordonnances(type_beneficiaire, date_debut, date_fin)
    cursor.execute(f"""
        SELECT o.id, o.date_ordonnance, o.est_validee, o.type_beneficiaire,
               o.beneficiaire, o.patient_id, o.medecin_id, o.mode_paiement, o.mutuelle_id,
               p.nom, p.prenom, m.nom AS medecin_nom, mu.nom AS mutuelle_nom
        FROM ordonnance o
        LEFT JOIN patients p ON o.patient_id = p.id
        LEFT JOIN medecin m ON o.medecin_id = m.id
        LEFT JOIN mutuelles mu ON o.mutuelle_id = mu.id
        {where_clause}
        ORDER BY o.date_ordonnance DESC, o.id DESC
    """, params)
    ordonnances = cursor.fetchall()

    if ordonnances:
        ids = [o["id"] for o in ordonnances]
        cursor.execute("""
            SELECT * FROM ligne_ordonnance WHERE ordonnance_id = ANY(%(ids)s) ORDER BY ordonnance_id, id
        """, {"ids": ids})
        lignes_par_ordonnance = {}
        for ligne in cursor.fetchall():
            lignes_par_ordonnance.setdefault(ligne["ordonnance_id"], []).append(ligne)

        for o in ordonnances:
            o["lignes"] = lignes_par_ordonnance.get(o["id"], [])
            o["montant_total"] = sum((ligne["montant"] or 0) for ligne in o["lignes"])

    return {"ordonnances": ordonnances}


@router.get("/refs/dosages")
def get_dosages(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT id, nom FROM dosages ORDER BY nom")
    return cursor.fetchall()


@router.get("/refs/formes")
def get_formes(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT id, nom FROM formes ORDER BY nom")
    return cursor.fetchall()


@router.get("/refs/medecins")
def get_medecins(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT id, nom FROM medecin ORDER BY nom")
    return cursor.fetchall()


@router.get("/{ordonnance_id}")
def get_ordonnance(ordonnance_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT o.*, p.nom, p.prenom, m.nom AS medecin_nom, mu.nom AS mutuelle_nom
        FROM ordonnance o
        LEFT JOIN patients p ON o.patient_id = p.id
        LEFT JOIN medecin m ON o.medecin_id = m.id
        LEFT JOIN mutuelles mu ON o.mutuelle_id = mu.id
        WHERE o.id = %s
    """, (ordonnance_id,))
    ordonnance = cursor.fetchone()
    if not ordonnance:
        raise HTTPException(status_code=404, detail="Ordonnance non trouvée")

    cursor.execute("""
        SELECT * FROM ligne_ordonnance WHERE ordonnance_id = %s ORDER BY id
    """, (ordonnance_id,))
    ordonnance["lignes"] = cursor.fetchall()
    ordonnance["montant_total"] = sum((ligne["montant"] or 0) for ligne in ordonnance["lignes"])
    return ordonnance


@router.post("/")
def create_ordonnance(data: dict, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["date_ordonnance"])
    if data.get("type_beneficiaire", "patient") == "patient":
        require_fields(data, ["patient_id"])
    cursor = db.cursor()
    type_beneficiaire = data.get("type_beneficiaire", "patient")
    lignes = data.get("lignes", [])
    lignes_resolues = [_resoudre_ligne_ordonnance(cursor, ligne, type_beneficiaire) for ligne in lignes]
    est_validee = data.get("est_validee", 0)
    stock_applique = bool(est_validee)

    cursor.execute("""
        INSERT INTO ordonnance (patient_id, date_ordonnance, est_validee, type_beneficiaire, beneficiaire, medecin_id, stock_applique, mode_paiement, mutuelle_id)
        VALUES (%(patient_id)s, %(date_ordonnance)s, %(est_validee)s, %(type_beneficiaire)s, %(beneficiaire)s, %(medecin_id)s, %(stock_applique)s, %(mode_paiement)s, %(mutuelle_id)s)
        RETURNING id
    """, {
        "patient_id": data.get("patient_id"),
        "date_ordonnance": data["date_ordonnance"],
        "est_validee": est_validee,
        "type_beneficiaire": data.get("type_beneficiaire", "patient"),
        "beneficiaire": data.get("beneficiaire"),
        "medecin_id": data.get("medecin_id"),
        "stock_applique": stock_applique,
        "mode_paiement": data.get("mode_paiement", "especes"),
        "mutuelle_id": data.get("mutuelle_id"),
    })
    ordonnance_id = cursor.fetchone()["id"]

    for ligne, resolue in zip(lignes, lignes_resolues):
        cursor.execute("""
            INSERT INTO ligne_ordonnance (ordonnance_id, patient_id, date_ordonnance, designation,
                                          dosage, forme, quantite, posologie, duree_jours, montant, prix_achat, stock_id)
            VALUES (%(ordonnance_id)s, %(patient_id)s, %(date_ordonnance)s, %(designation)s,
                    %(dosage)s, %(forme)s, %(quantite)s, %(posologie)s, %(duree_jours)s, %(montant)s, %(prix_achat)s, %(stock_id)s)
        """, {
            "ordonnance_id": ordonnance_id,
            "patient_id": data.get("patient_id"),
            "date_ordonnance": data["date_ordonnance"],
            "designation": resolue["designation"],
            "dosage": ligne.get("dosage"),
            "forme": ligne.get("forme"),
            "quantite": ligne.get("quantite", 1),
            "posologie": ligne.get("posologie"),
            "duree_jours": ligne.get("duree_jours"),
            "montant": resolue["montant"],
            "prix_achat": resolue["prix_achat"],
            "stock_id": resolue["stock_id"],
        })

    if stock_applique:
        _decrementer_stock(cursor, lignes_resolues)

    db.commit()
    log_audit(db, request, user, "CREATE", "ordonnance", ordonnance_id, data)
    return {"message": "Ordonnance créée", "id": ordonnance_id}


@router.put("/{ordonnance_id}")
def update_ordonnance(ordonnance_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["date_ordonnance"])
    if data.get("type_beneficiaire", "patient") == "patient":
        require_fields(data, ["patient_id"])
    cursor = db.cursor()

    cursor.execute("SELECT stock_applique FROM ordonnance WHERE id = %s", (ordonnance_id,))
    existante = cursor.fetchone()
    if not existante:
        raise HTTPException(status_code=404, detail="Ordonnance non trouvée")

    type_beneficiaire = data.get("type_beneficiaire", "patient")
    lignes = data.get("lignes", [])
    lignes_resolues = [_resoudre_ligne_ordonnance(cursor, ligne, type_beneficiaire) for ligne in lignes]
    est_validee = data.get("est_validee", 0)
    stock_applique = bool(est_validee)

    if existante["stock_applique"]:
        _restaurer_stock_ordonnance(cursor, ordonnance_id)

    cursor.execute("""
        UPDATE ordonnance
        SET patient_id = %(patient_id)s,
            date_ordonnance = %(date_ordonnance)s,
            est_validee = %(est_validee)s,
            type_beneficiaire = %(type_beneficiaire)s,
            beneficiaire = %(beneficiaire)s,
            medecin_id = %(medecin_id)s,
            stock_applique = %(stock_applique)s,
            mode_paiement = %(mode_paiement)s,
            mutuelle_id = %(mutuelle_id)s
        WHERE id = %(id)s
    """, {
        "patient_id": data.get("patient_id"),
        "date_ordonnance": data["date_ordonnance"],
        "est_validee": est_validee,
        "type_beneficiaire": data.get("type_beneficiaire", "patient"),
        "beneficiaire": data.get("beneficiaire"),
        "medecin_id": data.get("medecin_id"),
        "stock_applique": stock_applique,
        "mode_paiement": data.get("mode_paiement", "especes"),
        "mutuelle_id": data.get("mutuelle_id"),
        "id": ordonnance_id,
    })

    cursor.execute("DELETE FROM ligne_ordonnance WHERE ordonnance_id = %s", (ordonnance_id,))

    for ligne, resolue in zip(lignes, lignes_resolues):
        cursor.execute("""
            INSERT INTO ligne_ordonnance (ordonnance_id, patient_id, date_ordonnance, designation,
                                          dosage, forme, quantite, posologie, duree_jours, montant, prix_achat, stock_id)
            VALUES (%(ordonnance_id)s, %(patient_id)s, %(date_ordonnance)s, %(designation)s,
                    %(dosage)s, %(forme)s, %(quantite)s, %(posologie)s, %(duree_jours)s, %(montant)s, %(prix_achat)s, %(stock_id)s)
        """, {
            "ordonnance_id": ordonnance_id,
            "patient_id": data.get("patient_id"),
            "date_ordonnance": data["date_ordonnance"],
            "designation": resolue["designation"],
            "dosage": ligne.get("dosage"),
            "forme": ligne.get("forme"),
            "quantite": ligne.get("quantite", 1),
            "posologie": ligne.get("posologie"),
            "duree_jours": ligne.get("duree_jours"),
            "montant": resolue["montant"],
            "prix_achat": resolue["prix_achat"],
            "stock_id": resolue["stock_id"],
        })

    if stock_applique:
        _decrementer_stock(cursor, lignes_resolues)

    db.commit()
    log_audit(db, request, user, "UPDATE", "ordonnance", ordonnance_id, data)
    return {"message": "Ordonnance mise à jour"}


@router.delete("/{ordonnance_id}")
def delete_ordonnance(ordonnance_id: int, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("SELECT stock_applique FROM ordonnance WHERE id = %s", (ordonnance_id,))
    existante = cursor.fetchone()
    if not existante:
        raise HTTPException(status_code=404, detail="Ordonnance non trouvée")

    if existante["stock_applique"]:
        _restaurer_stock_ordonnance(cursor, ordonnance_id)
    cursor.execute("DELETE FROM ligne_ordonnance WHERE ordonnance_id = %s", (ordonnance_id,))
    cursor.execute("DELETE FROM ordonnance WHERE id = %s", (ordonnance_id,))
    db.commit()
    log_audit(db, request, user, "DELETE", "ordonnance", ordonnance_id, None)
    return {"message": "Ordonnance supprimée"}