
from ninja import Router

from app.api.serializers import LibrarySchemaIn, LibrarySchemaOut
from app.domain.models import Library
from app.domain.repositories import LibraryRepository

router = Router(tags=["Libraries"])
library_repo = LibraryRepository(Library)

@router.get("", response=list[LibrarySchemaOut])
async def list_libraries(request):
    libraries = await library_repo.get_all()
    return libraries

@router.post("", response=LibrarySchemaOut)
async def create_library(request, payload: LibrarySchemaIn):
    library = await library_repo.create(**payload.dict())
    return library

@router.get("/{library_id}", response=LibrarySchemaOut)
async def get_library(request, library_id: int):
    library = await library_repo.get_by_id(library_id)
    return library

@router.put("/{library_id}", response=LibrarySchemaOut)
async def update_library(request, library_id: int, payload: LibrarySchemaIn):
    library = await library_repo.update(library_id, **payload.dict())
    return library

@router.delete("/{library_id}")
async def delete_library(request, library_id: int):
    await library_repo.delete(library_id)
    return {"success": True}
