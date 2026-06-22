from fastapi import APIRouter, Depends, HTTPException, Request
from datetime import datetime
from database import get_db
from auth import get_current_user, require_role
from validation import require_fields, require_positive
from audit_log import log_audit

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

    if achats:
        ids = [a["id"] for a in achats]
        cursor.execute("""
            SELECT achat_id, designation, quantite, prix_unitaire, montant, type_article
            FROM lignes_achat
            WHERE achat_id = ANY(%(ids)s)
            ORDER BY id
        """, {"ids": ids})
        lignes_par_achat = {}
        for ligne in cursor.fetchall():
            lignes_par_achat.setdefault(ligne["achat_id"], []).append(ligne)
        for achat in achats:
            achat["lignes"] = lignes_par_achat.get(achat["id"], [])

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


def _get_fournisseur_nom(cursor, fournisseur_id):
    if not fournisseur_id:
        return None
    cursor.execute("SELECT nom FROM fournisseur WHERE id = %s", (fournisseur_id,))
    row = cursor.fetchone()
    return row["nom"] if row else None


def _creer_article_stock_pour_ligne(cursor, ligne, date_achat, fournisseur_nom):
    """Crée un nouvel article de stock pour une ligne d'achat sans correspondance, et retourne son idStock."""
    quantite = ligne.get("quantite", 1)
    prix_unitaire = ligne.get("prix_unitaire", 0)
    cursor.execute("""
        INSERT INTO stock ("DateEntree", "Type", "Designation", "Fournisseur",
                          "Quantite", "SeuilAlerte", "PrixVente", "PrixAchat",
                          "Dosage", "Forme", "DatePeremption")
        VALUES (%(DateEntree)s, %(Type)s, %(Designation)s, %(Fournisseur)s,
                %(Quantite)s, %(SeuilAlerte)s, %(PrixVente)s, %(PrixAchat)s,
                %(Dosage)s, %(Forme)s, %(DatePeremption)s)
        RETURNING "idStock"
    """, {
        "DateEntree": date_achat,
        "Type": ligne.get("type_article") or "",
        "Designation": ligne["designation"],
        "Fournisseur": fournisseur_nom,
        "Quantite": quantite,
        "SeuilAlerte": ligne.get("seuil_alerte") or 5,
        "PrixVente": ligne.get("prix_vente") or prix_unitaire,
        "PrixAchat": prix_unitaire,
        "Dosage": ligne.get("dosage"),
        "Forme": ligne.get("forme"),
        "DatePeremption": ligne.get("date_peremption"),
    })
    return cursor.fetchone()["idStock"]


def _inserer_ligne_achat(cursor, achat_id, ligne, stock_id, stock_cree=False):
    quantite = ligne.get("quantite", 1)
    prix_unitaire = ligne.get("prix_unitaire", 0)
    cursor.execute("""
        INSERT INTO lignes_achat (achat_id, designation, quantite, prix_unitaire, montant, type_article, stock_id, stock_cree)
        VALUES (%(achat_id)s, %(designation)s, %(quantite)s, %(prix_unitaire)s, %(montant)s, %(type_article)s, %(stock_id)s, %(stock_cree)s)
    """, {
        "achat_id": achat_id,
        "designation": ligne["designation"],
        "quantite": quantite,
        "prix_unitaire": prix_unitaire,
        "montant": quantite * prix_unitaire,
        "type_article": ligne.get("type_article"),
        "stock_id": stock_id,
        "stock_cree": stock_cree,
    })


def _insert_lignes(cursor, achat_id, lignes, date_achat, fournisseur_nom):
    """Insère les lignes d'achat et répercute l'impact sur le stock (mise à jour ou création d'article)."""
    nouveaux_articles = {}  # designation normalisée -> stock_id, pour dédupliquer dans le même achat

    for ligne in lignes:
        quantite = ligne.get("quantite", 1)
        prix_unitaire = ligne.get("prix_unitaire", 0)
        stock_id = ligne.get("stock_id")
        stock_cree = False

        if stock_id:
            cursor.execute("""
                UPDATE stock SET "Quantite" = "Quantite" + %s, "PrixAchat" = %s
                WHERE "idStock" = %s
            """, (quantite, prix_unitaire, stock_id))
            if cursor.rowcount == 0:
                # L'article de stock référencé n'existe plus -> traité comme nouvel article
                stock_id = None

        if not stock_id:
            key = ligne["designation"].strip().lower()
            if key in nouveaux_articles:
                stock_id = nouveaux_articles[key]
                cursor.execute('UPDATE stock SET "Quantite" = "Quantite" + %s WHERE "idStock" = %s', (quantite, stock_id))
            else:
                stock_id = _creer_article_stock_pour_ligne(cursor, ligne, date_achat, fournisseur_nom)
                nouveaux_articles[key] = stock_id
            stock_cree = True

        _inserer_ligne_achat(cursor, achat_id, ligne, stock_id, stock_cree)


def _retirer_lignes_du_stock(cursor, achat_id):
    """Annule l'impact stock des lignes existantes d'un achat (avant remplacement ou annulation)."""
    cursor.execute("SELECT stock_id, quantite FROM lignes_achat WHERE achat_id = %s", (achat_id,))
    for ligne in cursor.fetchall():
        if ligne["stock_id"]:
            cursor.execute('UPDATE stock SET "Quantite" = "Quantite" - %s WHERE "idStock" = %s', (ligne["quantite"], ligne["stock_id"]))


def _nettoyer_articles_crees(cursor, achat_id):
    """Supprime les articles de stock créés par cet achat (stock_cree=true) qui n'ont
    subi aucun autre mouvement depuis (ni autre achat actif, ni sortie)."""
    cursor.execute("""
        SELECT DISTINCT stock_id FROM lignes_achat
        WHERE achat_id = %s AND stock_cree = true AND stock_id IS NOT NULL
    """, (achat_id,))
    stock_ids = [row["stock_id"] for row in cursor.fetchall()]

    for stock_id in stock_ids:
        cursor.execute("""
            SELECT 1 FROM lignes_achat
            WHERE stock_id = %s AND achat_id != %s
            LIMIT 1
        """, (stock_id, achat_id))
        if cursor.fetchone():
            continue

        cursor.execute("""
            SELECT 1 FROM sortie s
            JOIN stock st ON st."idStock" = %s
            WHERE LOWER(TRIM(s."Designation")) = LOWER(TRIM(st."Designation"))
            LIMIT 1
        """, (stock_id,))
        if cursor.fetchone():
            continue

        cursor.execute('DELETE FROM stock WHERE "idStock" = %s', (stock_id,))


def _description_depense_achat(fournisseur_nom, numero_facture):
    numero = numero_facture or "(sans numéro)"
    if fournisseur_nom:
        return f"Achat fournisseur {fournisseur_nom} - Facture n°{numero}"
    return f"Achat fournisseur - Facture n°{numero}"


def _upsert_depense_achat(cursor, achat_id, date_achat, montant_total, fournisseur_nom, numero_facture):
    description = _description_depense_achat(fournisseur_nom, numero_facture)
    cursor.execute("SELECT id_depense FROM depense WHERE achat_id = %s", (achat_id,))
    existing = cursor.fetchone()
    if existing:
        cursor.execute("""
            UPDATE depense
            SET date_depense = %s, type_depense = 'Achats Fournisseurs', montant = %s, description = %s
            WHERE id_depense = %s
        """, (date_achat, montant_total, description, existing["id_depense"]))
    else:
        cursor.execute("""
            INSERT INTO depense (date_depense, type_depense, montant, description, achat_id)
            VALUES (%s, 'Achats Fournisseurs', %s, %s, %s)
        """, (date_achat, montant_total, description, achat_id))


def _validate_achat(data: dict):
    require_fields(data, ["date_achat"])
    lignes = data.get("lignes", [])
    if not lignes:
        raise HTTPException(status_code=400, detail="Champ(s) obligatoire(s) manquant(s) : lignes (au moins un article)")
    for ligne in lignes:
        require_fields(ligne, ["designation"])
        require_positive(ligne, ["quantite", "prix_unitaire"])


@router.post("/")
def create_achat(data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    _validate_achat(data)
    cursor = db.cursor()
    lignes = data.get("lignes", [])
    montant_total = sum(l.get("quantite", 1) * l.get("prix_unitaire", 0) for l in lignes)
    fournisseur_nom = _get_fournisseur_nom(cursor, data.get("fournisseur_id"))

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

    _insert_lignes(cursor, achat_id, lignes, data["date_achat"], fournisseur_nom)
    _upsert_depense_achat(cursor, achat_id, data["date_achat"], montant_total, fournisseur_nom, data.get("numero_facture"))

    db.commit()
    log_audit(db, request, user, "CREATE", "achats", achat_id, data)
    return {"message": "Achat créé", "id": achat_id}


@router.put("/{achat_id}")
def update_achat(achat_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    _validate_achat(data)
    cursor = db.cursor()
    lignes = data.get("lignes", [])
    montant_total = sum(l.get("quantite", 1) * l.get("prix_unitaire", 0) for l in lignes)
    fournisseur_nom = _get_fournisseur_nom(cursor, data.get("fournisseur_id"))

    cursor.execute('SELECT id FROM achats WHERE id = %s', (achat_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Achat non trouvé")

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

    _retirer_lignes_du_stock(cursor, achat_id)
    cursor.execute("DELETE FROM lignes_achat WHERE achat_id = %s", (achat_id,))
    _insert_lignes(cursor, achat_id, lignes, data["date_achat"], fournisseur_nom)
    _upsert_depense_achat(cursor, achat_id, data["date_achat"], montant_total, fournisseur_nom, data.get("numero_facture"))

    db.commit()
    log_audit(db, request, user, "UPDATE", "achats", achat_id, data)
    return {"message": "Achat mis à jour"}


@router.delete("/{achat_id}")
def delete_achat(achat_id: int, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("SELECT id FROM achats WHERE id = %s", (achat_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Achat non trouvé")

    _retirer_lignes_du_stock(cursor, achat_id)
    _nettoyer_articles_crees(cursor, achat_id)
    cursor.execute("DELETE FROM depense WHERE achat_id = %s", (achat_id,))
    cursor.execute("DELETE FROM lignes_achat WHERE achat_id = %s", (achat_id,))
    cursor.execute("DELETE FROM achats WHERE id = %s", (achat_id,))
    db.commit()
    log_audit(db, request, user, "DELETE", "achats", achat_id, None)
    return {"message": "Achat supprimé"}
