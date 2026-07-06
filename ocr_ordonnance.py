import base64
import json
import re
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from auth import get_current_user
from config import GROQ_API_KEY
from database import get_db

router = APIRouter(prefix="/ocr", tags=["OCR Ordonnance"])

UPLOAD_DIR = Path(__file__).resolve().parent / "uploads" / "ocr_temp"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

GROQ_VISION_MODEL = "qwen/qwen3.6-27b"

PROMPT_EXTRACTION = """Tu es un assistant qui extrait les informations d'une photo d'ordonnance médicale manuscrite.
Réponds UNIQUEMENT avec un objet JSON strictement de cette forme, sans aucun texte avant ou après :
{"patient_nom": "", "date": "", "medecin": "", "medicaments": [{"nom": "", "dosage": "", "posologie": ""}]}
Si une information est illisible ou absente, laisse la chaîne vide (ou un tableau vide pour medicaments).
Ne donne aucune explication ni raisonnement, uniquement le JSON."""


def _nettoyer_et_parser_json(texte: str) -> dict:
    """Nettoie la réponse du modèle (bloc <think>, balises ```json```, texte parasite)
    avant de parser le JSON attendu."""
    texte = re.sub(r"<think>.*?</think>", "", texte, flags=re.DOTALL)
    texte = re.sub(r"```(?:json)?", "", texte)
    debut = texte.find("{")
    fin = texte.rfind("}")
    if debut == -1 or fin == -1 or fin < debut:
        raise ValueError("JSON introuvable dans la réponse du modèle")
    return json.loads(texte[debut:fin + 1])


async def _appeler_groq_vision(image_b64: str, mime: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_VISION_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": PROMPT_EXTRACTION},
                                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                            ],
                        }
                    ],
                    "max_tokens": 1024,
                    "temperature": 0.1,
                },
            )
    except httpx.RequestError:
        raise HTTPException(status_code=500, detail="Service IA inaccessible")

    if response.status_code != 200:
        raise HTTPException(status_code=422, detail="Extraction impossible, saisie manuelle nécessaire")

    result = response.json()
    return result["choices"][0]["message"]["content"]


@router.post("/ordonnance")
async def extraire_ordonnance(photo: UploadFile = File(...), db=Depends(get_db), user=Depends(get_current_user)):
    """Lit UNIQUEMENT (aucune écriture en base) : extrait les données d'une photo
    d'ordonnance via Groq Vision et propose un patient existant s'il y en a un.
    L'enregistrement final reste entièrement géré par les routes/boutons existants
    (POST /patients/, POST /ordonnances/)."""
    contenu = await photo.read()
    extension = Path(photo.filename or "").suffix or ".jpg"
    photo_temp_id = str(uuid.uuid4())
    (UPLOAD_DIR / f"{photo_temp_id}{extension}").write_bytes(contenu)

    image_b64 = base64.b64encode(contenu).decode("utf-8")
    mime = photo.content_type or "image/jpeg"
    texte = await _appeler_groq_vision(image_b64, mime)

    try:
        extraction = _nettoyer_et_parser_json(texte)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Extraction impossible, saisie manuelle nécessaire")

    patient_existant = None
    nom_extrait = (extraction.get("patient_nom") or "").strip()
    if nom_extrait:
        cursor = db.cursor()
        cursor.execute(
            """SELECT id, nom, prenom FROM patients
               WHERE (supprime = 0 OR supprime IS NULL)
               AND (nom ILIKE %(recherche)s OR (nom || ' ' || prenom) ILIKE %(recherche)s)
               LIMIT 1""",
            {"recherche": f"%{nom_extrait}%"},
        )
        row = cursor.fetchone()
        if row:
            patient_existant = {"id": row["id"], "nom": f"{row['nom']} {row['prenom']}"}

    return {
        "extraction": extraction,
        "patient_existant": patient_existant,
        "photo_temp_id": photo_temp_id,
        "photo_url": f"/uploads/ocr_temp/{photo_temp_id}{extension}",
    }
