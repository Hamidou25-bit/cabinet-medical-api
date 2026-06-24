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

Suivre le pattern de `ordonnances.py` :

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
- Le préfixe des routes peut contenir un tiret — toujours vérifier avec `curl` avant de tester depuis le frontend.

## Ordre des fonctions dans auth.py

`get_current_user` doit être défini **avant** la route `@router.get("/me")` — l'ordre est critique pour éviter des erreurs.

## Tables PostgreSQL pertinentes

Tables principales : `patients`, `consultations`, `ordonnance`, `ligne_ordonnance`, `rendez_vous`, `stock`, `sortie`, `achats`, `lignes_achat`, `comptabilite`, `depense`, `type_depense`, `type_article_fournisseur` (Phase 18), `personnel`, `utilisateurs`, `examens_complementaires`, `type_examen`, `sous_type_examen`, `medecin`, `dosages`, `formes`, `fournisseur`, `materiel_cabinet`, `soins`, `dossier_patients`, `audit_logs`, `vaccinations` (Phase 11)

⚠️ `type_examen` (catégories d'examens, colonnes `id`/`nom`) et `sous_type_examen` (types d'examens, colonnes `id`/`type_examen_id`/`nom`/`tarif`) existaient déjà avant la Phase 8 — pas de FK déclarée vers `examens_complementaires.sous_type_examen_id`, mais la suppression est protégée au niveau API (409 si référencé).

⚠️ La table `rendez_vous` (colonnes `id`/`patient_id`/`medecin_id`/`date_heure_rdv` texte ISO/`motif`/`statut`/`notes`/`date_creation`) a été réactivée en Phase 11 via `api/rendez_vous.py`. Statuts normalisés **sans accent** : `en_attente`/`confirme`/`arrive`/`annule`/`reporte` (le défaut colonne `'planifié'` est un résidu pré-Phase 11, ignoré par le nouveau code).

⚠️ Le module Mutuelles (Phase 11) a été retiré en Phase 18 : `api/mutuelles.py` supprimé, plus de router dans `main.py`, plus d'option "Mutuelle" dans les formulaires Consultations/Ordonnances. La table `mutuelles` et les colonnes `mutuelle_id` (`consultations`/`ordonnance`) sont **conservées en base, non droppées** (même pattern que `rendez_vous` en Phase 7) pour préserver l'historique déjà saisi.

## État des modules API

| Module | Statut |
|---|---|
| Authentification | ✅ |
| Dashboard (`/dashboard/rdv-aujourdhui`, `/dashboard/statistiques`) | ✅ |
| Patients (liste + création) | ✅ |
| Dossier patient (`GET /patients/{id}/dossier`, agrège consultations/ordonnances/soins/examens/vaccinations) | ✅ |
| Consultations (liste, champ `traitement_apres_diagnostic` supprimé, `mode_paiement`) | ✅ |
| Stock (liste + alertes, `POST /stock/sortie`, `GET /stock/sorties` supprimé) | ✅ |
| Ordonnances (liste filtrable par type_beneficiaire/date + création + export Excel détaillé + validation déclenchant les mouvements de stock via `stock_applique`, montant calculé sur `PrixAchat` pour `type_beneficiaire='interne'`, `mode_paiement`) | ✅ |
| Rendez-vous (réactivé Phase 11, `api/rendez_vous.py`, CRUD + `PATCH /rendez-vous/{id}/statut`) | ✅ |
| Examens complémentaires (`examens-complementaires` CRUD + `examens-categories` + `examens-types` avec `tarif`) | ✅ |
| Vaccinations (`api/vaccinations.py`, CRUD) | ✅ |
| Personnel | ❌ à faire |
| Comptabilité | 🟡 en cours (`type_depense` CRUD admin, `depenses` lecture, `GET /comptabilite/synthese` recettes/dépenses/profit + `recettes_par_mode_paiement`, recettes ordonnances limitées aux ordonnances validées de type `patient`/`tiers`) |
| Rapports | ❌ à faire |
| CRUD Patients (modifier/supprimer) | ❌ à faire (colonne `supprime`) |
| CRUD Stock (entrées/sorties) | 🟡 sortie via `POST /stock/sortie` (entrées via achats) |

## Déploiement

**Automatique (GitHub Actions)** : tout push sur `main` déclenche `.github/workflows/deploy.yml`, qui se connecte en SSH au VPS avec une clé dédiée (secret `DEPLOY_SSH_KEY`, restreinte côté serveur via `command=` dans `authorized_keys` — elle ne peut exécuter que `/usr/local/bin/deploy-api.sh`, rien d'autre) puis vérifie que `https://cabinet-babamouneissa.com/api/` répond `{"status":"ok"}`. Secrets requis sur le dépôt GitHub : `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`. Le script serveur (`/usr/local/bin/deploy-api.sh`) ne touche jamais à `config.py` (exclu du dépôt via `.gitignore`).

**Manuel (si besoin)** :
```bash
cd /home/ubuntu/api && git pull && pm2 restart cabinet-api
```

Vérifier en ligne : http://51.161.10.252/index.html

## Points d'attention

- Le dossier `api/frontend/` a été supprimé (copie morte du premier commit) — ne pas le recréer.
- Ne jamais committer `config.py` ou des secrets JWT.
