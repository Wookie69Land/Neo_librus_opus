
from ninja import Router

from app.api.serializers import AuthorSchema
from app.domain.models import Author
from app.domain.repositories import AuthorRepository

router = Router(tags=["Authors"])
author_repo = AuthorRepository(Author)

@router.get("", response=list[AuthorSchema])
async def list_authors(request):
    authors = await author_repo.get_all()
    return authors

@router.post("", response=AuthorSchema)
async def create_author(request, payload: AuthorSchema):
    author = await author_repo.create(**payload.dict())
    return author

@router.get("/{author_id}", response=AuthorSchema)
async def get_author(request, author_id: int):
    author = await author_repo.get_by_id(author_id)
    return author

@router.put("/{author_id}", response=AuthorSchema)
async def update_author(request, author_id: int, payload: AuthorSchema):
    author = await author_repo.update(author_id, **payload.dict())
    return author

@router.delete("/{author_id}")
async def delete_author(request, author_id: int):
    await author_repo.delete(author_id)
    return {"success": True}
