from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from auth import get_current_user
from audit_log import log_audit
import bcrypt

router = APIRouter(prefix="/utilisateurs", tags=["Utilisateurs"])

ROLES_VALIDES = {"admin", "medecin", "secretaire", "laborantin"}


def require_admin(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return user


@router.get("/")
def list_utilisateurs(db=Depends(get_db), user=Depends(require_admin)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, nom_utilisateur, nom_complet, role, actif
        FROM utilisateurs
        ORDER BY nom_utilisateur
    """)
    return cursor.fetchall()


@router.post("/")
def create_utilisateur(data: dict, request: Request, db=Depends(get_db), user=Depends(require_admin)):
    nom_utilisateur = (data.get("nom_utilisateur") or "").strip()
    mot_de_passe = data.get("mot_de_passe") or ""
    role = data.get("role") or ""
    nom_complet = (data.get("nom_complet") or "").strip()

    if not nom_utilisateur or not mot_de_passe or not role:
        raise HTTPException(status_code=422, detail="Champs obligatoires : nom_utilisateur, mot_de_passe, role")
    if role not in ROLES_VALIDES:
        raise HTTPException(status_code=422, detail=f"Rôle invalide. Valeurs acceptées : {', '.join(ROLES_VALIDES)}")

    hashed = bcrypt.hashpw(mot_de_passe.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO utilisateurs (nom_utilisateur, mot_de_passe_hash, nom_complet, role, actif)
            VALUES (%(nom_utilisateur)s, %(hash)s, %(nom_complet)s, %(role)s, true)
            RETURNING id
        """, {
            "nom_utilisateur": nom_utilisateur,
            "hash": hashed,
            "nom_complet": nom_complet,
            "role": role,
        })
        db.commit()
        new_id = cursor.fetchone()["id"]
        log_audit(db, request, user, "CREATE", "utilisateurs", new_id, {
            "nom_utilisateur": nom_utilisateur,
            "nom_complet": nom_complet,
            "role": role,
        })
        return {"message": "Utilisateur créé", "id": new_id}
    except Exception as e:
        db.rollback()
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="Ce login est déjà utilisé")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{utilisateur_id}")
def update_utilisateur(utilisateur_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(require_admin)):
    nom_utilisateur = (data.get("nom_utilisateur") or "").strip()
    role = (data.get("role") or "").strip()
    nom_complet = (data.get("nom_complet") or "").strip()

    if not nom_utilisateur or not role:
        raise HTTPException(status_code=422, detail="Champs obligatoires : nom_utilisateur, role")
    if role not in ROLES_VALIDES:
        raise HTTPException(status_code=422, detail=f"Rôle invalide. Valeurs acceptées : {', '.join(ROLES_VALIDES)}")

    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE utilisateurs
            SET nom_utilisateur = %(nom_utilisateur)s,
                nom_complet = %(nom_complet)s,
                role = %(role)s
            WHERE id = %(id)s
        """, {
            "nom_utilisateur": nom_utilisateur,
            "nom_complet": nom_complet,
            "role": role,
            "id": utilisateur_id,
        })
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        db.commit()
        log_audit(db, request, user, "UPDATE", "utilisateurs", utilisateur_id, {
            "nom_utilisateur": nom_utilisateur,
            "nom_complet": nom_complet,
            "role": role,
        })
        return {"message": "Utilisateur mis à jour"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="Ce login est déjà utilisé")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{utilisateur_id}")
def delete_utilisateur(utilisateur_id: int, request: Request, db=Depends(get_db), user=Depends(require_admin)):
    if utilisateur_id == user.get("id"):
        raise HTTPException(status_code=403, detail="Impossible de supprimer votre propre compte")
    cursor = db.cursor()
    cursor.execute("DELETE FROM utilisateurs WHERE id = %s", (utilisateur_id,))
    if cursor.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    db.commit()
    log_audit(db, request, user, "DELETE", "utilisateurs", utilisateur_id, None)
    return {"message": "Utilisateur supprimé"}


@router.put("/{utilisateur_id}/password")
def change_password(utilisateur_id: int, data: dict, request: Request, db=Depends(get_db), user=Depends(require_admin)):
    mot_de_passe = data.get("mot_de_passe") or ""
    if not mot_de_passe:
        raise HTTPException(status_code=422, detail="Nouveau mot de passe requis")
    hashed = bcrypt.hashpw(mot_de_passe.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cursor = db.cursor()
    cursor.execute(
        "UPDATE utilisateurs SET mot_de_passe_hash = %s WHERE id = %s",
        (hashed, utilisateur_id)
    )
    if cursor.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    db.commit()
    log_audit(db, request, user, "UPDATE_PASSWORD", "utilisateurs", utilisateur_id, None)
    return {"message": "Mot de passe mis à jour"}
