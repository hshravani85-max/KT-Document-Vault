import sys
import os
import json
import sqlite3
import hashlib

sys.path.insert(0, r"C:\KT_Vault_V3")

import database
import storage_service
import key_management

def check_vault_health() -> dict:
    health = {
        "status": "HEALTHY",
        "timestamp": "",
        "checks": {
            "database": {"ok": False, "details": ""},
            "key_provider": {"ok": False, "key_id": "", "fingerprint": ""},
            "maintenance_mode": {"active": False},
            "storage": {"ok": False, "doc_count": 0}
        }
    }

    import datetime
    health["timestamp"] = datetime.datetime.now().isoformat()

    # 1. Database check
    try:
        conn = database.get_connection()
        res = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if res and res[0] == "ok":
            health["checks"]["database"]["ok"] = True
            health["checks"]["database"]["details"] = "PRAGMA integrity_check passed"
        else:
            health["status"] = "UNHEALTHY"
            health["checks"]["database"]["details"] = f"Integrity error: {res}"
    except Exception as e:
        health["status"] = "UNHEALTHY"
        health["checks"]["database"]["details"] = str(e)

    # 2. Key provider check
    try:
        keys_dir = os.path.join(r"C:\KT_Vault_V3\documents", ".keys")
        provider = key_management.WindowsDPAPIKeyProvider(keys_dir=keys_dir)
        active_key = "ktv_2026_v1"
        if provider.has_key(active_key):
            key_bytes = provider.get_key(active_key)
            fp = key_management.KeyEscrowService.compute_fingerprint(key_bytes)
            health["checks"]["key_provider"]["ok"] = True
            health["checks"]["key_provider"]["key_id"] = active_key
            health["checks"]["key_provider"]["fingerprint"] = fp
            if fp != "eb3dbffe98475f7a":
                health["status"] = "DEGRADED"
                health["checks"]["key_provider"]["details"] = "Fingerprint differs from verified primary key"
        else:
            health["status"] = "UNHEALTHY"
            health["checks"]["key_provider"]["details"] = f"Key '{active_key}' not found"
    except Exception as e:
        health["status"] = "UNHEALTHY"
        health["checks"]["key_provider"]["details"] = str(e)

    # 3. Maintenance mode check
    try:
        m_mode = storage_service.is_maintenance_mode()
        health["checks"]["maintenance_mode"]["active"] = m_mode
        if m_mode:
            health["status"] = "MAINTENANCE"
    except Exception as e:
        health["checks"]["maintenance_mode"]["details"] = str(e)

    # 4. Storage check
    try:
        docs_dir = r"C:\KT_Vault_V3\documents"
        if os.path.exists(docs_dir) and os.path.isdir(docs_dir):
            file_count = len([f for f in os.listdir(docs_dir) if os.path.isfile(os.path.join(docs_dir, f))])
            health["checks"]["storage"]["ok"] = True
            health["checks"]["storage"]["doc_count"] = file_count
        else:
            health["status"] = "UNHEALTHY"
            health["checks"]["storage"]["details"] = "Documents directory missing"
    except Exception as e:
        health["status"] = "UNHEALTHY"
        health["checks"]["storage"]["details"] = str(e)

    return health

if __name__ == "__main__":
    result = check_vault_health()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] in ("HEALTHY", "MAINTENANCE") else 1)
