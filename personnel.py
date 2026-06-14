from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import require_role
from validation import require_fields

router = APIRouter(prefix="/personnel", tags=["Personnel"])


@router.get("/")
def get_personnel(db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        SELECT p.id, p.nom, p.prenom, p.fonction, p.telephone, p.date_entree, p.date_sortie,
               u.id AS utilisateur_id, u.nom_utilisateur, u.role, u.actif
        FROM personnel p
        LEFT JOIN utilisateurs u ON u.personnel_id = p.id
        ORDER BY p.nom, p.prenom
    """)
    return cursor.fetchall()


@router.get("/{personnel_id}")
def get_personnel_by_id(personnel_id: int, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        SELECT p.id, p.nom, p.prenom, p.fonction, p.telephone, p.date_entree, p.date_sortie,
               u.id AS utilisateur_id, u.nom_utilisateur, u.role, u.actif
        FROM personnel p
        LEFT JOIN utilisateurs u ON u.personnel_id = p.id
        WHERE p.id = %s
    """, (personnel_id,))
    personnel = cursor.fetchone()
    if not personnel:
        raise HTTPException(status_code=404, detail="Membre du personnel non trouvé")
    return personnel


@router.post("/")
def create_personnel(data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["nom", "prenom", "fonction"])
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO personnel (nom, prenom, fonction, telephone, date_entree, date_sortie)
        VALUES (%(nom)s, %(prenom)s, %(fonction)s, %(telephone)s, %(date_entree)s, %(date_sortie)s)
        RETURNING id
    """, {
        "nom": data["nom"],
        "prenom": data["prenom"],
        "fonction": data.get("fonction"),
        "telephone": data.get("telephone"),
        "date_entree": data.get("date_entree") or datetime.utcnow().strftime("%Y-%m-%d"),
        "date_sortie": data.get("date_sortie"),
    })
    db.commit()
    return {"message": "Membre du personnel créé", "id": cursor.fetchone()["id"]}


@router.put("/{personnel_id}")
def update_personnel(personnel_id: int, data: dict, db=Depends(get_db), user=Depends(require_role("admin"))):
    require_fields(data, ["nom", "prenom", "fonction"])
    cursor = db.cursor()
    cursor.execute("""
        UPDATE personnel
        SET nom = %(nom)s,
            prenom = %(prenom)s,
            fonction = %(fonction)s,
            telephone = %(telephone)s,
            date_entree = %(date_entree)s,
            date_sortie = %(date_sortie)s
        WHERE id = %(id)s
    """, {
        "nom": data["nom"],
        "prenom": data["prenom"],
        "fonction": data.get("fonction"),
        "telephone": data.get("telephone"),
        "date_entree": data.get("date_entree"),
        "date_sortie": data.get("date_sortie"),
        "id": personnel_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Membre du personnel non trouvé")
    db.commit()
    return {"message": "Membre du personnel mis à jour"}


@router.delete("/{personnel_id}")
def deactivate_personnel(personnel_id: int, db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("""
        UPDATE personnel
        SET date_sortie = %(date_sortie)s
        WHERE id = %(id)s
    """, {
        "date_sortie": datetime.utcnow().strftime("%Y-%m-%d"),
        "id": personnel_id,
    })
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Membre du personnel non trouvé")

    cursor.execute("UPDATE utilisateurs SET actif = false WHERE personnel_id = %s", (personnel_id,))

    db.commit()
    return {"message": "Membre du personnel désactivé"}
