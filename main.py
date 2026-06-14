from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import patients
import consultations
import stock
import auth
import ordonnances
import rendez_vous
import examens
import personnel
import medecins
import fournisseurs

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
app.include_router(rendez_vous.router)
app.include_router(examens.router)
app.include_router(personnel.router)
app.include_router(medecins.router)
app.include_router(fournisseurs.router)
app.include_router(auth.router)

@app.get("/")
def root():
    return {"message": "API Cabinet Médical BabaMouneissa", "status": "ok"}
