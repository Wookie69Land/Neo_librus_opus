from ninja.errors import HttpError

from app.domain.models import LibraryAdmin, SessionToken


def get_authenticated_session(request) -> SessionToken:
    session = getattr(request, "auth", None)
    if session is None or not getattr(session, "user", None):
        raise HttpError(401, "Authentication credentials were not provided.")
    return session


async def require_library_admin_or_superuser(request) -> SessionToken:
    session = get_authenticated_session(request)
    if session.user.is_superuser:
        return session

    is_library_admin = await LibraryAdmin.objects.filter(user_id=session.user_id).aexists()
    if not is_library_admin:
        raise HttpError(403, "Permission denied")

    return session


def require_superuser(request) -> SessionToken:
    session = get_authenticated_session(request)
    if not session.user.is_superuser:
        raise HttpError(403, "Permission denied")
    return session


async def is_library_admin_for_library(user_id: int, library_id: int) -> bool:
    return await LibraryAdmin.objects.filter(user_id=user_id, library_id=library_id).aexists()


async def require_library_admin_for_library_or_superuser(
    request, library_id: int
) -> SessionToken:
    session = get_authenticated_session(request)
    if session.user.is_superuser:
        return session

    if not await is_library_admin_for_library(session.user_id, library_id):
        raise HttpError(403, "Permission denied")

    return session