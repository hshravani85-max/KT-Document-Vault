# KHANNA TRAVELS — KT VAULT V3
## Production Deployment, HTTPS & Network Hardening Guide

**Status:** READY FOR CONFIGURATION (Engineering Complete; Domain / TLS Certificate Required)  
**Host Architecture:** Windows Server 2022 / Windows 11 Enterprise (64-bit)  
**Application Server:** Streamlit on Python 3.14  
**Cryptography Provider:** Windows Data Protection API (DPAPI) + AES-256-GCM (KTV2 Envelopes)  

---

### 1. Architectural Overview & Network Isolation

```
[ Client Browser ]
        |
        |  HTTPS (Port 443 - TLS 1.3 / HSTS / WSS)
        v
[ Caddy / NGINX Reverse Proxy ]
        |
        |  HTTP (Loopback: 127.0.0.1:8501)
        v
[ Streamlit App Service (KTVaultV3) ]
        |
   +----+--------------------+
   |                         |
   v                         v
[ SQLite DB ]      [ DPAPI Vault Storage ]
(kt_vault_v3.db)    (documents/ + .keys/)
```

#### Core Security Boundary Rules:
1. **No Direct Public Port Exposure**: Streamlit is bound strictly to `127.0.0.1:8501` via [`.streamlit/config.toml`](file:///C:/KT_Vault_V3/.streamlit/config.toml). It must NEVER bind to `0.0.0.0` or be directly accessible over external networks.
2. **Mandatory TLS Termination**: All external and LAN traffic must terminate at a reverse proxy (Caddy or NGINX) enforcing TLS 1.2/1.3 and HSTS (`max-age=31536000`).
3. **Windows DPAPI Compatibility**: KT Vault master keys are protected using Windows DPAPI (`CryptProtectData`). The background application process must run under a Windows security context (local user account or managed service account) that preserves a persistent Windows user profile. A generic Linux container cannot decrypt DPAPI master keys.

---

### 2. Reverse Proxy Setup (Choose Option A or Option B)

#### Option A: Caddy (Recommended — Automated TLS)
1. Download Caddy for Windows from [caddyserver.com](https://caddyserver.com/).
2. Place `caddy.exe` in `C:\KT_Vault_V3\tools\`.
3. Use the production configuration template at [`deployment/caddy/Caddyfile`](file:///C:/KT_Vault_V3/deployment/caddy/Caddyfile).
4. Run:
   ```powershell
   caddy.exe run --config C:\KT_Vault_V3\deployment\caddy\Caddyfile
   ```

#### Option B: NGINX for Windows
1. Download NGINX for Windows.
2. Obtain or generate your organization's SSL/TLS certificate (`vault_server.crt` and `vault_server.key`) and place them in `C:\KT_Vault_V3\certs\`.
3. Use the configuration template at [`deployment/nginx/nginx.conf`](file:///C:/KT_Vault_V3/deployment/nginx/nginx.conf).
4. Run:
   ```powershell
   nginx.exe -c C:\KT_Vault_V3\deployment\nginx\nginx.conf
   ```

---

### 3. Windows Service Deployment

To run KT Vault automatically on Windows startup:
1. Open PowerShell as Administrator.
2. Review [`deployment/windows_service/install_kt_vault_service.ps1`](file:///C:/KT_Vault_V3/deployment/windows_service/install_kt_vault_service.ps1).
3. Execute:
   ```powershell
   & "C:\KT_Vault_V3\deployment\windows_service\install_kt_vault_service.ps1"
   ```
4. Verify service status:
   ```powershell
   Get-Service KTVaultV3
   ```

---

### 4. Health Checks and Monitoring

Automated health checks should be polled periodically (e.g., every 60 seconds) by network monitoring tools:
```powershell
& 'C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe' C:\KT_Vault_V3\deployment\health_check.py
```
Expected output:
```json
{
  "status": "HEALTHY",
  "checks": {
    "database": { "ok": true, "details": "PRAGMA integrity_check passed" },
    "key_provider": { "ok": true, "key_id": "ktv_2026_v1", "fingerprint": "eb3dbffe98475f7a" },
    "maintenance_mode": { "active": false },
    "storage": { "ok": true, "doc_count": 29 }
  }
}
```

---

### 5. Deployment Rollback Procedure

If an update fails:
1. Stop the service: `Stop-Service KTVaultV3`
2. Restore the database and code from the latest verified checkpoint:
   ```powershell
   Copy-Item C:\KT_Vault_V3\backups\checkpoint_final_hardening_20261027_105302\data\kt_vault_v3.db C:\KT_Vault_V3\data\kt_vault_v3.db -Force
   ```
3. Restart the service: `Start-Service KTVaultV3`
4. Confirm health: `python deployment/health_check.py`
