from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user
from validation import require_fields

router = APIRouter(prefix="/ordonnances", tags=["Ordonnances"])


def _resoudre_ligne_ordonnance(cursor, ligne):
    """Résout designation, montant et prix_achat d'une ligne d'ordonnance.
    Si stock_id est renseigné, le montant et le prix d'achat sont calculés
    à partir des prix du stock. Sinon (médicament externe), les valeurs
    envoyées par le frontend sont conservées telles quelles."""
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
        montant = quantite * (article["PrixVente"] or 0)
        prix_achat = quantite * (article["PrixAchat"] or 0)

    if not designation:
        raise HTTPException(status_code=400, detail="Champ(s) obligatoire(s) manquant(s) : designation")

    return {
        "designation": designation,
        "montant": montant,
        "prix_achat": prix_achat,
        "stock_id": stock_id,
    }


@router.get("/")
def get_ordonnances(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT o.id, o.date_ordonnance, o.est_validee, o.type_beneficiaire,
               o.beneficiaire, o.motif, o.patient_id,
               p.nom, p.prenom
        FROM ordonnance o
        LEFT JOIN patients p ON o.patient_id = p.id
        ORDER BY o.date_ordonnance DESC, o.id DESC
    """)
    return cursor.fetchall()


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
        SELECT o.*, p.nom, p.prenom
        FROM ordonnance o
        LEFT JOIN patients p ON o.patient_id = p.id
        WHERE o.id = %s
    """, (ordonnance_id,))
    ordonnance = cursor.fetchone()
    if not ordonnance:
        raise HTTPException(status_code=404, detail="Ordonnance non trouvée")

    cursor.execute("""
        SELECT * FROM ligne_ordonnance WHERE ordonnance_id = %s ORDER BY id
    """, (ordonnance_id,))
    ordonnance["lignes"] = cursor.fetchall()
    return ordonnance


@router.post("/")
def create_ordonnance(data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["patient_id", "date_ordonnance"])
    cursor = db.cursor()
    lignes = data.get("lignes", [])
    lignes_resolues = [_resoudre_ligne_ordonnance(cursor, ligne) for ligne in lignes]

    cursor.execute("""
        INSERT INTO ordonnance (patient_id, date_ordonnance, est_validee, type_beneficiaire, beneficiaire, motif)
        VALUES (%(patient_id)s, %(date_ordonnance)s, %(est_validee)s, %(type_beneficiaire)s, %(beneficiaire)s, %(motif)s)
        RETURNING id
    """, {
        "patient_id": data["patient_id"],
        "date_ordonnance": data["date_ordonnance"],
        "est_validee": data.get("est_validee", 0),
        "type_beneficiaire": data.get("type_beneficiaire", "patient"),
        "beneficiaire": data.get("beneficiaire"),
        "motif": data.get("motif"),
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
            "patient_id": data["patient_id"],
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

    db.commit()
    return {"message": "Ordonnance créée", "id": ordonnance_id}


@router.put("/{ordonnance_id}")
def update_ordonnance(ordonnance_id: int, data: dict, db=Depends(get_db), user=Depends(get_current_user)):
    require_fields(data, ["patient_id", "date_ordonnance"])
    cursor = db.cursor()
    lignes = data.get("lignes", [])
    lignes_resolues = [_resoudre_ligne_ordonnance(cursor, ligne) for ligne in lignes]

    cursor.execute("""
        UPDATE ordonnance
        SET patient_id = %(patient_id)s,
            date_ordonnance = %(date_ordonnance)s,
            est_validee = %(est_validee)s,
            type_beneficiaire = %(type_beneficiaire)s,
            beneficiaire = %(beneficiaire)s,
            motif = %(motif)s
        WHERE id = %(id)s
    """, {
        "patient_id": data["patient_id"],
        "date_ordonnance": data["date_ordonnance"],
        "est_validee": data.get("est_validee", 0),
        "type_beneficiaire": data.get("type_beneficiaire", "patient"),
        "beneficiaire": data.get("beneficiaire"),
        "motif": data.get("motif"),
        "id": ordonnance_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Ordonnance non trouvée")

    cursor.execute("DELETE FROM ligne_ordonnance WHERE ordonnance_id = %s", (ordonnance_id,))

    for ligne, resolue in zip(lignes, lignes_resolues):
        cursor.execute("""
            INSERT INTO ligne_ordonnance (ordonnance_id, patient_id, date_ordonnance, designation,
                                          dosage, forme, quantite, posologie, duree_jours, montant, prix_achat, stock_id)
            VALUES (%(ordonnance_id)s, %(patient_id)s, %(date_ordonnance)s, %(designation)s,
                    %(dosage)s, %(forme)s, %(quantite)s, %(posologie)s, %(duree_jours)s, %(montant)s, %(prix_achat)s, %(stock_id)s)
        """, {
            "ordonnance_id": ordonnance_id,
            "patient_id": data["patient_id"],
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

    db.commit()
    return {"message": "Ordonnance mise à jour"}


@router.delete("/{ordonnance_id}")
def delete_ordonnance(ordonnance_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM ligne_ordonnance WHERE ordonnance_id = %s", (ordonnance_id,))
    cursor.execute("DELETE FROM ordonnance WHERE id = %s", (ordonnance_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Ordonnance non trouvée")
    db.commit()
    return {"message": "Ordonnance supprimée"}