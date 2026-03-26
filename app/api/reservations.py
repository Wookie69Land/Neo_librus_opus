
from ninja import Router
from ninja.errors import HttpError

from app.api.permissions import (
    get_authenticated_session,
    is_library_admin_for_library,
    require_superuser,
    require_library_admin_or_superuser
)
from app.api.serializers import ReservationSchemaIn, ReservationSchemaOut, ReservationUpdateSchema
from app.domain.models import Reservation, Status
from app.domain.repositories import ReservationRepository

router = Router(tags=["Reservations"])
reservation_repo = ReservationRepository(Reservation)


async def _can_access_reservation(session, reservation: Reservation) -> bool:
    is_owner = reservation.reader_id == session.user_id
    is_library_admin = await is_library_admin_for_library(session.user_id, reservation.library_id)
    return is_owner or is_library_admin

@router.get("", response=list[ReservationSchemaOut])
async def list_reservations(request):
    await require_library_admin_or_superuser(request)
    reservations = await reservation_repo.get_all()
    return reservations

@router.post("", response=ReservationSchemaOut)
async def create_reservation(request, payload: ReservationSchemaIn):
    session = get_authenticated_session(request)
    reservation = await reservation_repo.create(
        reader_id=session.user_id, **payload.dict()
    )
    return reservation

@router.get("/{reservation_id}", response=ReservationSchemaOut)
async def get_reservation(request, reservation_id: int):
    session = get_authenticated_session(request)
    reservation = await reservation_repo.get_by_id(reservation_id)
    if reservation is None:
        raise HttpError(404, "Reservation not found")

    if not await _can_access_reservation(session, reservation):
        raise HttpError(403, "Permission denied")

    return reservation


@router.put("/{reservation_id}", response={200: ReservationSchemaOut, 403: dict, 404: dict, 422: dict})
async def update_reservation(request, reservation_id: int, payload: ReservationUpdateSchema):
    session = get_authenticated_session(request)
    try:
        reservation = await Reservation.objects.select_related("library").aget(id=reservation_id)
    except Reservation.DoesNotExist:
        return 404, {"detail": "Reservation not found"}

    if not await _can_access_reservation(session, reservation):
        return 403, {"detail": "Permission denied"}

    update_data = payload.dict(exclude_unset=True)
    if "status_id" in update_data:
        status_exists = await Status.objects.filter(id=update_data["status_id"]).aexists()
        if not status_exists:
            return 422, {"detail": "Status not found"}
        reservation.status_id = update_data["status_id"]

    if "end_time" in update_data:
        reservation.end_time = update_data["end_time"]

    if "librarian_id" in update_data:
        reservation.librarian_id = update_data["librarian_id"]

    await reservation.asave()
    return 200, reservation

@router.delete("/{reservation_id}")
async def delete_reservation(request, reservation_id: int):
    require_superuser(request)
    await reservation_repo.delete(reservation_id)
    return {"success": True}
