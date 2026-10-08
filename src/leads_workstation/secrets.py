from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


class SecretResolutionError(RuntimeError):
    pass


def resolve_secret(secret_ref: str) -> str:
    if secret_ref.startswith("env://"):
        name = secret_ref[len("env://") :]
        value = os.getenv(name)
        if not value:
            raise SecretResolutionError(f"environment secret is unavailable: {name}")
        return value

    if secret_ref.startswith("openbao://"):
        parsed = urllib.parse.urlsplit(secret_ref)
        # openbao://secret/path/to/item#field
        mount = parsed.netloc
        path = parsed.path.lstrip("/")
        field = parsed.fragment or "value"
        addr = os.getenv("OPENBAO_ADDR", "").rstrip("/")
        token = os.getenv("OPENBAO_TOKEN", "")
        if not addr or not token:
            raise SecretResolutionError("OPENBAO_ADDR and OPENBAO_TOKEN are required")
        url = f"{addr}/v1/{mount}/data/{path}"
        req = urllib.request.Request(
            url,
            headers={"X-Vault-Token": token, "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise SecretResolutionError("OpenBao secret lookup failed") from exc
        data = payload.get("data", {}).get("data", {})
        value = data.get(field)
        if value in (None, ""):
            raise SecretResolutionError(f"OpenBao field is unavailable: {field}")
        return str(value)

    raise SecretResolutionError(
        "secret_ref must use env://NAME or openbao://mount/path#field"
    )
