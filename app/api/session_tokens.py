from __future__ import annotations

import secrets

from app.api.jwt_utils import encode_token
from app.domain.models import LibraryAdmin, LibraryUser, SessionToken


async def get_user_role_context(user: LibraryUser) -> tuple[int, int]:
    library_admin = await LibraryAdmin.objects.filter(user=user).order_by("added_at").alast()
    if library_admin is None:
        return 0, 0

    return library_admin.role_id, library_admin.library_id


async def issue_user_session_token(user: LibraryUser) -> str:
    role_id, library_id = await get_user_role_context(user)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "region": user.region,
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        "role_id": role_id,
        "library_id": library_id,
        "jti": secrets.token_hex(16),
    }
    token_key = encode_token(payload)
    await SessionToken.objects.aupdate_or_create(user=user, defaults={"key": token_key})
    return token_key