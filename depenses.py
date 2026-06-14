from fastapi import APIRouter, Depends
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/depenses", tags=["Dépenses"])


@router.get("/")
def get_depenses(db=Depends(get_db), user=Depends(get_current_user)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT id_depense, date_depense, type_depense, montant, description
        FROM depense
        ORDER BY date_depense DESC, id_depense DESC
    """)
    return cursor.fetchall()
