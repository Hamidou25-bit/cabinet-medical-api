from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from datetime import datetime, timedelta
import bcrypt
import jwt
from database import get_db
from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(prefix="/auth", tags=["Authentification"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class LoginData(BaseModel):
    nom_utilisateur: str
    mot_de_passe: str


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/login")
def login(data: LoginData, db=Depends(get_db)):
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM utilisateurs WHERE nom_utilisateur = %s AND actif = true",
        (data.nom_utilisateur,)
    )
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect")

    if not bcrypt.checkpw(data.mot_de_passe.encode("utf-8"), user["mot_de_passe_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect")

    token = create_access_token({
        "sub": user["nom_utilisateur"],
        "role": user["role"],
        "id": user["id"]
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "nom_utilisateur": user["nom_utilisateur"],
        "role": user["role"]
    }


def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expirée, veuillez vous reconnecter")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide")


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {"user": user}


def require_role(*allowed_roles):
    def role_checker(user=Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Accès refusé pour ce rôle")
        return user
    return role_checker
