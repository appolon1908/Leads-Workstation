import os
import unittest
from unittest.mock import patch

from leads_workstation.auth import (
    AuthenticationError,
    authenticate,
    can_access_lead,
    permissions_for,
)


class MiddlewareServiceAuthTests(unittest.TestCase):
    def service_env(self):
        return {
            "LEADS_AUTH_MODE": "service",
            "LEADS_SERVICE_TOKEN": "unit-test-token",
            "LEADS_SERVICE_ALLOWED_CIDRS": "172.19.0.0/16,172.21.0.0/16",
            "LEADS_SERVICE_SUBJECT": "middleware-staging",
            "LEADS_SERVICE_CAMPAIGNS": "*",
        }

    def test_valid_internal_service_auth(self):
        with patch.dict(os.environ, self.service_env(), clear=False):
            ctx = authenticate(
                {"Authorization": "Bearer unit-test-token"},
                "172.19.0.4",
            )
        self.assertEqual(ctx.subject, "middleware-staging")
        self.assertEqual(ctx.roles, frozenset({"middleware_service"}))
        self.assertEqual(ctx.campaign_ids, frozenset({"*"}))
        self.assertTrue(
            can_access_lead(
                ctx,
                {
                    "lead_id": "lead-1",
                    "campaign_id": "campaign-any",
                    "assigned_agent": "agent-other",
                },
            )
        )

    def test_service_auth_rejects_bad_token(self):
        with (
            patch.dict(os.environ, self.service_env(), clear=False),
            self.assertRaises(AuthenticationError),
        ):
            authenticate(
                {"Authorization": "Bearer wrong-token"},
                "172.19.0.4",
            )

    def test_service_auth_rejects_disallowed_source(self):
        with (
            patch.dict(os.environ, self.service_env(), clear=False),
            self.assertRaises(AuthenticationError),
        ):
            authenticate(
                {"Authorization": "Bearer unit-test-token"},
                "203.0.113.10",
            )

    def test_service_auth_requires_explicit_cidr_allowlist(self):
        env = self.service_env()
        env["LEADS_SERVICE_ALLOWED_CIDRS"] = ""
        with (
            patch.dict(os.environ, env, clear=False),
            self.assertRaises(AuthenticationError),
        ):
            authenticate(
                {"Authorization": "Bearer unit-test-token"},
                "172.19.0.4",
            )

    def test_middleware_service_is_least_privilege(self):
        permissions = permissions_for({"middleware_service"})
        self.assertIn("lead:read", permissions)
        self.assertIn("lead:update", permissions)
        self.assertIn("lead:assign", permissions)
        self.assertIn("campaign:read", permissions)
        self.assertNotIn("campaign:create", permissions)
        self.assertNotIn("campaign:update", permissions)
        self.assertNotIn("campaign:member", permissions)
        self.assertNotIn("webhook:manage", permissions)


if __name__ == "__main__":
    unittest.main()
