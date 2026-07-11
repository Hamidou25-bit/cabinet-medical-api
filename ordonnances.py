from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from auth import get_current_user, require_role
from validation import require_fields
from audit_log import log_audit
from soins import inserer_soin
from repartition import calculer_et_enregistrer_repartition

router = APIRouter(prefix="/ordonnances", tags=["Ordonnances"])


def _resoudre_ligne_ordonnance(cursor, ligne, type_beneficiaire="patient"):
    """Résout designation, montant et prix_achat d'une ligne d'ordonnance.
    Si stock_id est renseigné, le prix d'achat (coût) est toujours calculé
    depuis le stock. Le montant dépend du type de bénéficiaire : usage interne,
    toujours recalculé depuis le prix d'achat ; patient/tiers, le montant
    envoyé par le frontend est accepté s'il est valide (> 0) — prix ajustable
    par le prescripteur —, sinon calculé depuis le prix de vente par défaut.
    Sans stock_id (médicament externe), les valeurs envoyées par le frontend
    sont conservées telles quelles."""
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
        if type_beneficiaire == "interne":
            montant = prix_achat
        else:
            try:
                montant_saisi = float(montant) if montant is not None else 0
            except (TypeError, ValueError):
                montant_saisi = 0
            montant = montant_saisi if montant_saisi > 0 else quantite * (article["PrixVente"] or 0)

    if not designation:
        raise HTTPException(status_code=400, detail="Champ(s) obligatoire(s) manquant(s) : designation")

    return {
        "designation": designation,
        "montant": montant,
        "prix_achat": prix_achat,
        "stock_id": stock_id,
        "quantite": quantite,
    }


def _verifier_montants_avant_validation(lignes_resolues):
    """Empêche de valider une ordonnance (est_validee=1) si une ligne contient
    un médicament (quantité > 0) mais un montant à 0 — signe d'un prix de vente
    manquant côté stock ou non saisi pour un médicament externe."""
    designations_invalides = [l["designation"] for l in lignes_resolues if l["quantite"] > 0 and l["montant"] <= 0]
    if designations_invalides:
        raise HTTPException(
            status_code=400,
            detail=f"Impossible de valider l'ordonnance : montant à 0 pour {', '.join(designations_invalides)}. "
                   f"Vérifiez le prix de vente (stock) ou saisissez un montant manuel."
        )


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


def _resoudre_soins_ordonnance(soins, type_beneficiaire, patient_id, beneficiaire, date_ordonnance):
    """Valide et prépare les soins saisis depuis le formulaire Ordonnance.
    Ignoré pour le type_beneficiaire 'interne' (un soin n'a pas de sens en usage interne).
    Le patient/bénéficiaire et la date sont repris de l'ordonnance elle-même."""
    if type_beneficiaire not in ("patient", "tiers") or not soins:
        return []
    resolues = []
    for soin in soins:
        if not soin.get("type_soin_id"):
            raise HTTPException(status_code=400, detail="Type de soin obligatoire pour chaque ligne de soin")
        resolues.append({
            "type_soin_id": soin["type_soin_id"],
            "patient_id": patient_id if type_beneficiaire == "patient" else None,
            "nom_patient_externe": beneficiaire if type_beneficiaire == "tiers" else None,
            "prix_applique": soin.get("prix_applique", 0),
            "date_soin": date_ordonnance,
            "notes": soin.get("notes"),
        })
    return resolues


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
               o.beneficiaire, o.patient_id, o.medecin_id, o.mode_paiement, o.mutuelle_id, o.paye,
               p.nom, p.prenom, m.nom AS medecin_nom, mu.nom AS mutuelle_nom,
               COALESCE(SUM(lo.montant), 0) AS montant_total
        FROM ordonnance o
        LEFT JOIN patients p ON o.patient_id = p.id
        LEFT JOIN medecin m ON o.medecin_id = m.id
        LEFT JOIN mutuelles mu ON o.mutuelle_id = mu.id
        LEFT JOIN ligne_ordonnance lo ON lo.ordonnance_id = o.id
        {where_clause}
        GROUP BY o.id, o.date_ordonnance, o.est_validee, o.type_beneficiaire,
                 o.beneficiaire, o.patient_id, o.medecin_id, o.mode_paiement, o.mutuelle_id, o.paye,
                 p.nom, p.prenom, m.nom, mu.nom
        ORDER BY o.date_ordonnance DESC, o.id DESC
    """, params)
    return cursor.fetchall()


@router.get("/export")
def export_ordonnances(type_beneficiaire: str = None, date_debut: str = None, date_fin: str = None,
                        db=Depends(get_db), user=Depends(require_role("admin"))):
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


@router.get("/marges")
def get_marges_ordonnances(date_debut: str = None, date_fin: str = None, db=Depends(get_db), user=Depends(require_role("admin"))):
    """Marge cabinet sur les médicaments du stock vendus via ordonnance, basée sur le
    prix d'achat/montant figés sur chaque ligne au moment de la vente (et non sur le
    prix actuel du stock, qui peut avoir changé depuis - cf. bug recettes Phase 14)."""
    cursor = db.cursor()
    cursor.execute("""
        SELECT lo.designation,
               SUM(lo.quantite) AS quantite_vendue,
               SUM(lo.quantite * lo.prix_achat) AS cout_total,
               SUM(lo.montant) AS recette_totale,
               SUM(lo.montant) - SUM(lo.quantite * lo.prix_achat) AS marge_totale
        FROM ligne_ordonnance lo
        JOIN ordonnance o ON o.id = lo.ordonnance_id
        WHERE lo.stock_id IS NOT NULL
        AND o.paye = TRUE
        AND o.type_beneficiaire IN ('patient', 'tiers')
        AND (%(date_debut)s IS NULL OR o.date_ordonnance >= %(date_debut)s)
        AND (%(date_fin)s IS NULL OR o.date_ordonnance <= %(date_fin)s)
        GROUP BY lo.designation
        ORDER BY marge_totale DESC
    """, {"date_debut": date_debut, "date_fin": date_fin})
    lignes = cursor.fetchall()

    resultat = []
    for l in lignes:
        cout_total = float(l["cout_total"] or 0)
        recette_totale = float(l["recette_totale"] or 0)
        marge_totale = recette_totale - cout_total
        resultat.append({
            "designation": l["designation"],
            "quantite_vendue": l["quantite_vendue"],
            "cout_total": cout_total,
            "recette_totale": recette_totale,
            "marge_totale": marge_totale,
            "taux_marge_pct": round(marge_totale * 100 / cout_total, 1) if cout_total > 0 else 0,
        })

    totaux = {
        "cout_total": sum(r["cout_total"] for r in resultat),
        "recette_totale": sum(r["recette_totale"] for r in resultat),
        "marge_totale": sum(r["marge_totale"] for r in resultat),
    }
    return {"lignes": resultat, "totaux": totaux}


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
    if est_validee:
        _verifier_montants_avant_validation(lignes_resolues)

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

    soins_resolus = _resoudre_soins_ordonnance(
        data.get("soins", []), type_beneficiaire, data.get("patient_id"), data.get("beneficiaire"), data["date_ordonnance"]
    )
    for soin in soins_resolus:
        inserer_soin(cursor, soin, ordonnance_id)

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
    if est_validee:
        _verifier_montants_avant_validation(lignes_resolues)

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

    soins_resolus = _resoudre_soins_ordonnance(
        data.get("soins", []), type_beneficiaire, data.get("patient_id"), data.get("beneficiaire"), data["date_ordonnance"]
    )
    cursor.execute("DELETE FROM soins WHERE ordonnance_id = %s", (ordonnance_id,))
    for soin in soins_resolus:
        inserer_soin(cursor, soin, ordonnance_id)

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


@router.post("/{ordonnance_id}/encaisser")
def encaisser_ordonnance(ordonnance_id: int, request: Request, db=Depends(get_db), user=Depends(require_role("admin", "secretaire"))):
    """Encaisse une ordonnance validée (patient/tiers) : ne facture que les lignes dont
    le médicament provient du stock du cabinet (stock_id renseigné) — un médicament acheté
    par le patient en dehors du cabinet n'a rien à encaisser ici."""
    cursor = db.cursor()
    cursor.execute("""
        SELECT o.id, o.type_beneficiaire, o.est_validee, o.paye, o.beneficiaire, o.date_ordonnance, p.nom, p.prenom
        FROM ordonnance o
        LEFT JOIN patients p ON o.patient_id = p.id
        WHERE o.id = %s
    """, (ordonnance_id,))
    ordonnance = cursor.fetchone()
    if not ordonnance:
        raise HTTPException(status_code=404, detail="Ordonnance non trouvée")
    if ordonnance["type_beneficiaire"] not in ("patient", "tiers"):
        raise HTTPException(status_code=400, detail="Seules les ordonnances patient/tiers peuvent être encaissées")
    if not ordonnance["est_validee"]:
        raise HTTPException(status_code=400, detail="L'ordonnance doit être validée avant d'être encaissée")
    if ordonnance["paye"]:
        raise HTTPException(status_code=400, detail="Ordonnance déjà encaissée")

    cursor.execute("""
        SELECT designation, montant
        FROM ligne_ordonnance
        WHERE ordonnance_id = %s AND stock_id IS NOT NULL
        ORDER BY id
    """, (ordonnance_id,))
    lignes_facturees = cursor.fetchall()
    montant = float(sum((l["montant"] or 0) for l in lignes_facturees))
    if montant <= 0:
        return {"message": "Aucun médicament en stock cabinet à facturer", "montant": 0, "encaisse": False}

    cursor.execute("UPDATE ordonnance SET paye = true WHERE id = %s", (ordonnance_id,))
    calculer_et_enregistrer_repartition(db, "ordonnance", ordonnance_id, montant, ordonnance["date_ordonnance"])
    db.commit()
    log_audit(db, request, user, "ENCAISSER", "ordonnance", ordonnance_id, None)
    patient_nom = f"{ordonnance['nom'] or ''} {ordonnance['prenom'] or ''}".strip() or ordonnance["beneficiaire"] or "-"
    return {
        "message": "Ordonnance encaissée",
        "montant": montant,
        "encaisse": True,
        "ordonnance": {"id": ordonnance["id"], "patient_nom": patient_nom},
        "lignes": [{"libelle": l["designation"], "montant": float(l["montant"] or 0)} for l in lignes_facturees],
    }