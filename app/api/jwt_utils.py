"""JWT encode/decode helpers for SessionToken.key."""
from typing import Any

import jwt
from django.conf import settings

ALGORITHM = "HS256"


def encode_token(payload: dict[str, Any]) -> str:
    """Encode a dict payload into a signed JWT string.

    PyJWT validates the registered ``sub`` claim as a string during decode,
    so normalize it here before signing new tokens.
    """
    normalized_payload = dict(payload)
    if "sub" in normalized_payload:
        normalized_payload["sub"] = str(normalized_payload["sub"])

    return jwt.encode(normalized_payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode a signed JWT string back into its payload dict.

    Raises jwt.PyJWTError on invalid/tampered tokens.
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"verify_sub": False},
    )
