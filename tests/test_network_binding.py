import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from leads_workstation.api import serve, validate_network_binding


class NetworkBindingTests(unittest.TestCase):
    def test_loopback_allowed_without_network_opt_in(self):
        with patch.dict(os.environ, {"LEADS_AUTH_MODE": "closed"}, clear=True):
            for host in ("127.0.0.1", "localhost", "::1"):
                with self.subTest(host=host):
                    validate_network_binding(host, False)

    def test_non_loopback_requires_allow_network_even_with_service_auth(self):
        env = {
            "LEADS_AUTH_MODE": "service",
            "LEADS_SERVICE_TOKEN": "service-token",
            "LEADS_SERVICE_ALLOWED_CIDRS": "172.19.0.0/16",
            "LEADS_SERVICE_CAMPAIGNS": "*",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            self.assertRaises(SystemExit),
        ):
            validate_network_binding("0.0.0.0", False)

    def test_keycloak_allows_network_binding(self):
        with patch.dict(os.environ, {"LEADS_AUTH_MODE": "keycloak"}, clear=True):
            validate_network_binding("0.0.0.0", True)

    def test_service_auth_rejects_missing_or_invalid_configuration(self):
        for token, cidrs in (
            (None, "172.19.0.0/16"),
            ("", "172.19.0.0/16"),
            (" \t", "172.19.0.0/16"),
            ("service-token", None),
            ("service-token", ""),
            ("service-token", " , \t,"),
            ("service-token", "not-a-network"),
            ("service-token", "172.19.0.0/16,not-a-network"),
        ):
            env = {"LEADS_AUTH_MODE": "service", "LEADS_SERVICE_CAMPAIGNS": "*"}
            if token is not None:
                env["LEADS_SERVICE_TOKEN"] = token
            if cidrs is not None:
                env["LEADS_SERVICE_ALLOWED_CIDRS"] = cidrs
            with (
                self.subTest(token=token, cidrs=cidrs),
                patch.dict(os.environ, env, clear=True),
                self.assertRaises(SystemExit),
            ):
                validate_network_binding("0.0.0.0", True)

    def test_service_network_binding_requires_explicit_campaign_scope(self):
        for scope in (None, "", " , \t,"):
            env = {
                "LEADS_AUTH_MODE": "service",
                "LEADS_SERVICE_TOKEN": "service-token",
                "LEADS_SERVICE_ALLOWED_CIDRS": "172.19.0.0/16",
            }
            if scope is not None:
                env["LEADS_SERVICE_CAMPAIGNS"] = scope
            with (
                self.subTest(scope=scope),
                patch.dict(os.environ, env, clear=True),
                self.assertRaises(SystemExit),
            ):
                validate_network_binding("0.0.0.0", True)

    def test_unconfigured_closed_dev_and_unknown_auth_cannot_bind_network(self):
        for mode in (None, "closed", "dev", "unknown"):
            env = {} if mode is None else {"LEADS_AUTH_MODE": mode}
            with (
                self.subTest(mode=mode),
                patch.dict(os.environ, env, clear=True),
                self.assertRaises(SystemExit),
            ):
                validate_network_binding("0.0.0.0", True)

    def test_configured_service_auth_reaches_server_startup(self):
        env = {
            "LEADS_AUTH_MODE": "service",
            "LEADS_SERVICE_TOKEN": "service-token",
            "LEADS_SERVICE_ALLOWED_CIDRS": "172.19.0.0/16,172.21.0.0/16",
            "LEADS_SERVICE_CAMPAIGNS": "campaign-a",
        }
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict(os.environ, env, clear=True),
            patch("leads_workstation.api.ThreadingHTTPServer") as server,
        ):
            try:
                serve(Path(temp) / "api.db", "0.0.0.0", 0, True)
            except SystemExit as exc:
                self.fail(f"configured service auth rejected before server startup: {exc}")
            self.assertEqual(server.call_args.args[0], ("0.0.0.0", 0))


if __name__ == "__main__":
    unittest.main()
