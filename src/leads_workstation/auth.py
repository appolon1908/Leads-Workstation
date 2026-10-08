from __future__ import annotations

import hmac
import ipaddress
import os
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache


class AuthenticationError(PermissionError):
    pass


class AuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class AuthContext:
    subject: str
    roles: frozenset[str]
    campaign_ids: frozenset[str]
    issuer: str | None = None

    def has_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))


PERMISSIONS = {
    "admin": {"*"},
    "super_user": {"*"},
    "supervisor": {
        "lead:read",
        "lead:create",
        "lead:update",
        "lead:assign",
        "lead:transition",
        "lead:contact",
        "lead:suppress",
        "lead:consent",
        "campaign:read",
        "campaign:update",
        "campaign:member",
        "audit:read",
        "outbox:read",
        "candidate:read",
        "candidate:promote",
    },
    "agent": {
        "lead:read",
        "lead:create",
        "lead:update",
        "lead:transition",
        "lead:contact",
        "campaign:read",
    },
    "importer": {
        "candidate:read",
        "candidate:stage",
        "candidate:promote",
        "lead:read",
    },
    "auditor": {
        "lead:read",
        "campaign:read",
        "audit:read",
        "outbox:read",
        "candidate:read",
    },
    "readonly": {
        "lead:read",
        "campaign:read",
        "candidate:read",
    },
    "middleware_service": {
        "lead:read",
        "lead:create",
        "lead:update",
        "lead:assign",
        "lead:transition",
        "lead:contact",
        "lead:suppress",
        "lead:consent",
        "campaign:read",
        "audit:read",
        "outbox:read",
        "candidate:read",
    },
}


def permissions_for(roles: Iterable[str]) -> set[str]:
    effective: set[str] = set()
    for role in roles:
        effective.update(PERMISSIONS.get(role, set()))
    return effective


def require_permission(ctx: AuthContext, permission: str) -> None:
    allowed = permissions_for(ctx.roles)
    if "*" in allowed or permission in allowed:
        return
    raise AuthorizationError(f"missing permission: {permission}")


def can_access_lead(ctx: AuthContext, lead: dict) -> bool:
    if ctx.has_role(
        "admin",
        "super_user",
        "auditor",
        "readonly",
        "importer",
        "middleware_service",
    ):
        return True
    campaign_id = lead.get("campaign_id")
    if ctx.has_role("supervisor"):
        return bool(campaign_id and campaign_id in ctx.campaign_ids)
    if ctx.has_role("agent"):
        return bool(
            lead.get("assigned_agent") == ctx.subject
            and campaign_id
            and campaign_id in ctx.campaign_ids
        )
    return False


def _header(headers, name: str) -> str:
    value = headers.get(name)
    return str(value or "").strip()


def _roles_from_claims(claims: dict, client_id: str | None) -> set[str]:
    roles = set(claims.get("realm_access", {}).get("roles", []) or [])
    if client_id:
        roles.update(
            claims.get("resource_access", {})
            .get(client_id, {})
            .get("roles", [])
            or []
        )
    return {str(r).strip() for r in roles if str(r).strip()}


def context_from_claims(claims: dict, client_id: str | None = None) -> AuthContext:
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise AuthenticationError("token has no subject")
    campaigns = claims.get("campaigns") or claims.get("campaign_ids") or []
    if isinstance(campaigns, str):
        campaigns = [c.strip() for c in campaigns.split(",") if c.strip()]
    return AuthContext(
        subject=subject,
        roles=frozenset(_roles_from_claims(claims, client_id)),
        campaign_ids=frozenset(str(c) for c in campaigns),
        issuer=claims.get("iss"),
    )


@lru_cache(maxsize=8)
def _cached_jwk_client(jwks_url: str):
    import jwt

    return jwt.PyJWKClient(
        jwks_url,
        cache_keys=True,
        lifespan=max(60, int(os.getenv("LEADS_JWKS_CACHE_SECONDS", "300"))),
    )


def _client_ip_allowed(client_ip: str, cidr_csv: str) -> bool:
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    networks = []
    for raw in cidr_csv.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            networks.append(ipaddress.ip_network(raw, strict=False))
        except ValueError as exc:
            raise AuthenticationError("invalid service CIDR configuration") from exc
    if not networks:
        raise AuthenticationError("service CIDR allowlist is required")
    return any(address in network for network in networks)


def authenticate(headers, client_ip: str) -> AuthContext:
    mode = os.getenv("LEADS_AUTH_MODE", "closed").strip().lower()

    if mode == "service":
        expected = os.getenv("LEADS_SERVICE_TOKEN", "")
        allowed_cidrs = os.getenv("LEADS_SERVICE_ALLOWED_CIDRS", "")
        if not expected or not allowed_cidrs:
            raise AuthenticationError("service auth token and CIDR allowlist must be configured")
        if not _client_ip_allowed(client_ip, allowed_cidrs):
            raise AuthenticationError("service caller address is not allowed")
        auth = _header(headers, "Authorization")
        if not auth.lower().startswith("bearer "):
            raise AuthenticationError("bearer token required")
        supplied = auth.split(None, 1)[1]
        if not hmac.compare_digest(supplied, expected):
            raise AuthenticationError("invalid service token")
        subject = os.getenv("LEADS_SERVICE_SUBJECT", "middleware-service").strip()
        if not subject:
            raise AuthenticationError("service subject must be configured")
        campaigns_raw = os.getenv("LEADS_SERVICE_CAMPAIGNS", "*")
        campaigns = frozenset(
            value.strip()
            for value in campaigns_raw.split(",")
            if value.strip()
        )
        if not campaigns:
            raise AuthenticationError("service campaign scope must be configured")
        return AuthContext(
            subject=subject,
            roles=frozenset({"middleware_service"}),
            campaign_ids=campaigns,
            issuer="internal-service",
        )

    if mode == "dev":
        if client_ip not in {"127.0.0.1", "::1", "localhost"}:
            raise AuthenticationError("development auth is loopback-only")
        subject = _header(headers, "X-Dev-User")
        if not subject:
            raise AuthenticationError("X-Dev-User is required in dev auth mode")
        roles = {
            r.strip()
            for r in _header(headers, "X-Dev-Roles").split(",")
            if r.strip()
        }
        campaigns = {
            c.strip()
            for c in _header(headers, "X-Dev-Campaigns").split(",")
            if c.strip()
        }
        return AuthContext(
            subject=subject,
            roles=frozenset(roles),
            campaign_ids=frozenset(campaigns),
            issuer="development",
        )

    if mode == "keycloak":
        auth = _header(headers, "Authorization")
        if not auth.lower().startswith("bearer "):
            raise AuthenticationError("bearer token required")
        token = auth.split(None, 1)[1]
        issuer = os.getenv("LEADS_KEYCLOAK_ISSUER", "").rstrip("/")
        audience = os.getenv("LEADS_KEYCLOAK_AUDIENCE", "")
        client_id = os.getenv("LEADS_KEYCLOAK_CLIENT_ID") or audience or None
        if not issuer or not audience:
            raise AuthenticationError("Keycloak issuer and audience must be configured")
        try:
            import jwt
        except ImportError as exc:
            raise AuthenticationError(
                "Keycloak auth requires the auth extra: pip install -e '.[auth]'"
            ) from exc

        jwks_url = os.getenv(
            "LEADS_KEYCLOAK_JWKS_URL",
            issuer + "/protocol/openid-connect/certs",
        )
        try:
            jwk_client = _cached_jwk_client(jwks_url)
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "RS384", "RS512"],
                audience=audience,
                issuer=issuer,
                leeway=max(0, int(os.getenv("LEADS_JWT_LEEWAY_SECONDS", "30"))),
                options={"require": ["exp", "iat", "sub"]},
            )
            authorized_party = str(claims.get("azp") or "").strip()
            if authorized_party and client_id and authorized_party != client_id:
                raise AuthenticationError("token authorized party does not match client")
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError("invalid bearer token") from exc
        return context_from_claims(claims, client_id)

    raise AuthenticationError(
        "V2 API is fail-closed. Set LEADS_AUTH_MODE=dev for loopback development, "
        "service for allowlisted internal service calls, or keycloak for authenticated operation."
    )
