import os
import unittest
from unittest.mock import patch

from leads_workstation.api import validate_network_binding


class NetworkBindingTests(unittest.TestCase):
    def test_loopback_always_allowed(self):
        with patch.dict(os.environ, {"LEADS_AUTH_MODE": "closed"}, clear=False):
            validate_network_binding("127.0.0.1", False)

    def test_non_loopback_requires_allow_network(self):
        with self.assertRaises(SystemExit):
            validate_network_binding("0.0.0.0", False)

    def test_keycloak_allows_network_binding(self):
        with patch.dict(os.environ, {"LEADS_AUTH_MODE": "keycloak"}, clear=False):
            validate_network_binding("0.0.0.0", True)

    def test_configured_service_auth_allows_network_binding(self):
        env = {
            "LEADS_AUTH_MODE": "service",
            "LEADS_SERVICE_TOKEN": "service-token",
            "LEADS_SERVICE_ALLOWED_CIDRS": "172.19.0.0/16,172.21.0.0/16",
        }
        with patch.dict(os.environ, env, clear=False):
            validate_network_binding("0.0.0.0", True)

    def test_service_auth_missing_token_fails_closed(self):
        env = {
            "LEADS_AUTH_MODE": "service",
            "LEADS_SERVICE_TOKEN": "",
            "LEADS_SERVICE_ALLOWED_CIDRS": "172.19.0.0/16",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            self.assertRaises(SystemExit),
        ):
            validate_network_binding("0.0.0.0", True)

    def test_service_auth_invalid_cidr_fails_closed(self):
        env = {
            "LEADS_AUTH_MODE": "service",
            "LEADS_SERVICE_TOKEN": "service-token",
            "LEADS_SERVICE_ALLOWED_CIDRS": "not-a-network",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            self.assertRaises(SystemExit),
        ):
            validate_network_binding("0.0.0.0", True)

    def test_dev_auth_cannot_bind_network(self):
        with (
            patch.dict(os.environ, {"LEADS_AUTH_MODE": "dev"}, clear=False),
            self.assertRaises(SystemExit),
        ):
            validate_network_binding("0.0.0.0", True)


if __name__ == "__main__":
    unittest.main()
