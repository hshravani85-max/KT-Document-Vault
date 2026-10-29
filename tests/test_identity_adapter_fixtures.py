import unittest
import os
import sys
import time

PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import auth_services
from auth_services import EntraIDAuthAdapter, LocalAuthAdapter, get_identity_adapter

class TestIdentityAdapterFixtures(unittest.TestCase):
    """
    Validates Microsoft Entra ID / OIDC enterprise authentication adapter
    using isolated synthetic fixtures without requiring external cloud connectivity.
    """

    def setUp(self):
        self.tenant_id = "test-tenant-1111-2222-3333"
        self.client_id = "test-client-aaaa-bbbb-cccc"
        self.adapter = EntraIDAuthAdapter(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret="test_synthetic_secret_xyz",
            redirect_uri="https://vault.khannatravels.internal/oauth2/callback"
        )

    def test_01_configuration_state(self):
        self.assertTrue(self.adapter.is_configured())
        unconfigured = EntraIDAuthAdapter(tenant_id="", client_id="")
        self.assertFalse(unconfigured.is_configured())

    def test_02_authorization_url_generation(self):
        auth_url = self.adapter.get_authorization_url(
            state="test_state_123",
            code_challenge="pkce_challenge_abc",
            nonce="nonce_val_999"
        )
        self.assertIn("https://login.microsoftonline.com/test-tenant-1111-2222-3333/oauth2/v2.0/authorize", auth_url)
        self.assertIn("client_id=test-client-aaaa-bbbb-cccc", auth_url)
        self.assertIn("state=test_state_123", auth_url)
        self.assertIn("code_challenge=pkce_challenge_abc", auth_url)
        self.assertIn("code_challenge_method=S256", auth_url)
        self.assertIn("nonce=nonce_val_999", auth_url)

    def test_03_logout_url_generation(self):
        logout_url = self.adapter.get_logout_url(
            post_logout_redirect_uri="https://vault.khannatravels.internal/login"
        )
        self.assertIn("https://login.microsoftonline.com/test-tenant-1111-2222-3333/oauth2/v2.0/logout", logout_url)
        self.assertIn("post_logout_redirect_uri=", logout_url)

    def test_04_role_mapping_success(self):
        # Admin group
        claims_admin = {"groups": ["KT-Vault-Admins"], "preferred_username": "admin@khannatravels.com"}
        self.assertEqual(self.adapter.map_claims_to_role(claims_admin), "Administrator")

        # Operations group
        claims_ops = {"groups": ["KT-Vault-Operations"], "preferred_username": "ops@khannatravels.com"}
        self.assertEqual(self.adapter.map_claims_to_role(claims_ops), "Operations")

        # Visa group
        claims_visa = {"groups": ["KT-Vault-Visa"], "preferred_username": "visa@khannatravels.com"}
        self.assertEqual(self.adapter.map_claims_to_role(claims_visa), "Visa")

        # Ticketing group
        claims_ticket = {"groups": ["KT-Vault-Ticketing"], "preferred_username": "ticket@khannatravels.com"}
        self.assertEqual(self.adapter.map_claims_to_role(claims_ticket), "Ticketing")

        # Sales group
        claims_sales = {"groups": ["KT-Vault-Sales"], "preferred_username": "sales@khannatravels.com"}
        self.assertEqual(self.adapter.map_claims_to_role(claims_sales), "Sales")

        # Auditor group
        claims_auditor = {"groups": ["KT-Vault-Auditors"], "preferred_username": "audit@khannatravels.com"}
        self.assertEqual(self.adapter.map_claims_to_role(claims_auditor), "Read-only Auditor")

    def test_05_role_mapping_fail_closed(self):
        # Unrecognized group
        claims_unknown = {"groups": ["KT-Finance-General"], "preferred_username": "finance@khannatravels.com"}
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.map_claims_to_role(claims_unknown)
        self.assertIn("does not belong to an authorized KT Vault security group", str(ctx.exception))

        # Empty groups
        claims_empty = {"groups": [], "preferred_username": "nobody@khannatravels.com"}
        with self.assertRaises(PermissionError):
            self.adapter.map_claims_to_role(claims_empty)

    def test_06_token_claims_validation(self):
        now = time.time()
        valid_claims = {
            "aud": self.client_id,
            "iss": f"https://login.microsoftonline.com/{self.tenant_id}/v2.0",
            "exp": now + 3600,
            "nbf": now - 10,
            "nonce": "nonce_test_xyz",
            "preferred_username": "staff@khannatravels.com"
        }

        # Valid token
        res = self.adapter.validate_id_token_claims(valid_claims, expected_nonce="nonce_test_xyz")
        self.assertEqual(res["preferred_username"], "staff@khannatravels.com")

        # Expired token
        expired_claims = valid_claims.copy()
        expired_claims["exp"] = now - 500
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.validate_id_token_claims(expired_claims)
        self.assertIn("expired", str(ctx.exception).lower())

        # Audience mismatch
        wrong_aud = valid_claims.copy()
        wrong_aud["aud"] = "wrong-client-id"
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.validate_id_token_claims(wrong_aud)
        self.assertIn("audience mismatch", str(ctx.exception).lower())

        # Issuer mismatch
        wrong_iss = valid_claims.copy()
        wrong_iss["iss"] = "https://login.microsoftonline.com/malicious-tenant-id/v2.0"
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.validate_id_token_claims(wrong_iss)
        self.assertIn("issuer", str(ctx.exception).lower())

    def test_07_factory_provider_fallback(self):
        # Default environment returns LocalAuthAdapter
        orig_val = os.environ.get("KT_AUTH_PROVIDER")
        try:
            if "KT_AUTH_PROVIDER" in os.environ:
                del os.environ["KT_AUTH_PROVIDER"]
            adapter = get_identity_adapter()
            self.assertIsInstance(adapter, LocalAuthAdapter)

            # Explicit 'entra_id' returns EntraIDAuthAdapter
            os.environ["KT_AUTH_PROVIDER"] = "entra_id"
            os.environ["AZURE_TENANT_ID"] = "tenant_env_123"
            os.environ["AZURE_CLIENT_ID"] = "client_env_456"
            adapter_entra = get_identity_adapter()
            self.assertIsInstance(adapter_entra, EntraIDAuthAdapter)
            self.assertEqual(adapter_entra.tenant_id, "tenant_env_123")
        finally:
            if orig_val is not None:
                os.environ["KT_AUTH_PROVIDER"] = orig_val
            elif "KT_AUTH_PROVIDER" in os.environ:
                del os.environ["KT_AUTH_PROVIDER"]
            if "AZURE_TENANT_ID" in os.environ:
                del os.environ["AZURE_TENANT_ID"]
            if "AZURE_CLIENT_ID" in os.environ:
                del os.environ["AZURE_CLIENT_ID"]

if __name__ == "__main__":
    unittest.main()
