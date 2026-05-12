
from ninja import Query, Router

from app.api.permissions import (
    require_library_admin_for_library_or_superuser,
    require_superuser,
)
from app.api.serializers import (
    LibrarySchemaIn,
    LibrarySchemaOut,
    LibraryUserSchema,
    PaginatedLibraryUserSchema,
    ReadersListQuery,
)
from app.domain.models import Library, LibraryUser
from app.domain.repositories import LibraryRepository

router = Router(tags=["Libraries"])
library_repo = LibraryRepository(Library)

@router.get("", response=list[LibrarySchemaOut])
async def list_libraries(request):
    libraries = await library_repo.get_all()
    return libraries

@router.post("", response=LibrarySchemaOut)
async def create_library(request, payload: LibrarySchemaIn):
    require_superuser(request)
    library = await library_repo.create(**payload.dict())
    return library

@router.get("/{library_id}", response=LibrarySchemaOut)
async def get_library(request, library_id: int):
    library = await library_repo.get_by_id(library_id)
    return library

@router.put("/{library_id}", response=LibrarySchemaOut)
async def update_library(request, library_id: int, payload: LibrarySchemaIn):
    await require_library_admin_for_library_or_superuser(request, library_id)
    library = await library_repo.update(library_id, **payload.dict())
    return library

@router.delete("/{library_id}")
async def delete_library(request, library_id: int):
    await require_superuser(request, library_id)
    await library_repo.delete(library_id)
    return {"success": True}


@router.get(
    "/{library_id}/readers",
    response=PaginatedLibraryUserSchema,
    summary="List readers of a library",
    description=(
        "Returns a paginated list of users who have made at least one reservation "
        "at the specified library. Accessible by the library's admins and superusers."
    ),
)
async def list_library_readers(
    request, library_id: int, params: ReadersListQuery = Query(...)
):
    await require_library_admin_for_library_or_superuser(request, library_id)

    queryset = (
        LibraryUser.objects.filter(reservations_as_reader__library_id=library_id)
        .distinct()
        .order_by("last_name", "first_name", "id")
    )

    page = max(params.page, 1)
    page_size = min(max(params.page_size, 1), 100)
    total = await queryset.acount()
    start = (page - 1) * page_size
    end = start + page_size
    items = [
        LibraryUserSchema(
            id=user.id,
            username=user.username,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            region=user.region,
            is_active=user.is_active,
            date_joined=user.date_joined,
            last_login=user.last_login,
        )
        async for user in queryset[start:end]
    ]
    total_pages = max((total + page_size - 1) // page_size, 1)
    return PaginatedLibraryUserSchema(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )
