from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth import require_role
from config import GROQ_API_KEY
import httpx

router = APIRouter(prefix="/ia", tags=["IA"])


class DiagnosticRequest(BaseModel):
    motif: str
    age: int | None = None
    sexe: str | None = None
    antecedents: str | None = None


@router.post("/diagnostic")
async def aide_diagnostic(data: DiagnosticRequest, user=Depends(require_role("admin", "medecin"))):
    prompt = f"""Tu es un assistant médical pour un médecin en Afrique de l'Ouest (Mali).

Patient : {data.age or 'âge inconnu'} ans, {data.sexe or 'sexe inconnu'}
Motif de consultation : {data.motif}
Antécédents : {data.antecedents or 'aucun renseigné'}

En tant qu'aide au diagnostic (pas un diagnostic définitif), propose :

1. DIAGNOSTICS POSSIBLES (liste les 3 plus probables avec pourcentage de probabilité)
2. EXAMENS COMPLÉMENTAIRES SUGGÉRÉS (liste courte et pratique)
3. TRAITEMENTS HABITUELS (médicaments courants avec posologie standard)
4. SIGNES D'ALARME à surveiller

Réponds en français, de façon concise et structurée.
IMPORTANT : Précise toujours que c'est une aide et que le médecin doit confirmer."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1024,
                    "temperature": 0.3,
                },
            )
    except httpx.RequestError:
        raise HTTPException(status_code=500, detail="Service IA inaccessible")

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Erreur service IA")

    result = response.json()
    texte = result["choices"][0]["message"]["content"]
    return {"diagnostic": texte}
