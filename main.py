from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import patients
import consultations
import stock
import auth
import ordonnances
import examens
import examens_categories
import examens_types
import personnel
import medecins
import fournisseurs
import type_depense
import depenses
import achats
import comptabilite
import type_soins
import soins
import utilisateurs
import dossier
import dashboard
import mutuelles

app = FastAPI(title="Cabinet Médical BabaMouneissa API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(patients.router)
app.include_router(consultations.router)
app.include_router(stock.router)
app.include_router(ordonnances.router)
app.include_router(examens.router)
app.include_router(examens_categories.router)
app.include_router(examens_types.router)
app.include_router(personnel.router)
app.include_router(medecins.router)
app.include_router(fournisseurs.router)
app.include_router(type_depense.router)
app.include_router(depenses.router)
app.include_router(achats.router)
app.include_router(comptabilite.router)
app.include_router(type_soins.router)
app.include_router(soins.router)
app.include_router(utilisateurs.router)
app.include_router(dossier.router)
app.include_router(dashboard.router)
app.include_router(mutuelles.router)
app.include_router(auth.router)

@app.get("/")
def root():
    return {"message": "API Cabinet Médical BabaMouneissa", "status": "ok"}
