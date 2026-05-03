
from ninja import Router
from ninja.errors import HttpError
from django.db.models import Exists, OuterRef

from app.api.permissions import (
    get_authenticated_session,
    is_library_admin_for_library,
)
from app.api.serializers import ReservationSchemaIn, ReservationSchemaOut, ReservationUpdateSchema
from app.domain.models import Book, Library, LibraryAdmin, LibraryBook, Reservation, Status

router = Router(tags=["Reservations"])

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_EXPIRED = "expired"
STATUS_CANCELLED = "cancelled"
STATUS_CLOSED = "closed"

# Statuses an admin can transition a reservation into, keyed by current status
ADMIN_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    STATUS_PENDING: {STATUS_ACCEPTED, STATUS_REJECTED},
}

# Statuses from which a user is allowed to cancel their own reservation
USER_CANCELLABLE_STATUSES: set[str] = {STATUS_PENDING, STATUS_ACCEPTED}


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


@router.get(
    "",
    response=list[ReservationSchemaOut],
    summary="List reservations",
    description=(
        "Returns reservations visible to the caller. "
        "Regular users see only their own reservations. "
        "Library admins see reservations for their library. "
        "Superusers see all reservations."
    ),
)
async def list_reservations(request):
    session = get_authenticated_session(request)
    queryset = _reservation_with_related_queryset()

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


@router.post(
    "",
    response=ReservationSchemaOut,
    summary="Create a reservation",
    description=(
        "Creates a new reservation in **pending** status for the authenticated user. "
        "The book must exist in the selected library. "
        "Awaits library admin action within 48 hours, otherwise the system expires it automatically."
    ),
)
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

    status, _ = await Status.objects.aget_or_create(name=STATUS_PENDING)
    reservation = await Reservation.objects.acreate(
        reader_id=session.user_id, status_id=status.id, **payload.dict()
    )
    full_reservation = await _get_reservation_for_response(reservation.id)
    await full_reservation.anotify(STATUS_PENDING)
    return full_reservation


@router.get(
    "/{reservation_id}",
    response=ReservationSchemaOut,
    summary="Get a reservation",
    description="Returns a single reservation. Accessible by the reservation owner or a library admin of the reservation's library.",
)
async def get_reservation(request, reservation_id: int):
    session = get_authenticated_session(request)
    try:
        reservation = await _get_reservation_for_response(reservation_id)
    except Reservation.DoesNotExist:
        raise HttpError(404, "Reservation not found")

    if not await _can_access_reservation(session, reservation):
        raise HttpError(403, "Permission denied")

    return reservation


@router.put(
    "/{reservation_id}",
    response={200: ReservationSchemaOut, 403: dict, 404: dict, 422: dict},
    summary="Accept or reject a reservation (library admin only)",
    description=(
        "Library admins can transition a **pending** reservation to:\n\n"
        "- `accepted` (status_id: **2**) — the book is confirmed for the reader\n"
        "- `rejected` (status_id: **7**) — the request is declined\n\n"
        "No other transitions are permitted through this endpoint. "
        "Subsequent transitions (`accepted` → `closed`) are handled automatically by the system."
    ),
)
async def update_reservation(request, reservation_id: int, payload: ReservationUpdateSchema):
    session = get_authenticated_session(request)
    try:
        reservation = await _reservation_with_related_queryset().aget(id=reservation_id)
    except Reservation.DoesNotExist:
        return 404, {"detail": "Reservation not found"}

    if not await is_library_admin_for_library(session.user_id, reservation.library_id):
        return 403, {"detail": "Permission denied"}

    status = await Status.objects.filter(id=payload.status_id).afirst()
    if status is None:
        return 422, {"detail": "Status not found"}

    current_status_name = reservation.status.name.lower()
    requested_status_name = status.name.lower()

    allowed_targets = ADMIN_ALLOWED_TRANSITIONS.get(current_status_name, set())
    if requested_status_name not in allowed_targets:
        return 422, {"detail": "Invalid reservation status transition"}

    reservation.status_id = status.id
    reservation.librarian_id = session.user_id
    await reservation.asave(update_fields=["status_id", "librarian_id", "updated_at"])
    full_reservation = await _get_reservation_for_response(reservation.id)
    await full_reservation.anotify(status.name)
    return 200, full_reservation


@router.delete(
    "/{reservation_id}",
    response={200: dict, 403: dict, 404: dict, 422: dict},
    summary="Cancel a reservation (owner only)",
    description=(
        "Allows the reservation owner to cancel their own reservation. "
        "Cancellation is permitted only when the reservation is in **pending** or **accepted** status. "
        "The record is not deleted — its status is set to `cancelled`."
    ),
)
async def cancel_reservation(request, reservation_id: int):
    session = get_authenticated_session(request)
    try:
        reservation = await _reservation_with_related_queryset().aget(id=reservation_id)
    except Reservation.DoesNotExist:
        return 404, {"detail": "Reservation not found"}

    if reservation.reader_id != session.user_id:
        return 403, {"detail": "Permission denied"}

    current_status_name = reservation.status.name.lower()
    if current_status_name not in USER_CANCELLABLE_STATUSES:
        return 422, {"detail": f"Cannot cancel a reservation with status '{current_status_name}'"}

    cancelled_status, _ = await Status.objects.aget_or_create(name=STATUS_CANCELLED)
    reservation.status_id = cancelled_status.id
    await reservation.asave(update_fields=["status_id", "updated_at"])
    await reservation.anotify(STATUS_CANCELLED)
    return 200, {"success": True}
