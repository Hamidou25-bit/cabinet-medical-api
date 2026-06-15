# Cabinet Médical BabaMouneissa — API (FastAPI)

Dépôt : https://github.com/Hamidou25-bit/cabinet-medical-api (branche `main`)

## Stack technique

- Backend : FastAPI + psycopg2 (pas d'ORM), `RealDictCursor`, connexion par requête via `Depends(get_db)`
- Auth : JWT (PyJWT, HS256, durée 8h), table `utilisateurs`, compte admin `hamidou`
- Base de données : PostgreSQL, base `cabinet_medical`, user `cabinet_user`
- CORS : ouvert à tous (`allow_origins=["*"]`)

## Lancer en local

```bash
# Terminal 1 : tunnel SSH vers la base de données de production
ssh -L 5433:localhost:5432 ubuntu@51.161.10.252

# Terminal 2 : lancer l'API
cd api && uvicorn main:app --reload --port 8001
```

⚠️ `database.py` : le port par défaut doit toujours rester **5432** (production). En local on utilise le tunnel sur 5433, mais ne jamais pusher cette valeur sur GitHub.

## Fichier de config

`api/config.py` est exclu de Git (`.gitignore`) car il contient le `SECRET_KEY` JWT. Si le dépôt est cloné sur une nouvelle machine, il faut le recréer manuellement.

## Convention pour chaque nouveau module API

Suivre le pattern de `ordonnances.py` / `rendez_vous.py` :

```python
from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/nom-module", tags=["Nom Module"])

@router.get("/")
def get_items(db=Depends(get_db), user=Depends(get_current_user)):
    ...
```

- Toujours inclure `user=Depends(get_current_user)` sur chaque route (protection JWT)
- Après création du fichier, ajouter dans `main.py` :
  ```python
  import nom_module
  app.include_router(nom_module.router)
  ```
- Le préfixe des routes peut contenir un tiret (ex: `/rendez-vous/`, pas `/rendez_vous/`) — toujours vérifier avec `curl` avant de tester depuis le frontend.

## Ordre des fonctions dans auth.py

`get_current_user` doit être défini **avant** la route `@router.get("/me")` — l'ordre est critique pour éviter des erreurs.

## Tables PostgreSQL pertinentes

Tables principales : `patients`, `consultations`, `ordonnance`, `ligne_ordonnance`, `rendez_vous`, `stock`, `sortie`, `achats`, `lignes_achat`, `comptabilite`, `depense`, `type_depense`, `personnel`, `utilisateurs`, `examens_complementaires`, `medecin`, `dosages`, `formes`, `fournisseur`, `materiel_cabinet`, `soins`, `dossier_patients`, `audit_logs`

## État des modules API

| Module | Statut |
|---|---|
| Authentification | ✅ |
| Dashboard | ✅ |
| Patients (liste + création) | ✅ |
| Consultations (liste) | ✅ |
| Stock (liste + alertes) | ✅ |
| Ordonnances (liste filtrable par type_beneficiaire/date + création + export Excel détaillé) | ✅ |
| Rendez-vous (liste + création) | ✅ |
| Examens complémentaires | ❌ à faire |
| Personnel | ❌ à faire |
| Comptabilité | 🟡 en cours (`type_depense` CRUD admin, `depenses` lecture, `GET /comptabilite/synthese` recettes/dépenses/profit) |
| Rapports | ❌ à faire |
| CRUD Patients (modifier/supprimer) | ❌ à faire (colonne `supprime`) |
| CRUD Stock (entrées/sorties) | ❌ à faire (table `sortie`) |

## Déploiement

```bash
cd /home/ubuntu/api && git pull && pm2 restart cabinet-api
```

Vérifier en ligne : http://51.161.10.252/index.html

## Points d'attention

- Le dossier `api/frontend/` a été supprimé (copie morte du premier commit) — ne pas le recréer.
- Ne jamais committer `config.py` ou des secrets JWT.
