"""JWT encode/decode helpers for SessionToken.key."""
import jwt
from django.conf import settings

ALGORITHM = "HS256"


def encode_token(payload: dict) -> str:
    """Encode a dict payload into a signed JWT string."""
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode a signed JWT string back into its payload dict.

    Raises jwt.PyJWTError on invalid/tampered tokens.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
