
from ninja import Router

from app.api.permissions import require_library_admin_or_superuser, require_superuser
from app.api.serializers import AuthorSchemaIn, AuthorSchemaOut
from app.domain.models import Author
from app.domain.repositories import AuthorRepository

router = Router(tags=["Authors"])
author_repo = AuthorRepository(Author)

@router.get("", response=list[AuthorSchemaOut], auth=None)
async def list_authors(request):
    authors = await author_repo.get_all()
    return authors

@router.post("", response=AuthorSchemaOut)
async def create_author(request, payload: AuthorSchemaIn):
    await require_library_admin_or_superuser(request)
    author = await author_repo.create(**payload.dict())
    return author

@router.get("/{author_id}", response=AuthorSchemaOut)
async def get_author(request, author_id: int):
    author = await author_repo.get_by_id(author_id)
    return author

@router.put("/{author_id}", response=AuthorSchemaOut)
async def update_author(request, author_id: int, payload: AuthorSchemaIn):
    await require_library_admin_or_superuser(request)
    author = await author_repo.update(author_id, **payload.dict())
    return author

@router.delete("/{author_id}")
async def delete_author(request, author_id: int):
    await require_superuser(request)
    await author_repo.delete(author_id)
    return {"success": True}
