
from ninja import Router

from app.api.serializers import ReservationSchemaIn, ReservationSchemaOut
from app.domain.models import Reservation
from app.domain.repositories import ReservationRepository

router = Router(tags=["Reservations"])
reservation_repo = ReservationRepository(Reservation)

@router.get("", response=list[ReservationSchemaOut])
async def list_reservations(request):
    reservations = await reservation_repo.get_all()
    return reservations

@router.post("", response=ReservationSchemaOut)
async def create_reservation(request, payload: ReservationSchemaIn):
    reservation = await reservation_repo.create(
        reader_id=request.user.id, **payload.dict()
    )
    return reservation

@router.get("/{reservation_id}", response=ReservationSchemaOut)
async def get_reservation(request, reservation_id: int):
    reservation = await reservation_repo.get_by_id(reservation_id)
    return reservation

@router.delete("/{reservation_id}")
async def delete_reservation(request, reservation_id: int):
    await reservation_repo.delete(reservation_id)
    return {"success": True}
