from fastapi import HTTPException


def require_fields(data: dict, fields: list):
    """Vérifie que les champs listés sont présents et non vides dans `data`."""
    missing = [f for f in fields if data.get(f) in (None, "", [])]
    if missing:
        raise HTTPException(status_code=400, detail=f"Champ(s) obligatoire(s) manquant(s) : {', '.join(missing)}")


def require_positive(data: dict, fields: list):
    """Vérifie que les champs numériques listés sont strictement positifs."""
    invalid = [f for f in fields if not isinstance(data.get(f), (int, float)) or data.get(f) <= 0]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Champ(s) invalide(s) (valeur positive requise) : {', '.join(invalid)}")
