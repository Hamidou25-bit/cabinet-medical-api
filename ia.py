from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth import require_role
from config import GROQ_API_KEY
import httpx

router = APIRouter(prefix="/ia", tags=["IA"])


class Message(BaseModel):
    role: str  # "user" ou "assistant"
    content: str


class DiagnosticRequest(BaseModel):
    motif: str
    age: int | None = None
    sexe: str | None = None
    antecedents: str | None = None


class ChatMedicalRequest(BaseModel):
    messages: list[Message]
    motif: str | None = None
    age: int | None = None
    sexe: str | None = None
    antecedents: str | None = None


def _construire_system_prompt(motif, age, sexe, antecedents):
    return f"""Tu es un assistant médical expert qui aide les médecins au Cabinet BabaMouneissa au Mali (Afrique de l'Ouest).

Contexte patient :
- Motif de consultation : {motif or 'non précisé'}
- Âge : {age or 'non précisé'} ans
- Sexe : {sexe or 'non précisé'}
- Antécédents : {antecedents or 'aucun renseigné'}

Contexte géographique : Mali, Afrique de l'Ouest.
Maladies fréquentes : paludisme, typhoïde, infections respiratoires, diarrhées infectieuses, hypertension, diabète.

Pour chaque réponse tu dois :

1. DIAGNOSTICS POSSIBLES
   - Lister les 3 diagnostics les plus probables
   - Indiquer le pourcentage de probabilité pour chacun
   - Expliquer brièvement pourquoi

2. EXAMENS COMPLÉMENTAIRES
   - Liste précise et pratique des examens à demander
   - Préciser l'urgence (urgent / dans les 24h / peut attendre)

3. TRAITEMENT PROPOSÉ
   Pour chaque médicament, donner OBLIGATOIREMENT :
   - Nom du médicament (DCI + nom commercial si connu au Mali)
   - Forme : comprimé / sirop / injectable / sachet
   - Dosage exact : ex. 500mg, 250mg/5ml
   - Posologie complète : ex. "1 comprimé 3 fois par jour"
   - Durée : ex. "pendant 7 jours"
   - Voie d'administration : orale / intramusculaire / intraveineuse
   - Précautions : contre-indications importantes si nécessaire

   Exemple de format attendu :
   💊 Paracétamol (Doliprane) — comprimé 500mg
      → 2 comprimés (1g) toutes les 6h — voie orale — 5 jours
      → Ne pas dépasser 4g/jour

   💊 Arthémether-Luméfantrine (Coartem) — comprimé 20mg/120mg
      → 4 comprimés à H0, H8, H24, H36, H48, H60
      → Prendre avec un aliment gras
      → Contre-indiqué 1er trimestre grossesse

4. SIGNES D'ALARME
   - Signes qui doivent amener le patient à revenir immédiatement
   - Signes de gravité à surveiller

5. SUIVI
   - Date de contrôle recommandée
   - Évolution attendue sous traitement

Réponds toujours en français.
Sois précis, pratique et adapté au contexte africain (médicaments disponibles au Mali).
IMPORTANT : Rappelle toujours que c'est une aide et que le médecin reste seul responsable de la décision clinique finale."""


async def _appeler_groq(messages):
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": messages,
                    "max_tokens": 2048,
                    "temperature": 0.2,
                },
            )
    except httpx.RequestError:
        raise HTTPException(status_code=500, detail="Service IA inaccessible")

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Erreur service IA")

    result = response.json()
    return result["choices"][0]["message"]["content"]


@router.post("/chat")
async def chat_medical(data: ChatMedicalRequest, user=Depends(require_role("admin", "medecin"))):
    system_prompt = _construire_system_prompt(data.motif, data.age, data.sexe, data.antecedents)
    groq_messages = [{"role": "system", "content": system_prompt}]
    groq_messages += [{"role": m.role, "content": m.content} for m in data.messages]
    texte = await _appeler_groq(groq_messages)
    return {"response": texte}


@router.post("/diagnostic")
async def aide_diagnostic(data: DiagnosticRequest, user=Depends(require_role("admin", "medecin"))):
    system_prompt = _construire_system_prompt(data.motif, data.age, data.sexe, data.antecedents)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Motif de consultation : {data.motif}"},
    ]
    texte = await _appeler_groq(messages)
    return {"diagnostic": texte}
