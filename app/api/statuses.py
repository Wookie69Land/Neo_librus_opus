
from ninja import Router

from app.api.serializers import StatusSchema
from app.domain.models import Status
from app.domain.repositories import StatusRepository

router = Router(tags=["Statuses"])
status_repo = StatusRepository(Status)

@router.get("", response=list[StatusSchema])
async def list_statuses(request):
    statuses = await status_repo.get_all()
    return statuses

@router.post("", response=StatusSchema)
async def create_status(request, payload: StatusSchema):
    status = await status_repo.create(**payload.dict())
    return status

@router.get("/{status_id}", response=StatusSchema)
async def get_status(request, status_id: int):
    status = await status_repo.get_by_id(status_id)
    return status

@router.put("/{status_id}", response=StatusSchema)
async def update_status(request, status_id: int, payload: StatusSchema):
    status = await status_repo.update(status_id, **payload.dict())
    return status

@router.delete("/{status_id}")
async def delete_status(request, status_id: int):
    await status_repo.delete(status_id)
    return {"success": True}
