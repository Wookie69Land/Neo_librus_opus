from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from ninja import Router

from app.api.jwt_utils import decode_token
from app.api.serializers import (
    LibraryUserSchema,
    UserDetailSchema,
    UserUpdateSchema,
)
from app.domain.models import LibraryAdmin, LibraryUser, Reservation, SessionToken

router = Router(tags=["Users"])


def _parse_token(session_token: SessionToken) -> tuple[int, int, int]:
    """Extract (user_id, role_id, library_id) from the JWT stored in the token key."""
    claims = decode_token(session_token.key)
    return int(claims["sub"]), int(claims["role_id"]), int(claims["library_id"])


@router.get("/{user_id}", response={200: UserDetailSchema, 403: dict, 404: dict})
async def get_user(request, user_id: int):
    session: SessionToken = request.auth
    requester_id, role_id, _library_id = _parse_token(session)
    is_library_worker = role_id != 0

    if requester_id != user_id and not is_library_worker:
        return 403, {"detail": "Permission denied"}

    try:
        user = await LibraryUser.objects.aget(id=user_id)
    except LibraryUser.DoesNotExist:
        return 404, {"detail": "User not found"}

    library_roles = [
        {"library": la.library, "role": la.role}
        async for la in LibraryAdmin.objects.select_related("library", "role").filter(user_id=user_id)
    ]

    active_reservations = [
        r async for r in Reservation.objects.select_related(
            "status", "library", "book"
        ).filter(reader_id=user_id, end_time__isnull=True)
    ]

    return 200, UserDetailSchema(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        region=user.region,
        is_active=user.is_active,
        date_joined=user.date_joined,
        last_login=user.last_login,
        library_roles=library_roles,
        active_reservations=active_reservations,
    )


@router.put("/{user_id}", response={200: LibraryUserSchema, 403: dict, 404: dict, 422: dict})
async def update_user(request, user_id: int, payload: UserUpdateSchema):
    session: SessionToken = request.auth
    requester_id, _role_id, _library_id = _parse_token(session)

    if requester_id != user_id and not session.user.is_superuser:
        return 403, {"detail": "Permission denied"}

    try:
        user = await LibraryUser.objects.aget(id=user_id)
    except LibraryUser.DoesNotExist:
        return 404, {"detail": "User not found"}

    try:
        for field, value in payload.dict(exclude_none=True, exclude_unset=True).items():
            if field == "password":
                validate_password(value, user=user)
                user.set_password(value)
            else:
                setattr(user, field, value)
        await user.asave()
    except DjangoValidationError as exc:
        return 422, {"detail": exc.messages}

    return 200, user


@router.delete("/{user_id}", response={200: dict, 403: dict, 404: dict})
async def delete_user(request, user_id: int):
    session: SessionToken = request.auth
    requester_id, _role_id, _library_id = _parse_token(session)

    if requester_id != user_id and not session.user.is_superuser:
        return 403, {"detail": "Permission denied"}

    try:
        user = await LibraryUser.objects.aget(id=user_id)
    except LibraryUser.DoesNotExist:
        return 404, {"detail": "User not found"}

    await user.adelete()
    return 200, {"detail": "User deleted successfully"}

    return 200, {"detail": "User deleted successfully"}
