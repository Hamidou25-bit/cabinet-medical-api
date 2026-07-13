from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from auth import require_role, get_current_user
from validation import require_fields, require_positive
from audit_log import log_audit
from stock_utils import (
    valider_categorie_et_unites,
    convertir_en_unites,
    arrondir_prix_fcfa,
    valider_marge_pourcentage,
    valider_statut_equipement,
    consommer_stock,
    CATEGORIES_CONSOMMABLES,
)

router = APIRouter(prefix="/stock", tags=["Stock"])

@router.get("/")
def get_stock(categorie: str = None, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    where_clause = ""
    params = {}
    if categorie:
        where_clause = 'WHERE categorie = %(categorie)s'
        params["categorie"] = categorie
    cursor.execute(f"""
        SELECT "idStock", "DateEntree", "Type", "Designation", "Fournisseur",
               "Quantite", "SeuilAlerte", "PrixVente", "PrixAchat",
               "Dosage", "Forme", "DatePeremption", categorie, unites_par_boite,
               marge_personnalisee, statut_equipement, sous_type_examen_id, quantite_examen
        FROM stock
        {where_clause}
        ORDER BY "Designation"
    """, params)
    return cursor.fetchall()

@router.get("/designations")
def get_designations(db=Depends(get_db), user=Depends(require_role("admin", "medecin", "secretaire"))):
    """Liste allégée du stock (sans alertes/fournisseur) pour l'autocomplete des lignes d'ordonnance.
    Filtrée sur les médicaments uniquement : le matériel médical n'a pas vocation à être prescrit."""
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "Designation", "Quantite", "PrixVente", "PrixAchat",
               "Dosage", "Forme"
        FROM stock
        WHERE categorie = 'medicament'
        ORDER BY "Designation"
    """)
    return cursor.fetchall()

@router.get("/consommables")
def get_consommables(categorie: str = None, db=Depends(get_db), user=Depends(get_current_user)):
    """Liste allégée des consommables, accessible à tous les rôles connectés (GET /stock/
    est admin-only) — utilisée par la page Utilisation Médicale (consommable_medical)
    et la sélection de consommables labo sur la page Examens (consommable_laboratoire).
    Ne renvoie JAMAIS de médicaments ni d'équipement."""
    if categorie is not None and categorie not in CATEGORIES_CONSOMMABLES:
        raise HTTPException(
            status_code=400,
            detail=f"categorie invalide : {categorie} (valeurs possibles : {', '.join(CATEGORIES_CONSOMMABLES)})",
        )
    categories = [categorie] if categorie else list(CATEGORIES_CONSOMMABLES)
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "Designation", "Quantite", "SeuilAlerte", "PrixVente",
               "Dosage", "Forme", categorie, sous_type_examen_id, quantite_examen
        FROM stock
        WHERE categorie = ANY(%s)
        ORDER BY "Designation"
    """, (categories,))
    return cursor.fetchall()

@router.get("/disponibilite")
def get_stock_disponibilite(q: str = "", db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock" as id, "Designation" as designation,
               "Dosage" as dosage, "Forme" as forme,
               "Quantite" as quantite, "SeuilAlerte" as seuil_alerte,
               "PrixVente" as prix_vente, "PrixAchat" as prix_achat,
               categorie
        FROM stock
        WHERE LOWER("Designation") LIKE LOWER(%s)
          AND "Quantite" > 0
          AND categorie = 'medicament'
        ORDER BY "Designation" ASC
        LIMIT 15
    """, (f'%{q}%',))
    return cursor.fetchall()

@router.get("/alertes")
def get_alertes(db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "Designation", "Quantite", "SeuilAlerte", categorie
        FROM stock
        WHERE "Quantite" <= "SeuilAlerte"
          AND categorie <> 'equipement'
        ORDER BY "Quantite"
    """)
    return cursor.fetchall()

@router.get("/equipements-a-remplacer")
def get_equipements_a_remplacer(db=Depends(get_db), user=Depends(require_role("admin"))):
    """Équipements passés manuellement en statut 'a_remplacer' — pendant de
    GET /alertes (qui, lui, exclut l'équipement : pas de logique de seuil)."""
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "Designation", "Type", "DateEntree", "Fournisseur"
        FROM stock
        WHERE categorie = 'equipement'
          AND statut_equipement = 'a_remplacer'
        ORDER BY "Designation"
    """)
    return cursor.fetchall()

@router.get("/alertes-peremption")
def get_alertes_peremption(db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        SELECT "idStock", "Designation", "DatePeremption"
        FROM stock
        WHERE "DatePeremption" IS NOT NULL
          AND "DatePeremption" <> ''
          AND "DatePeremption"::date <= CURRENT_DATE + INTERVAL '30 days'
        ORDER BY "DatePeremption"
    """)
    return cursor.fetchall()

def _calculer_recalcul_prix(cursor):
    """Calcule le recalcul des prix de vente à partir des marges (catégorie ou
    personnalisée par article). Lecture seule — utilisé par l'aperçu et
    l'application réelle pour garantir un résultat strictement identique.

    Retourne (a_modifier, ignores) :
    - a_modifier : articles dont le nouveau prix diffère du PrixVente actuel
    - ignores : articles à PrixAchat NULL ou <= 0, exclus du calcul (signalés
      plutôt que recalculés en silence vers un prix aberrant à 0 FCFA)
    """
    cursor.execute("""
        SELECT s."idStock", s."Designation", s.categorie,
               s."PrixAchat", s."PrixVente",
               s.marge_personnalisee, m.marge_pourcentage
        FROM stock s
        JOIN marges_categorie m ON m.categorie = s.categorie
        WHERE s.categorie <> 'equipement'
        ORDER BY s."Designation"
    """)
    a_modifier, ignores = [], []
    for row in cursor.fetchall():
        prix_achat = row["PrixAchat"]
        if prix_achat is None or float(prix_achat) <= 0:
            ignores.append({
                "id": row["idStock"],
                "designation": row["Designation"],
                "categorie": row["categorie"],
                "PrixAchat": prix_achat,
                "raison": "PrixAchat nul ou manquant",
            })
            continue
        # NUMERIC -> Decimal via psycopg2 : conversion float obligatoire avant
        # de mélanger avec PrixAchat (REAL -> float), cf. bug Phase 15
        marge = row["marge_personnalisee"] if row["marge_personnalisee"] is not None else row["marge_pourcentage"]
        marge = float(marge)
        nouveau_prix = arrondir_prix_fcfa(float(prix_achat) * (1 + marge / 100))
        ancien_prix = row["PrixVente"]
        if ancien_prix is None or float(ancien_prix) != float(nouveau_prix):
            a_modifier.append({
                "id": row["idStock"],
                "designation": row["Designation"],
                "categorie": row["categorie"],
                "PrixAchat": float(prix_achat),
                "ancien_prix_vente": float(ancien_prix) if ancien_prix is not None else None,
                "nouveau_prix_vente": nouveau_prix,
                "marge_appliquee": marge,
                "marge_source": "personnalisee" if row["marge_personnalisee"] is not None else "categorie",
            })
    return a_modifier, ignores


@router.get("/recalculer-prix/apercu")
def apercu_recalcul_prix(db=Depends(get_db), user=Depends(require_role("admin"))):
    """Aperçu du recalcul des prix de vente — ne modifie rien en base."""
    a_modifier, ignores = _calculer_recalcul_prix(db.cursor())
    return {
        "nb_articles_a_modifier": len(a_modifier),
        "articles": a_modifier,
        "articles_ignores": ignores,
    }


@router.post("/recalculer-prix/appliquer")
def appliquer_recalcul_prix(request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    """Applique réellement le recalcul des prix de vente (même calcul que l'aperçu)."""
    cursor = db.cursor()
    a_modifier, ignores = _calculer_recalcul_prix(cursor)
    for ligne in a_modifier:
        cursor.execute(
            'UPDATE stock SET "PrixVente" = %s WHERE "idStock" = %s',
            (ligne["nouveau_prix_vente"], ligne["id"]),
        )
    db.commit()
    log_audit(db, request, user, "RECALCUL_PRIX", "stock", None, {
        "nb_articles_modifies": len(a_modifier),
        "articles": a_modifier,
        "articles_ignores": ignores,
    })
    return {
        "message": f"{len(a_modifier)} article(s) mis à jour",
        "nb_articles_modifies": len(a_modifier),
        "articles": a_modifier,
        "articles_ignores": ignores,
    }


def _resoudre_statut_et_prix_vente(article, cursor, statut_defaut="bon_etat"):
    """Règles spécifiques à l'équipement (jamais vendu) : PrixVente non exigé et
    forcé à 0, statut_equipement accepté. Pour toute autre catégorie : PrixVente
    obligatoire, statut_equipement refusé s'il est fourni non nul, et forcé à
    NULL en base. statut_defaut s'applique quand le payload ne fournit pas de
    statut : 'bon_etat' à la création, None à la mise à jour (le PUT conserve
    alors le statut existant via COALESCE plutôt que de l'écraser).
    Retourne (est_equipement, statut_equipement, prix_vente)."""
    est_equipement = article.get("categorie", "medicament") == "equipement"
    statut = article.get("statut_equipement")
    if est_equipement:
        statut = valider_statut_equipement(statut, cursor) if statut is not None else statut_defaut
        return True, statut, 0
    if statut is not None:
        raise HTTPException(
            status_code=400,
            detail="statut_equipement n'est accepté que pour la catégorie 'equipement'",
        )
    require_fields(article, ["PrixVente"])
    return False, None, article.get("PrixVente")


def _resoudre_lien_examen(article, cursor):
    """Lien consommable labo → type d'examen (pré-remplissage des consommables du
    modal Examen). Pertinent uniquement pour categorie='consommable_laboratoire' :
    pour toute autre catégorie, sous_type_examen_id est refusé s'il est fourni non
    nul et forcé à NULL en base (quantite_examen retombe au défaut 1) — même
    pattern que statut_equipement. Retourne (sous_type_examen_id, quantite_examen)."""
    est_labo = article.get("categorie", "medicament") == "consommable_laboratoire"
    sous_type_id = article.get("sous_type_examen_id")
    if not est_labo:
        if sous_type_id is not None:
            raise HTTPException(
                status_code=400,
                detail="sous_type_examen_id n'est accepté que pour la catégorie 'consommable_laboratoire'",
            )
        return None, 1
    if sous_type_id is not None:
        try:
            sous_type_id = int(sous_type_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="sous_type_examen_id doit être un entier")
        cursor.execute("SELECT id FROM sous_type_examen WHERE id = %s", (sous_type_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Type d'examen {sous_type_id} non trouvé")
    quantite = article.get("quantite_examen")
    if quantite is None or quantite == "":
        quantite = 1
    try:
        quantite = float(quantite)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="quantite_examen doit être un nombre")
    if quantite <= 0:
        raise HTTPException(status_code=400, detail="quantite_examen doit être > 0")
    return sous_type_id, quantite


@router.post("/")
def create_article(article: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(article, ["Designation", "Quantite"])
    unites_par_boite = valider_categorie_et_unites(article)
    cursor = db.cursor()
    est_equipement, statut_equipement, prix_vente = _resoudre_statut_et_prix_vente(article, cursor)
    sous_type_examen_id, quantite_examen = _resoudre_lien_examen(article, cursor)
    cursor.execute("""
        INSERT INTO stock ("DateEntree", "Type", "Designation", "Fournisseur",
                          "Quantite", "SeuilAlerte", "PrixVente", "PrixAchat",
                          "Dosage", "Forme", "DatePeremption", categorie, unites_par_boite,
                          statut_equipement, sous_type_examen_id, quantite_examen)
        VALUES (%(DateEntree)s, %(Type)s, %(Designation)s, %(Fournisseur)s,
                %(Quantite)s, %(SeuilAlerte)s, %(PrixVente)s, %(PrixAchat)s,
                %(Dosage)s, %(Forme)s, %(DatePeremption)s, %(categorie)s, %(unites_par_boite)s,
                %(statut_equipement)s, %(sous_type_examen_id)s, %(quantite_examen)s)
        RETURNING "idStock"
    """, {
        "sous_type_examen_id": sous_type_examen_id,
        "quantite_examen": quantite_examen,
        "DateEntree": article.get("DateEntree"),
        "Type": article.get("Type"),
        "Designation": article.get("Designation"),
        "Fournisseur": article.get("Fournisseur"),
        "Quantite": article.get("Quantite"),
        "SeuilAlerte": article.get("SeuilAlerte"),
        "PrixVente": prix_vente,
        "PrixAchat": article.get("PrixAchat"),
        "Dosage": article.get("Dosage"),
        "Forme": article.get("Forme"),
        "DatePeremption": article.get("DatePeremption"),
        "categorie": article.get("categorie", "medicament"),
        "unites_par_boite": unites_par_boite,
        "statut_equipement": statut_equipement,
    })
    db.commit()
    new_id = cursor.fetchone()["idStock"]
    log_audit(db, request, user, "CREATE", "stock", new_id, article)
    return {"message": "Article créé", "id": new_id}


@router.put("/{stock_id}")
def update_article(stock_id: int, article: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(article, ["Designation", "Quantite"])
    unites_par_boite = valider_categorie_et_unites(article)
    cursor = db.cursor()
    est_equipement, statut_equipement, prix_vente = _resoudre_statut_et_prix_vente(article, cursor, statut_defaut=None)

    # marge_personnalisee : mise à jour uniquement si la clé est présente dans le
    # payload (NULL explicite = revenir à la marge de catégorie). Un payload sans
    # la clé ne doit pas effacer une marge existante.
    set_marge = ""
    params_marge = {}
    if "marge_personnalisee" in article:
        marge = article["marge_personnalisee"]
        if marge is not None:
            marge = valider_marge_pourcentage(marge, "marge_personnalisee")
        set_marge = ", marge_personnalisee = %(marge_personnalisee)s"
        params_marge = {"marge_personnalisee": marge}

    # Équipement : COALESCE conserve le statut existant si le payload n'en fournit
    # pas (et 'bon_etat' couvre le reclassement d'un article vers équipement).
    # Autres catégories : statut remis à NULL (efface un statut devenu obsolète
    # après reclassement hors équipement).
    set_statut = ("statut_equipement = COALESCE(%(statut_equipement)s, statut_equipement, 'bon_etat')"
                  if est_equipement else "statut_equipement = NULL")

    sous_type_examen_id, quantite_examen = _resoudre_lien_examen(article, cursor)
    cursor.execute(f"""
        UPDATE stock
        SET "DateEntree" = %(DateEntree)s,
            "Type" = %(Type)s,
            "Designation" = %(Designation)s,
            "Fournisseur" = %(Fournisseur)s,
            "Quantite" = %(Quantite)s,
            "SeuilAlerte" = %(SeuilAlerte)s,
            "PrixVente" = %(PrixVente)s,
            "PrixAchat" = %(PrixAchat)s,
            "Dosage" = %(Dosage)s,
            "Forme" = %(Forme)s,
            "DatePeremption" = %(DatePeremption)s,
            categorie = %(categorie)s,
            unites_par_boite = %(unites_par_boite)s,
            sous_type_examen_id = %(sous_type_examen_id)s,
            quantite_examen = %(quantite_examen)s,
            {set_statut}
            {set_marge}
        WHERE "idStock" = %(idStock)s
    """, {
        **params_marge,
        "statut_equipement": statut_equipement,
        "sous_type_examen_id": sous_type_examen_id,
        "quantite_examen": quantite_examen,
        "DateEntree": article.get("DateEntree"),
        "Type": article.get("Type"),
        "Designation": article.get("Designation"),
        "Fournisseur": article.get("Fournisseur"),
        "Quantite": article.get("Quantite"),
        "SeuilAlerte": article.get("SeuilAlerte"),
        "PrixVente": prix_vente,
        "PrixAchat": article.get("PrixAchat"),
        "Dosage": article.get("Dosage"),
        "Forme": article.get("Forme"),
        "DatePeremption": article.get("DatePeremption"),
        "categorie": article.get("categorie", "medicament"),
        "unites_par_boite": unites_par_boite,
        "idStock": stock_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    db.commit()
    log_audit(db, request, user, "UPDATE", "stock", stock_id, article)
    return {"message": "Article mis à jour"}


@router.post("/{stock_id}/reapprovisionner")
def reapprovisionner_article(stock_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    """Ajoute du stock à un article existant, soit en unités directes
    (quantite_unites), soit en boîtes (nombre_boites × unites_par_boite).
    Exactement un des deux champs doit être fourni."""
    quantite_unites = data.get("quantite_unites")
    nombre_boites = data.get("nombre_boites")
    cursor = db.cursor()
    unites_ajoutees = convertir_en_unites(cursor, stock_id, quantite_unites, nombre_boites)

    cursor.execute(
        'UPDATE stock SET "Quantite" = "Quantite" + %s WHERE "idStock" = %s RETURNING "Quantite"',
        (unites_ajoutees, stock_id),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    nouvelle_quantite = row["Quantite"]
    db.commit()
    champ = "quantite_unites" if quantite_unites is not None else "nombre_boites"
    log_audit(db, request, user, "UPDATE", "stock", stock_id, {
        "action": "reapprovisionnement",
        champ: int(quantite_unites if quantite_unites is not None else nombre_boites),
        "unites_ajoutees": unites_ajoutees,
        "nouvelle_quantite": nouvelle_quantite,
    })
    return {
        "message": "Stock réapprovisionné",
        "unites_ajoutees": unites_ajoutees,
        "nouvelle_quantite": nouvelle_quantite,
    }


@router.post("/{stock_id}/consommer")
def consommer_article(stock_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    """Sortie interne d'un consommable (usage non facturé au patient), tracée dans
    mouvements_consommable. Réservée aux catégories consommable_laboratoire et
    consommable_medical — refuse explicitement les médicaments (qui sortent
    exclusivement via les ordonnances) et l'équipement. Tous rôles connectés."""
    require_fields(data, ["quantite", "type_sortie"])

    type_sortie = data["type_sortie"]
    if type_sortie not in ("examen_patient", "usage_interne"):
        raise HTTPException(
            status_code=400,
            detail=f"type_sortie invalide : {type_sortie} (valeurs possibles : examen_patient, usage_interne)",
        )

    try:
        quantite = int(data["quantite"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="quantite doit être un entier")
    if quantite < 1:
        raise HTTPException(status_code=400, detail="quantite doit être >= 1")

    cursor = db.cursor()
    # patient_id/examen_id n'ont de sens que pour une sortie liée à un examen
    patient_id = data.get("patient_id") if type_sortie == "examen_patient" else None
    examen_id = data.get("examen_id") if type_sortie == "examen_patient" else None
    # Pré-vérification des références pour renvoyer un 404 clair plutôt qu'une
    # erreur FK illisible (500)
    if patient_id is not None:
        cursor.execute("SELECT id FROM patients WHERE id = %s", (patient_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} non trouvé")
    if examen_id is not None:
        cursor.execute("SELECT id FROM examens_complementaires WHERE id = %s", (examen_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Examen {examen_id} non trouvé")

    # consommer_stock verrouille la ligne (FOR UPDATE) : évite deux prélèvements
    # simultanés passant tous les deux le contrôle de stock suffisant
    article, mouvement, nouvelle_quantite = consommer_stock(
        cursor, stock_id, quantite, type_sortie, user["id"],
        patient_id=patient_id, examen_id=examen_id, motif=data.get("motif"),
    )
    db.commit()
    log_audit(db, request, user, "CONSOMMER", "stock", stock_id, {
        "mouvement_id": mouvement["id"],
        "designation": article["Designation"],
        "quantite": quantite,
        "type_sortie": type_sortie,
        "patient_id": patient_id,
        "examen_id": examen_id,
        "motif": data.get("motif"),
        "nouvelle_quantite": nouvelle_quantite,
    })
    return {
        "message": "Prélèvement enregistré",
        "mouvement": mouvement,
        "nouvelle_quantite": nouvelle_quantite,
    }


@router.get("/mouvements")
def get_mouvements(categorie: str = None, limit: int = 50, offset: int = 0, db=Depends(get_db), user=Depends(get_current_user)):
    """Historique paginé des mouvements de consommable, tous articles confondus,
    filtrable par catégorie (ex: consommable_laboratoire pour le modal Consommables
    de la page Examens)."""
    if categorie is not None and categorie not in CATEGORIES_CONSOMMABLES:
        raise HTTPException(
            status_code=400,
            detail=f"categorie invalide : {categorie} (valeurs possibles : {', '.join(CATEGORIES_CONSOMMABLES)})",
        )
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    where_clause = ""
    params = {"limit": limit, "offset": offset}
    if categorie:
        where_clause = "WHERE s.categorie = %(categorie)s"
        params["categorie"] = categorie
    cursor = db.cursor()
    cursor.execute(f"""
        SELECT COUNT(*) AS total
        FROM mouvements_consommable m
        LEFT JOIN stock s ON m.stock_id = s."idStock"
        {where_clause}
    """, params)
    total = cursor.fetchone()["total"]
    cursor.execute(f"""
        SELECT m.id, m.stock_id, m.designation, m.quantite, m.type_sortie, m.motif,
               m.date_mouvement, m.patient_id, m.examen_id,
               u.nom_complet AS utilisateur_nom, u.nom_utilisateur AS utilisateur_login,
               p.nom AS patient_nom, p.prenom AS patient_prenom
        FROM mouvements_consommable m
        LEFT JOIN stock s ON m.stock_id = s."idStock"
        LEFT JOIN utilisateurs u ON m.utilisateur_id = u.id
        LEFT JOIN patients p ON m.patient_id = p.id
        {where_clause}
        ORDER BY m.date_mouvement DESC, m.id DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """, params)
    return {"total": total, "mouvements": cursor.fetchall()}


@router.put("/mouvements/{mouvement_id}")
def update_mouvement(mouvement_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    """Corrige un prélèvement d'usage interne (quantité et/ou motif) en réajustant
    stock.Quantite de la différence. Réservé aux mouvements type_sortie='usage_interne' —
    les sorties liées à un examen sont gérées automatiquement et ne se corrigent pas ici."""
    cursor = db.cursor()
    cursor.execute("SELECT * FROM mouvements_consommable WHERE id = %s", (mouvement_id,))
    mouvement = cursor.fetchone()
    if not mouvement:
        raise HTTPException(status_code=404, detail="Mouvement non trouvé")
    if mouvement["type_sortie"] != "usage_interne":
        raise HTTPException(status_code=400, detail="Seuls les prélèvements d'usage interne sont modifiables")
    if mouvement["stock_id"] is None:
        raise HTTPException(status_code=400, detail="L'article de stock lié à ce mouvement n'existe plus — quantité non modifiable")

    ancienne_quantite = mouvement["quantite"]
    nouvelle_quantite = ancienne_quantite
    if "quantite" in data and data["quantite"] is not None:
        try:
            nouvelle_quantite = int(data["quantite"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="quantite doit être un entier")
        if nouvelle_quantite < 1:
            raise HTTPException(status_code=400, detail="quantite doit être >= 1")

    delta = nouvelle_quantite - ancienne_quantite  # >0 : prélever plus, <0 : restituer
    if delta != 0:
        cursor.execute(
            'SELECT "Designation", "Quantite" FROM stock WHERE "idStock" = %s FOR UPDATE',
            (mouvement["stock_id"],),
        )
        article = cursor.fetchone()
        if not article:
            raise HTTPException(status_code=400, detail="L'article de stock lié à ce mouvement n'existe plus — quantité non modifiable")
        if article["Quantite"] - delta < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuffisant pour '{article['Designation']}' : "
                       f"{article['Quantite']} unité(s) disponible(s), {delta} supplémentaire(s) demandée(s)",
            )
        cursor.execute(
            'UPDATE stock SET "Quantite" = "Quantite" - %s WHERE "idStock" = %s',
            (delta, mouvement["stock_id"]),
        )

    motif = data.get("motif", mouvement["motif"])
    cursor.execute("""
        UPDATE mouvements_consommable SET quantite = %s, motif = %s WHERE id = %s
        RETURNING id, stock_id, designation, quantite, type_sortie, motif, date_mouvement
    """, (nouvelle_quantite, motif, mouvement_id))
    updated = cursor.fetchone()
    db.commit()
    log_audit(db, request, user, "UPDATE", "mouvements_consommable", mouvement_id, {
        "designation": mouvement["designation"],
        "ancienne_quantite": ancienne_quantite,
        "nouvelle_quantite": nouvelle_quantite,
        "delta_stock": -delta,
        "motif": motif,
    })
    return {"message": "Mouvement modifié", "mouvement": updated}


@router.delete("/mouvements/{mouvement_id}")
def delete_mouvement(mouvement_id: int, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    """Supprime un prélèvement d'usage interne et restitue la quantité au stock.
    Réservé aux mouvements type_sortie='usage_interne'. Si l'article de stock a été
    supprimé entre-temps (stock_id NULL), le mouvement est supprimé sans restitution."""
    cursor = db.cursor()
    cursor.execute("SELECT * FROM mouvements_consommable WHERE id = %s", (mouvement_id,))
    mouvement = cursor.fetchone()
    if not mouvement:
        raise HTTPException(status_code=404, detail="Mouvement non trouvé")
    if mouvement["type_sortie"] != "usage_interne":
        raise HTTPException(status_code=400, detail="Seuls les prélèvements d'usage interne sont supprimables")

    stock_restaure = False
    if mouvement["stock_id"] is not None:
        cursor.execute(
            'UPDATE stock SET "Quantite" = "Quantite" + %s WHERE "idStock" = %s RETURNING "Quantite"',
            (mouvement["quantite"], mouvement["stock_id"]),
        )
        stock_restaure = cursor.fetchone() is not None
    cursor.execute("DELETE FROM mouvements_consommable WHERE id = %s", (mouvement_id,))
    db.commit()
    log_audit(db, request, user, "DELETE", "mouvements_consommable", mouvement_id, {
        "designation": mouvement["designation"],
        "quantite_restituee": mouvement["quantite"] if stock_restaure else 0,
        "stock_id": mouvement["stock_id"],
    })
    return {"message": "Mouvement supprimé", "stock_restaure": stock_restaure}


@router.get("/{stock_id}/mouvements")
def get_mouvements_article(stock_id: int, limit: int = 20, offset: int = 0, db=Depends(get_db), user=Depends(get_current_user)):
    """Historique paginé des mouvements de consommable d'un article."""
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    cursor = db.cursor()
    cursor.execute('SELECT "idStock", "Designation" FROM stock WHERE "idStock" = %s', (stock_id,))
    article = cursor.fetchone()
    if not article:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    cursor.execute("SELECT COUNT(*) AS total FROM mouvements_consommable WHERE stock_id = %s", (stock_id,))
    total = cursor.fetchone()["total"]
    cursor.execute("""
        SELECT m.id, m.quantite, m.type_sortie, m.motif, m.date_mouvement,
               m.patient_id, m.examen_id,
               u.nom_complet AS utilisateur_nom, u.nom_utilisateur AS utilisateur_login,
               p.nom AS patient_nom, p.prenom AS patient_prenom
        FROM mouvements_consommable m
        LEFT JOIN utilisateurs u ON m.utilisateur_id = u.id
        LEFT JOIN patients p ON m.patient_id = p.id
        WHERE m.stock_id = %s
        ORDER BY m.date_mouvement DESC, m.id DESC
        LIMIT %s OFFSET %s
    """, (stock_id, limit, offset))
    return {
        "article": article,
        "total": total,
        "mouvements": cursor.fetchall(),
    }


@router.post("/sortie")
def create_sortie(data: dict, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["Designation", "QuantiteSortie"])
    require_positive(data, ["QuantiteSortie"])
    cursor = db.cursor()
    cursor.execute('SELECT "PrixVente", "PrixAchat", "Quantite" FROM stock WHERE "Designation" = %s', (data["Designation"],))
    article = cursor.fetchone()
    if not article:
        raise HTTPException(status_code=404, detail="Article non trouvé dans le stock")

    quantite_sortie = data["QuantiteSortie"]
    prix_vente = data.get("PrixVente", article["PrixVente"])
    prix_achat = data.get("PrixAchat", article["PrixAchat"])

    cursor.execute("""
        INSERT INTO sortie ("DateSortie", "Designation", "QuantiteSortie", "PrixVente",
                            "Montant", "Patient", "idOrdonnance", "PrixAchat")
        VALUES (%(DateSortie)s, %(Designation)s, %(QuantiteSortie)s, %(PrixVente)s,
                %(Montant)s, %(Patient)s, %(idOrdonnance)s, %(PrixAchat)s)
        RETURNING "idSortie"
    """, {
        "DateSortie": data.get("DateSortie") or datetime.utcnow().strftime("%Y-%m-%d"),
        "Designation": data["Designation"],
        "QuantiteSortie": quantite_sortie,
        "PrixVente": prix_vente,
        "Montant": quantite_sortie * prix_vente,
        "Patient": data.get("Patient", ""),
        "idOrdonnance": data.get("idOrdonnance"),
        "PrixAchat": prix_achat,
    })
    sortie_id = cursor.fetchone()["idSortie"]

    cursor.execute('UPDATE stock SET "Quantite" = "Quantite" - %s WHERE "Designation" = %s', (quantite_sortie, data["Designation"]))

    db.commit()
    log_audit(db, request, user, "CREATE", "sortie", sortie_id, data)
    return {"message": "Sortie enregistrée", "id": sortie_id}


@router.delete("/{stock_id}")
def delete_article(stock_id: int, request: Request, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("DELETE FROM stock WHERE \"idStock\" = %s", (stock_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    db.commit()
    log_audit(db, request, user, "DELETE", "stock", stock_id, None)
    return {"message": "Article supprimé"}
