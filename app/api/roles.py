
from ninja import Router

from app.api.serializers import RoleSchema
from app.domain.models import Role
from app.domain.repositories import RoleRepository

router = Router(tags=["Roles"])
role_repo = RoleRepository(Role)

@router.get("", response=list[RoleSchema])
async def list_roles(request):
    roles = await role_repo.get_all()
    return roles

@router.post("", response=RoleSchema)
async def create_role(request, payload: RoleSchema):
    role = await role_repo.create(**payload.dict())
    return role

@router.get("/{role_id}", response=RoleSchema)
async def get_role(request, role_id: int):
    role = await role_repo.get_by_id(role_id)
    return role

@router.put("/{role_id}", response=RoleSchema)
async def update_role(request, role_id: int, payload: RoleSchema):
    role = await role_repo.update(role_id, **payload.dict())
    return role

@router.delete("/{role_id}")
async def delete_role(request, role_id: int):
    await role_repo.delete(role_id)
    return {"success": True}
