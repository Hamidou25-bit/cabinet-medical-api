from fastapi import APIRouter, Depends
from database import get_db
from auth import require_role

router = APIRouter(prefix="/audit-logs", tags=["Journal d'audit"])


@router.get("/")
def get_audit_logs(
    user_id: int | None = None,
    table_name: str | None = None,
    action: str | None = None,
    date_debut: str | None = None,
    date_fin: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db=Depends(get_db),
    user=Depends(require_role("admin")),
):
    conditions = []
    params = {}

    if user_id is not None:
        conditions.append("user_id = %(user_id)s")
        params["user_id"] = user_id
    if table_name:
        conditions.append("table_name = %(table_name)s")
        params["table_name"] = table_name
    if action:
        conditions.append("action = %(action)s")
        params["action"] = action
    if date_debut:
        conditions.append("timestamp >= %(date_debut)s")
        params["date_debut"] = date_debut
    if date_fin:
        conditions.append("timestamp <= %(date_fin)s")
        params["date_fin"] = date_fin + " 23:59:59"

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params["limit"] = limit
    params["offset"] = offset

    cursor = db.cursor()
    cursor.execute(f"""
        SELECT id, user_id, username, action, table_name, record_id, details, ip_address, timestamp
        FROM audit_logs
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """, params)
    return cursor.fetchall()


@router.delete("/")
def purge_audit_logs(db=Depends(get_db), user=Depends(require_role("admin"))):
    cursor = db.cursor()
    cursor.execute("DELETE FROM audit_logs")
    db.commit()
    return {"message": "Journal d'audit vidé"}
