
from ninja import Router
from ninja.errors import HttpError
from django.db.models import Exists, OuterRef
from django.utils import timezone

from app.api.permissions import (
    get_authenticated_session,
    is_library_admin_for_library,
)
from app.api.serializers import ReservationSchemaIn, ReservationSchemaOut, ReservationUpdateSchema
from app.domain.models import Book, Library, LibraryAdmin, LibraryBook, Reservation, Status
from app.domain.repositories import ReservationRepository

router = Router(tags=["Reservations"])
reservation_repo = ReservationRepository(Reservation)
DEFAULT_RESERVATION_STATUS_NAME = "pending"
ACCEPTED_RESERVATION_STATUS_NAME = "accepted"
PICKED_UP_RESERVATION_STATUS_NAME = "picked_up"
CLOSED_RESERVATION_STATUS_NAME = "closed"
ARCHIVED_RESERVATION_STATUS_NAME = "archived"
ALLOWED_STATUS_TRANSITIONS = {
    DEFAULT_RESERVATION_STATUS_NAME: {ACCEPTED_RESERVATION_STATUS_NAME, ARCHIVED_RESERVATION_STATUS_NAME},
    ACCEPTED_RESERVATION_STATUS_NAME: {PICKED_UP_RESERVATION_STATUS_NAME, ARCHIVED_RESERVATION_STATUS_NAME},
    PICKED_UP_RESERVATION_STATUS_NAME: {CLOSED_RESERVATION_STATUS_NAME, ARCHIVED_RESERVATION_STATUS_NAME},
    CLOSED_RESERVATION_STATUS_NAME: {ARCHIVED_RESERVATION_STATUS_NAME},
    ARCHIVED_RESERVATION_STATUS_NAME: set(),
}


async def _get_default_reservation_status() -> Status:
    status, _ = await Status.objects.aget_or_create(name=DEFAULT_RESERVATION_STATUS_NAME)
    return status


async def _get_status_by_name(status_name: str) -> Status:
    status, _ = await Status.objects.aget_or_create(name=status_name)
    return status


def _reservation_with_related_queryset():
    return Reservation.objects.select_related(
        "status", "reader", "librarian", "library", "book"
    ).prefetch_related("book__authors")


async def _get_reservation_for_response(reservation_id: int) -> Reservation:
    return await _reservation_with_related_queryset().aget(id=reservation_id)


async def _can_access_reservation(session, reservation: Reservation) -> bool:
    is_owner = reservation.reader_id == session.user_id
    is_library_admin = await is_library_admin_for_library(session.user_id, reservation.library_id)
    return is_owner or is_library_admin


def _is_transition_allowed(current_status_name: str, requested_status_name: str) -> bool:
    allowed_targets = ALLOWED_STATUS_TRANSITIONS.get(current_status_name, set())
    return requested_status_name in allowed_targets

@router.get("", response=list[ReservationSchemaOut])
async def list_reservations(request):
    session = get_authenticated_session(request)
    queryset = _reservation_with_related_queryset().exclude(
        status__name__iexact=ARCHIVED_RESERVATION_STATUS_NAME
    )

    if session.user.is_superuser:
        filtered_queryset = queryset
    else:
        admin_library_ids = [
            library_id
            async for library_id in LibraryAdmin.objects.filter(
                user_id=session.user_id
            ).values_list("library_id", flat=True)
        ]
        if admin_library_ids:
            filtered_queryset = queryset.filter(library_id__in=admin_library_ids)
        else:
            filtered_queryset = queryset.filter(reader_id=session.user_id)

    reservations = [reservation async for reservation in filtered_queryset]
    return reservations

@router.post("", response=ReservationSchemaOut)
async def create_reservation(request, payload: ReservationSchemaIn):
    session = get_authenticated_session(request)
    book = await (
        Book.objects.filter(id=payload.book_id)
        .annotate(
            library_exists=Exists(Library.objects.filter(id=payload.library_id)),
            book_in_library=Exists(
                LibraryBook.objects.filter(
                    book_id=OuterRef("pk"), library_id=payload.library_id
                )
            ),
        )
        .afirst()
    )

    if book is None:
        raise HttpError(404, "Book not found")
    if not book.library_exists:
        raise HttpError(404, "Library not found")
    if not book.book_in_library:
        raise HttpError(422, "Book is not available in the selected library")

    status = await _get_default_reservation_status()
    reservation = await reservation_repo.create(
        reader_id=session.user_id, status_id=status.id, **payload.dict()
    )
    return await _get_reservation_for_response(reservation.id)

@router.get("/{reservation_id}", response=ReservationSchemaOut)
async def get_reservation(request, reservation_id: int):
    session = get_authenticated_session(request)
    try:
        reservation = await _get_reservation_for_response(reservation_id)
    except Reservation.DoesNotExist:
        raise HttpError(404, "Reservation not found")

    if not await _can_access_reservation(session, reservation):
        raise HttpError(403, "Permission denied")

    return reservation


@router.put("/{reservation_id}", response={200: ReservationSchemaOut, 403: dict, 404: dict, 422: dict})
async def update_reservation(request, reservation_id: int, payload: ReservationUpdateSchema):
    session = get_authenticated_session(request)
    try:
        reservation = await _reservation_with_related_queryset().aget(id=reservation_id)
    except Reservation.DoesNotExist:
        return 404, {"detail": "Reservation not found"}

    if not await is_library_admin_for_library(session.user_id, reservation.library_id):
        return 403, {"detail": "Permission denied"}

    update_data = payload.dict(exclude_unset=True)
    if "status_id" in update_data:
        status = await Status.objects.filter(id=update_data["status_id"]).afirst()
        if status is None:
            return 422, {"detail": "Status not found"}
        current_status_name = reservation.status.name.lower()
        requested_status_name = status.name.lower()

        if not _is_transition_allowed(current_status_name, requested_status_name):
            return 422, {"detail": "Invalid reservation status transition"}

        reservation.status_id = status.id
        reservation.librarian_id = session.user_id
        if requested_status_name == CLOSED_RESERVATION_STATUS_NAME and reservation.end_time is None:
            reservation.end_time = timezone.now()

    if "status_id" not in update_data and ("end_time" in update_data or "librarian_id" in update_data):
        return 422, {
            "detail": "Reservation status update is required when changing end_time or librarian"
        }

    await reservation.asave()
    return 200, await _get_reservation_for_response(reservation.id)

@router.delete("/{reservation_id}")
async def delete_reservation(request, reservation_id: int):
    session = get_authenticated_session(request)
    try:
        reservation = await _reservation_with_related_queryset().aget(id=reservation_id)
    except Reservation.DoesNotExist:
        raise HttpError(404, "Reservation not found")

    if not await is_library_admin_for_library(session.user_id, reservation.library_id):
        raise HttpError(403, "Permission denied")

    archived_status = await _get_status_by_name(ARCHIVED_RESERVATION_STATUS_NAME)
    reservation.status_id = archived_status.id
    reservation.librarian_id = session.user_id
    await reservation.asave(update_fields=["status", "librarian", "updated_at"])
    return {"success": True}
