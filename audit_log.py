import json
from datetime import datetime
from fastapi import Request


def log_audit(db, request: Request, user: dict, action: str, table_name: str, record_id, details: dict | None = None):
    try:
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO audit_logs (user_id, username, action, table_name, record_id, details, ip_address, timestamp)
            VALUES (%(user_id)s, %(username)s, %(action)s, %(table_name)s, %(record_id)s, %(details)s, %(ip_address)s, %(timestamp)s)
        """, {
            "user_id": user.get("id"),
            "username": user.get("sub"),
            "action": action,
            "table_name": table_name,
            "record_id": record_id,
            "details": json.dumps(details or {}, default=str),
            "ip_address": request.client.host if request and request.client else None,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        })
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[audit_log] Échec d'écriture du log: {e}")
