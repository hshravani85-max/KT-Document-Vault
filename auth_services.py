"""
Khanna Travels - KT Vault V3
Authentication, Identity and Granular Access Control Service (auth_services.py)
Phase 16 Hardening: Multi-role RBAC, Account Lockout, Session Fixation Protection & SSO/MFA Adapters
"""

import sqlite3
import json
import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Set
import database

# =====================================================================
# Database Migration & Schema Initialization
# =====================================================================

def init_auth_schema(conn=None):
    """
    Safely ensures that all Phase 16 authentication, RBAC, and security
    audit columns and tables exist in the SQLite database.
    Idempotent and non-destructive.
    """
    should_close = False
    if conn is None:
        conn = database.get_connection()
        should_close = True

    try:
        c = conn.cursor()
        # Add columns to users table safely
        columns = [
            ("is_active", "INTEGER DEFAULT 1"),
            ("department", "TEXT DEFAULT 'General'"),
            ("failed_attempts", "INTEGER DEFAULT 0"),
            ("locked_until", "TEXT DEFAULT NULL"),
            ("mfa_enabled", "INTEGER DEFAULT 0"),
            ("auth_provider", "TEXT DEFAULT 'local'")
        ]
        for col_name, col_def in columns:
            try:
                c.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass  # Already exists

        # Create security audit log table
        c.execute("""
            CREATE TABLE IF NOT EXISTS security_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                username TEXT,
                user_id TEXT,
                role TEXT,
                ip_address TEXT,
                details TEXT
            )
        """)
        conn.commit()
    finally:
        if should_close:
            conn.close()

# Auto-initialize schema on module load
try:
    init_auth_schema()
except Exception:
    pass


# =====================================================================
# Security Audit Logging
# =====================================================================

def log_security_event(
    event_type: str,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    role: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: str = "127.0.0.1"
):
    """
    Records security-relevant events to the durable security_audit_logs table.
    Never records passwords, tokens, or encryption keys.
    """
    conn = database.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO security_audit_logs (event_type, username, user_id, role, ip_address, details, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event_type),
                username,
                user_id,
                role,
                ip_address,
                details,
                datetime.now().isoformat()
            )
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


# =====================================================================
# Granular Role-Based Access Control (RBAC) Specification
# =====================================================================

# The four core office departments with shared document access:
OFFICE_DEPARTMENTS = {"Sales", "Visa", "Operations", "Ticketing"}

# Authorized reviewers permitted to verify or reject travel documents:
AUTHORIZED_REVIEWER_ROLES = {"Administrator", "Operations", "Visa", "Ticketing", "Supervisor", "Admin"}

# System administrators with authority over deletion, users, keys, and security:
ADMIN_ROLES = {"Administrator", "Admin"}

# All office personnel permitted general document read, preview, download, and upload:
ALL_OFFICE_ROLES = OFFICE_DEPARTMENTS | ADMIN_ROLES | {"Staff", "Supervisor"}

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "Administrator": {
        "customer:view", "customer:create", "customer:edit",
        "document:view_metadata", "document:view_content", "document:download",
        "document:upload", "document:verify", "document:reopen", "document:version_history", "document:delete",
        "admin:access", "admin:user_manage", "admin:key_rotate", "admin:backup",
        "audit:view", "trip:view", "trip:create", "trip:edit", "pack:generate"
    },
    "Operations": {
        "customer:view", "customer:create", "customer:edit",
        "document:view_metadata", "document:view_content", "document:download",
        "document:upload", "document:verify", "document:reopen", "document:version_history",
        "trip:view", "trip:create", "trip:edit", "pack:generate"
    },
    "Visa": {
        "customer:view", "customer:create", "customer:edit",
        "document:view_metadata", "document:view_content", "document:download",
        "document:upload", "document:verify", "document:reopen", "document:version_history",
        "trip:view", "trip:create", "trip:edit", "pack:generate"
    },
    "Ticketing": {
        "customer:view", "customer:create", "customer:edit",
        "document:view_metadata", "document:view_content", "document:download",
        "document:upload", "document:verify", "document:reopen", "document:version_history",
        "trip:view", "trip:create", "trip:edit", "pack:generate"
    },
    "Sales": {
        "customer:view", "customer:create", "customer:edit",
        "document:view_metadata", "document:view_content", "document:download",
        "document:upload", "document:version_history",
        "trip:view", "trip:create", "trip:edit", "pack:generate"
    },
    "Read-only Auditor": {
        "customer:view",
        "document:view_metadata", "document:view_content",
        "trip:view",
        "audit:view"
    }
}

# Role aliases for backward compatibility with existing V3 data
ROLE_ALIASES = {
    "Admin": "Administrator",
    "Supervisor": "Operations",
    "Staff": "Sales"
}

def normalize_role(role: str) -> str:
    """Resolves role aliases to canonical Phase 16 role names."""
    if not role:
        return "Unknown"
    role_str = str(role).strip()
    return ROLE_ALIASES.get(role_str, role_str)

def get_role_permissions(role: str) -> Set[str]:
    """Returns the set of permission codes granted to the role."""
    canonical = normalize_role(role)
    return ROLE_PERMISSIONS.get(canonical, set())

def has_permission(user_or_token: Any, permission_code: str) -> bool:
    """
    Checks if a user dict or session token has the requested permission.
    Returns False if unauthenticated, inactive, or unauthorized.
    """
    if isinstance(user_or_token, str):
        user = get_user_by_token(user_or_token)
    elif isinstance(user_or_token, dict):
        user = user_or_token
    else:
        return False

    if not user or user.get("is_active", 1) == 0:
        return False

    role = user.get("role", "")
    perms = get_role_permissions(role)
    return permission_code in perms

def require_permission(token: str, permission_code: str) -> Dict[str, Any]:
    """
    Enforces a granular permission on a session token.
    Raises PermissionError with clear security audit logging if denied.
    """
    user = get_user_by_token(token)
    if not user:
        log_security_event("PERMISSION_DENIED_UNAUTHENTICATED", details=f"Attempted {permission_code}")
        raise PermissionError("Unauthenticated: Invalid or expired session.")

    if user.get("is_active", 1) == 0:
        log_security_event("PERMISSION_DENIED_DISABLED", username=user.get("username"), details=f"Attempted {permission_code}")
        raise PermissionError("Unauthorized: Account has been deactivated.")

    role = user.get("role", "")
    perms = get_role_permissions(role)
    if permission_code not in perms:
        log_security_event(
            "PERMISSION_DENIED",
            username=user.get("username"),
            user_id=user.get("id"),
            role=role,
            details=f"Missing required permission: '{permission_code}'"
        )
        raise PermissionError(f"Unauthorized: Role '{role}' lacks permission '{permission_code}'.")

    return user

def can_access_document(role: str, department: str = "", doc_name_or_type: str = "", action: str = "view") -> bool:
    """
    Validates document access based on the confirmed Khanna Travels office workflow:
    1. The four departments — Sales, Visa, Operations and Ticketing — ALL have full shared access
       to search, view, preview, download, and upload all customer and trip documents.
    2. There are NO document-type visibility restrictions between these four departments.
       (e.g., Ticketing can view/download passports & visas; Visa can view/download flight tickets).
    3. Document verification and rejection strictly require an authorized reviewer role
       (Administrator, Operations, Visa, Ticketing). Sales and Read-only Auditor are rejected.
    4. Document deletion is strictly restricted to Administrator.
    5. Read-only Auditor is restricted to viewing metadata and previewing content for compliance.
    """
    canonical_role = normalize_role(role)
    dept = (department or "").strip()

    # 1. Document deletion: Strictly Administrator-controlled
    if action == "delete":
        return canonical_role in ADMIN_ROLES

    # 2. Document verification / rejection: Strictly Authorized Reviewer-controlled
    if action in ("verify", "reject", "reopen"):
        return canonical_role in AUTHORIZED_REVIEWER_ROLES

    # 3. Document view, preview, download, upload:
    # All 4 departments (Sales, Visa, Operations, Ticketing) + Administrator have full shared access
    # across ALL document types (passports, visas, flight tickets, hotel vouchers, itineraries, etc.)
    if (canonical_role in ADMIN_ROLES or
        canonical_role in OFFICE_DEPARTMENTS or
        dept in OFFICE_DEPARTMENTS or
        role in ("Staff", "Supervisor")):
        return True

    # 4. Read-only Auditor: View-only metadata and content preview for audit purposes
    if canonical_role == "Read-only Auditor":
        return action in ("view", "preview", "view_metadata")

    return False


# =====================================================================
# Identity & Authentication Adapters (SSO / MFA Architecture)
# =====================================================================

class IdentityAdapter:
    """
    Abstract identity adapter interface for enterprise authentication.
    Allows KT Vault to transition from local authentication to external SSO (e.g. Entra ID).
    """
    def authenticate(self, username: str, password: str, **kwargs) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def verify_mfa(self, user_id: str, mfa_token: str) -> bool:
        raise NotImplementedError

    def get_user_claims(self, user_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError


class LocalAuthAdapter(IdentityAdapter):
    """
    Local database authentication adapter using PBKDF2-HMAC-SHA256,
    salt per user, account lockout protection, and session fixation guards.
    """

    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15

    def authenticate(self, username: str, password: str, **kwargs) -> Optional[Dict[str, Any]]:
        conn = database.get_connection()
        ip_address = kwargs.get("ip_address", "127.0.0.1")
        try:
            user = conn.execute(
                """
                SELECT id, username, password_hash, salt, full_name, role,
                       COALESCE(is_active, 1) as is_active,
                       COALESCE(department, 'General') as department,
                       COALESCE(failed_attempts, 0) as failed_attempts,
                       locked_until,
                       COALESCE(mfa_enabled, 0) as mfa_enabled,
                       COALESCE(auth_provider, 'local') as auth_provider
                FROM users WHERE username = ?
                """,
                (username,)
            ).fetchone()

            if not user:
                log_security_event("LOGIN_FAILED_UNKNOWN_USER", username=username, ip_address=ip_address)
                return None

            user_dict = dict(user)

            # 1. Check account active status
            if user_dict["is_active"] == 0:
                log_security_event(
                    "LOGIN_BLOCKED_DISABLED_ACCOUNT",
                    username=username,
                    user_id=user_dict["id"],
                    ip_address=ip_address
                )
                raise PermissionError("Account is disabled. Please contact the KT Vault administrator.")

            # 2. Check account lockout status
            locked_until_str = user_dict.get("locked_until")
            if locked_until_str:
                try:
                    locked_until_dt = datetime.fromisoformat(locked_until_str)
                    if datetime.now() < locked_until_dt:
                        remaining_min = int((locked_until_dt - datetime.now()).total_seconds() / 60) + 1
                        log_security_event(
                            "LOGIN_BLOCKED_LOCKED_ACCOUNT",
                            username=username,
                            user_id=user_dict["id"],
                            ip_address=ip_address,
                            details=f"Locked until {locked_until_str}"
                        )
                        raise PermissionError(
                            f"Account is temporarily locked due to repeated failed logins. "
                            f"Try again in {remaining_min} minute(s)."
                        )
                    else:
                        # Lockout expired, clear it
                        conn.execute("UPDATE users SET locked_until = NULL, failed_attempts = 0 WHERE id = ?", (user_dict["id"],))
                        conn.commit()
                        user_dict["failed_attempts"] = 0
                except ValueError:
                    pass

            user = user_dict
            # 3. Verify password hash using constant-time comparison
            pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), user['salt'], 100000)
            if not secrets.compare_digest(pwd_hash, user['password_hash']):
                # Increment failed attempts
                new_attempts = user_dict["failed_attempts"] + 1
                locked_until_val = None
                if new_attempts >= self.MAX_FAILED_ATTEMPTS:
                    locked_until_val = (datetime.now() + timedelta(minutes=self.LOCKOUT_MINUTES)).isoformat()
                    conn.execute(
                        "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                        (new_attempts, locked_until_val, user_dict["id"])
                    )
                    conn.commit()
                    log_security_event(
                        "ACCOUNT_LOCKED",
                        username=username,
                        user_id=user_dict["id"],
                        ip_address=ip_address,
                        details=f"Locked for {self.LOCKOUT_MINUTES} min after {new_attempts} failed attempts"
                    )
                    raise PermissionError(
                        f"Account locked: 5 consecutive failed login attempts reached. "
                        f"Locked for {self.LOCKOUT_MINUTES} minutes."
                    )
                else:
                    conn.execute(
                        "UPDATE users SET failed_attempts = ? WHERE id = ?",
                        (new_attempts, user_dict["id"])
                    )
                    conn.commit()
                    log_security_event(
                        "LOGIN_FAILED_PASSWORD_MISMATCH",
                        username=username,
                        user_id=user_dict["id"],
                        ip_address=ip_address,
                        details=f"Failed attempt {new_attempts}/{self.MAX_FAILED_ATTEMPTS}"
                    )
                return None

            # 4. Successful credentials verification: reset failed counters
            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?",
                (user_dict["id"],)
            )

            # 5. Session fixation prevention: invalidate previous active sessions for this user
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_dict["id"],))

            # 6. Issue cryptographically secure random session token
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=12)

            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_dict["id"], expires_at.isoformat())
            )
            conn.commit()

            log_security_event(
                "LOGIN_SUCCESS",
                username=username,
                user_id=user_dict["id"],
                role=user_dict["role"],
                ip_address=ip_address
            )

            return {
                'token': token,
                'user_id': user_dict['id'],
                'username': user_dict['username'],
                'full_name': user_dict['full_name'],
                'role': user_dict['role'],
                'canonical_role': normalize_role(user_dict['role']),
                'department': user_dict['department'],
                'is_active': user_dict['is_active'],
                'expires_at': expires_at.isoformat()
            }
        finally:
            conn.close()

    def verify_mfa(self, user_id: str, mfa_token: str) -> bool:
        # Local placeholder: production MFA should be delegated to Entra ID / external IdP
        return False

    def get_user_claims(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = database.get_connection()
        try:
            row = conn.execute(
                "SELECT id, username, full_name, role, department, is_active FROM users WHERE id = ?",
                (user_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


class EntraIDAuthAdapter(IdentityAdapter):
    """
    Microsoft Entra ID (Azure AD) SSO / MFA Adapter Interface.
    Prepared for enterprise OIDC / OAuth 2.0 PKCE authentication flow.
    Enforces enterprise MFA via Microsoft Conditional Access and OIDC role mapping.
    """
    DEFAULT_GROUP_ROLE_MAPPING = {
        "KT-Vault-Admins": "Administrator",
        "KT-Vault-Operations": "Operations",
        "KT-Vault-Visa": "Visa",
        "KT-Vault-Ticketing": "Ticketing",
        "KT-Vault-Sales": "Sales",
        "KT-Vault-Auditors": "Read-only Auditor"
    }

    def __init__(
        self,
        tenant_id: str = "",
        client_id: str = "",
        client_secret: Optional[str] = None,
        redirect_uri: str = "http://localhost:8501/oauth2/callback",
        group_role_mapping: Optional[Dict[str, str]] = None
    ):
        self.tenant_id = tenant_id.strip()
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip() if client_secret else None
        self.redirect_uri = redirect_uri.strip()
        self.group_role_mapping = group_role_mapping or self.DEFAULT_GROUP_ROLE_MAPPING.copy()

    @property
    def authority(self) -> str:
        tid = self.tenant_id or "common"
        return f"https://login.microsoftonline.com/{tid}"

    def is_configured(self) -> bool:
        return bool(self.tenant_id and self.client_id)

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: Optional[str] = None,
        code_challenge: Optional[str] = None,
        nonce: Optional[str] = None
    ) -> str:
        """
        Builds the Microsoft Entra ID OIDC v2.0 authorization URL.
        """
        if not self.is_configured():
            raise RuntimeError("Entra ID is not configured with AZURE_TENANT_ID and AZURE_CLIENT_ID.")

        target_redirect = redirect_uri or self.redirect_uri
        params = [
            ("client_id", self.client_id),
            ("response_type", "code"),
            ("redirect_uri", target_redirect),
            ("response_mode", "query"),
            ("scope", "openid profile email User.Read"),
            ("state", state)
        ]
        if code_challenge:
            params.append(("code_challenge", code_challenge))
            params.append(("code_challenge_method", "S256"))
        if nonce:
            params.append(("nonce", nonce))

        import urllib.parse
        qs = urllib.parse.urlencode(params)
        return f"{self.authority}/oauth2/v2.0/authorize?{qs}"

    def get_logout_url(self, post_logout_redirect_uri: Optional[str] = None) -> str:
        """
        Returns the Microsoft single logout endpoint URL.
        """
        target = post_logout_redirect_uri or self.redirect_uri
        import urllib.parse
        return f"{self.authority}/oauth2/v2.0/logout?post_logout_redirect_uri={urllib.parse.quote(target)}"

    def map_claims_to_role(self, claims: Dict[str, Any]) -> str:
        """
        Maps Entra ID token claims (groups or roles) to canonical KT Vault roles.
        Fails closed: if no matching group exists, raises PermissionError.
        """
        assigned_groups = set()
        # Check standard Entra ID claim locations
        if "groups" in claims and isinstance(claims["groups"], list):
            assigned_groups.update(claims["groups"])
        if "roles" in claims and isinstance(claims["roles"], list):
            assigned_groups.update(claims["roles"])
        if "wids" in claims and isinstance(claims["wids"], list):
            assigned_groups.update(claims["wids"])

        # Role priority order: Administrator > Operations > Visa > Ticketing > Sales > Read-only Auditor
        priority = ["Administrator", "Operations", "Visa", "Ticketing", "Sales", "Read-only Auditor"]
        
        matched_roles = set()
        for g in assigned_groups:
            if g in self.group_role_mapping:
                matched_roles.add(self.group_role_mapping[g])

        for r in priority:
            if r in matched_roles:
                return r

        # Fail closed: reject unauthorized users
        log_security_event(
            "SSO_ROLE_MAPPING_FAILED",
            username=claims.get("preferred_username") or claims.get("email"),
            details=f"User has claims with groups {list(assigned_groups)}, but none match KT Vault roles"
        )
        raise PermissionError(
            "Access Denied: Your enterprise account does not belong to an authorized KT Vault security group."
        )

    def validate_id_token_claims(
        self,
        claims: Dict[str, Any],
        expected_nonce: Optional[str] = None,
        clock_skew_seconds: int = 60
    ) -> Dict[str, Any]:
        """
        Validates standard JWT claims from Microsoft Entra ID.
        """
        import time
        now = time.time()

        # 1. Expiration check
        exp = claims.get("exp")
        if not exp or now > (float(exp) + clock_skew_seconds):
            raise PermissionError("OIDC token has expired.")

        # 2. Not before / issued at check
        nbf = claims.get("nbf", claims.get("iat"))
        if nbf and now < (float(nbf) - clock_skew_seconds):
            raise PermissionError("OIDC token is not yet valid.")

        # 3. Audience check
        aud = claims.get("aud")
        if aud != self.client_id:
            raise PermissionError(f"OIDC token audience mismatch (expected '{self.client_id}', got '{aud}').")

        # 4. Issuer check
        iss = claims.get("iss", "")
        if self.tenant_id and self.tenant_id not in iss:
            raise PermissionError(f"OIDC token issuer '{iss}' does not match tenant '{self.tenant_id}'.")

        # 5. Nonce check
        if expected_nonce and claims.get("nonce") != expected_nonce:
            raise PermissionError("OIDC token nonce mismatch.")

        return claims

    def authenticate(self, username: str, password: str, **kwargs) -> Optional[Dict[str, Any]]:
        if not self.is_configured():
            raise NotImplementedError(
                "Microsoft Entra ID is not yet configured. "
                "Requires AZURE_TENANT_ID and AZURE_CLIENT_ID environment settings."
            )
        # Delegated to OIDC redirect flow in web interface
        raise NotImplementedError("Direct password authentication is disabled for Entra ID SSO.")

    def verify_mfa(self, user_id: str, mfa_token: str) -> bool:
        # Managed natively by Microsoft Authenticator / Conditional Access Policies
        return True

    def get_user_claims(self, user_id: str) -> Optional[Dict[str, Any]]:
        return None


# Default adapter instance
_LOCAL_ADAPTER = LocalAuthAdapter()


def get_identity_adapter() -> IdentityAdapter:
    """
    Returns the active identity provider adapter based on configuration.
    Defaults to LocalAuthAdapter. Can be configured for EntraIDAuthAdapter via environment variables.
    """
    provider_type = os.environ.get("KT_AUTH_PROVIDER", "local").strip().lower()
    if provider_type in ("entra_id", "azure_ad", "oidc"):
        tenant_id = os.environ.get("AZURE_TENANT_ID", "")
        client_id = os.environ.get("AZURE_CLIENT_ID", "")
        client_secret = os.environ.get("AZURE_CLIENT_SECRET")
        redirect_uri = os.environ.get("OIDC_REDIRECT_URI", "http://localhost:8501/oauth2/callback")
        return EntraIDAuthAdapter(tenant_id, client_id, client_secret, redirect_uri)
    return _LOCAL_ADAPTER


# =====================================================================
# Public Service API (Preserves Full Backward Compatibility)
# =====================================================================

def authenticate_user(username: str, password: str, ip_address: str = "127.0.0.1") -> Optional[Dict[str, Any]]:
    """
    Authenticates a user against the active authentication adapter.
    Enforces lockout, status checks, and session fixation rotation.
    """
    if not username or not password:
        return None
    return _LOCAL_ADAPTER.authenticate(username.strip(), password, ip_address=ip_address)


def get_user_by_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the user associated with a session token.
    Validates expiration and user active status. Automatically revokes invalid sessions.
    """
    if not token or not isinstance(token, str):
        return None
        
    conn = database.get_connection()
    try:
        try:
            query = '''
                SELECT u.id, u.username, u.full_name, u.role,
                       u.is_active,
                       u.department,
                       s.expires_at 
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.token = ?
            '''
            session = conn.execute(query, (token.strip(),)).fetchone()
        except sqlite3.OperationalError as e:
            if "no such column" in str(e):
                fallback_query = '''
                    SELECT u.id, u.username, u.full_name, u.role,
                           s.expires_at 
                    FROM sessions s
                    JOIN users u ON s.user_id = u.id
                    WHERE s.token = ?
                '''
                session = conn.execute(fallback_query, (token.strip(),)).fetchone()
            else:
                raise

        if not session:
            return None

        session_dict = dict(session)
        if 'is_active' not in session_dict or session_dict['is_active'] is None:
            session_dict['is_active'] = 1
        if 'department' not in session_dict or not session_dict['department']:
            session_dict['department'] = 'General'

        # Check session expiration
        try:
            expires_at = datetime.fromisoformat(session_dict['expires_at'])
            if expires_at < datetime.now():
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                log_security_event("SESSION_EXPIRED", user_id=session_dict['id'], username=session_dict['username'])
                return None
        except Exception:
            return None

        # Check user active status (staff offboarding immediate revocation)
        if session_dict['is_active'] == 0:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            log_security_event("SESSION_REVOKED_DEACTIVATED_USER", user_id=session_dict['id'], username=session_dict['username'])
            return None

        session_dict['canonical_role'] = normalize_role(session_dict['role'])
        return session_dict
    finally:
        conn.close()


def logout(token: str):
    """
    Terminates the session and logs the logout event.
    """
    if not token:
        return
    conn = database.get_connection()
    try:
        user = conn.execute(
            "SELECT u.username, u.id FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token = ?",
            (token.strip(),)
        ).fetchone()
        conn.execute("DELETE FROM sessions WHERE token = ?", (token.strip(),))
        conn.commit()
        if user:
            log_security_event("LOGOUT", username=user["username"], user_id=user["id"])
    finally:
        conn.close()


def require_role(token: str, allowed_roles: List[str]) -> Dict[str, Any]:
    """
    Validates that the session token belongs to an active user with one of the allowed roles.
    Preserves backward compatibility with legacy role strings ('Admin', 'Supervisor', 'Staff')
    while mapping to canonical Phase 16 roles:
    - If allowed_roles contains 'Staff' or 'Sales': Grants access to all 4 office departments (ALL_OFFICE_ROLES).
    - If allowed_roles contains 'Supervisor' or 'Operations': Grants access to all authorized reviewers (AUTHORIZED_REVIEWER_ROLES).
    - If allowed_roles contains 'Admin' or 'Administrator': Strictly requires Administrator/Admin.
    """
    user = get_user_by_token(token)
    if not user:
        raise PermissionError("Unauthenticated: Invalid or expired session.")

    canonical_user_role = normalize_role(user['role'])
    
    # Expand allowed_roles using office hierarchy
    expanded_allowed = set()
    for r in allowed_roles:
        expanded_allowed.add(r)
        expanded_allowed.add(normalize_role(r))
        if r in ("Staff", "Sales"):
            expanded_allowed.update(ALL_OFFICE_ROLES)
        elif r in ("Supervisor", "Operations"):
            expanded_allowed.update(AUTHORIZED_REVIEWER_ROLES)
        elif r in ("Admin", "Administrator"):
            expanded_allowed.update(ADMIN_ROLES)

    if user['role'] not in expanded_allowed and canonical_user_role not in expanded_allowed:
        log_security_event(
            "ROLE_UNAUTHORIZED_ACCESS",
            username=user.get("username"),
            user_id=user.get("id"),
            role=user.get("role"),
            details=f"Required one of {allowed_roles}"
        )
        raise PermissionError(f"Unauthorized: Requires one of {allowed_roles}.")

    return user


def set_user_active_status(user_id: str, is_active: bool, admin_token: str) -> bool:
    """
    Enables or disables a user account (e.g. for staff offboarding).
    Requires Administrator permission.
    Immediately purges any active sessions if disabled.
    """
    require_permission(admin_token, "admin:user_manage")

    conn = database.get_connection()
    try:
        active_val = 1 if is_active else 0
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (active_val, user_id))
        if not is_active:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()

        admin = get_user_by_token(admin_token)
        log_security_event(
            "USER_STATUS_CHANGED",
            username=admin.get("username") if admin else "Admin",
            details=f"User {user_id} active set to {is_active}"
        )
        return True
    finally:
        conn.close()


def create_user_account(
    username: str,
    password: str,
    full_name: str,
    role: str,
    department: str = "General",
    admin_token: Optional[str] = None
) -> str:
    """
    Creates a new employee account with salt and PBKDF2 hash.
    Requires Administrator permission if admin_token is supplied.
    """
    if admin_token:
        require_permission(admin_token, "admin:user_manage")

    if not username or not password or not full_name or not role:
        raise ValueError("All user fields are required.")

    clean_user = username.strip().lower()
    salt = secrets.token_bytes(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    user_id = f"KT-U-{secrets.token_hex(4).upper()}"

    conn = database.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO users (id, username, password_hash, salt, full_name, role, is_active, department, auth_provider)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, 'local')
            """,
            (user_id, clean_user, pwd_hash, salt, full_name.strip(), role.strip(), department.strip())
        )
        conn.commit()
        log_security_event("USER_CREATED", username=clean_user, user_id=user_id, role=role)
        return user_id
    finally:
        conn.close()
