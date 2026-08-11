from __future__ import annotations

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


_CONTEXT = b"libraryforge.integration-secrets.v1"


def _fernet() -> Fernet:
    digest = hashlib.sha256(
        _CONTEXT + str(settings.SECRET_KEY).encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secrets(value: dict[str, str]) -> str:
    payload = json.dumps(value, sort_keys=True).encode("utf-8")
    return _fernet().encrypt(payload).decode("ascii")


def decrypt_secrets(value: str) -> dict[str, str]:
    if not value:
        return {}

    try:
        payload = _fernet().decrypt(value.encode("ascii"))
    except (InvalidToken, ValueError) as exc:
        raise ValueError(
            "Integration secrets cannot be decrypted. Ensure DJANGO_SECRET_KEY has not changed."
        ) from exc

    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Integration secret payload is invalid.")

    return {
        str(key): str(item)
        for key, item in decoded.items()
        if item is not None
    }
