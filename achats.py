from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from database import get_db
from auth import get_current_user, require_role
from validation import require_fields, require_positive

router = APIRouter(prefix="/achats", tags=["Achats"])


@router.get("/")
def get_achats(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT a.id, a.fournisseur_id, a.numero_facture, a.date_achat, a.montant_total,
               a.statut_paiement, a.notes, a.date_creation, a.statut_facture,
               f.nom AS fournisseur_nom
        FROM achats a
        LEFT JOIN fournisseur f ON a.fournisseur_id = f.id
        ORDER BY a.date_achat DESC, a.id DESC
    """)
    achats = cursor.fetchall()
    for achat in achats:
        if achat["fournisseur_id"] is not None and achat["fournisseur_nom"] is None:
            achat["fournisseur_nom"] = "Fournisseur inconnu"
    return achats


@router.get("/{achat_id}")
def get_achat(achat_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT a.*, f.nom AS fournisseur_nom
        FROM achats a
        LEFT JOIN fournisseur f ON a.fournisseur_id = f.id
        WHERE a.id = %s
    """, (achat_id,))
    achat = cursor.fetchone()
    if not achat:
        raise HTTPException(status_code=404, detail="Achat non trouvé")
    if achat["fournisseur_id"] is not None and achat["fournisseur_nom"] is None:
        achat["fournisseur_nom"] = "Fournisseur inconnu"

    cursor.execute("SELECT * FROM lignes_achat WHERE achat_id = %s ORDER BY id", (achat_id,))
    achat["lignes"] = cursor.fetchall()
    return achat


def _insert_lignes(cursor, achat_id, lignes):
    for ligne in lignes:
        quantite = ligne.get("quantite", 1)
        prix_unitaire = ligne.get("prix_unitaire", 0)
        cursor.execute("""
            INSERT INTO lignes_achat (achat_id, designation, quantite, prix_unitaire, montant, type_article)
            VALUES (%(achat_id)s, %(designation)s, %(quantite)s, %(prix_unitaire)s, %(montant)s, %(type_article)s)
        """, {
            "achat_id": achat_id,
            "designation": ligne["designation"],
            "quantite": quantite,
            "prix_unitaire": prix_unitaire,
            "montant": quantite * prix_unitaire,
            "type_article": ligne.get("type_article"),
        })


def _validate_achat(data: dict):
    require_fields(data, ["date_achat"])
    lignes = data.get("lignes", [])
    if not lignes:
        raise HTTPException(status_code=400, detail="Champ(s) obligatoire(s) manquant(s) : lignes (au moins un article)")
    for ligne in lignes:
        require_fields(ligne, ["designation"])
        require_positive(ligne, ["quantite", "prix_unitaire"])


@router.post("/")
def create_achat(data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    _validate_achat(data)
    cursor = db.cursor()
    lignes = data.get("lignes", [])
    montant_total = sum(l.get("quantite", 1) * l.get("prix_unitaire", 0) for l in lignes)

    cursor.execute("""
        INSERT INTO achats (fournisseur_id, numero_facture, date_achat, montant_total, statut_paiement, notes, date_creation, statut_facture)
        VALUES (%(fournisseur_id)s, %(numero_facture)s, %(date_achat)s, %(montant_total)s, %(statut_paiement)s, %(notes)s, %(date_creation)s, 'Actif')
        RETURNING id
    """, {
        "fournisseur_id": data.get("fournisseur_id"),
        "numero_facture": data.get("numero_facture"),
        "date_achat": data["date_achat"],
        "montant_total": montant_total,
        "statut_paiement": data.get("statut_paiement", "Non payé"),
        "notes": data.get("notes"),
        "date_creation": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    achat_id = cursor.fetchone()["id"]

    _insert_lignes(cursor, achat_id, lignes)

    db.commit()
    return {"message": "Achat créé", "id": achat_id}


@router.put("/{achat_id}")
def update_achat(achat_id: int, data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    _validate_achat(data)
    cursor = db.cursor()
    lignes = data.get("lignes", [])
    montant_total = sum(l.get("quantite", 1) * l.get("prix_unitaire", 0) for l in lignes)

    cursor.execute("""
        UPDATE achats
        SET fournisseur_id = %(fournisseur_id)s,
            numero_facture = %(numero_facture)s,
            date_achat = %(date_achat)s,
            montant_total = %(montant_total)s,
            statut_paiement = %(statut_paiement)s,
            notes = %(notes)s
        WHERE id = %(id)s
    """, {
        "fournisseur_id": data.get("fournisseur_id"),
        "numero_facture": data.get("numero_facture"),
        "date_achat": data["date_achat"],
        "montant_total": montant_total,
        "statut_paiement": data.get("statut_paiement", "Non payé"),
        "notes": data.get("notes"),
        "id": achat_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Achat non trouvé")

    cursor.execute("DELETE FROM lignes_achat WHERE achat_id = %s", (achat_id,))
    _insert_lignes(cursor, achat_id, lignes)

    db.commit()
    return {"message": "Achat mis à jour"}


@router.delete("/{achat_id}")
def delete_achat(achat_id: int, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("UPDATE achats SET statut_facture = 'Annulé' WHERE id = %s", (achat_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Achat non trouvé")
    db.commit()
    return {"message": "Achat annulé"}
