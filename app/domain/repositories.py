from app.domain.models import (
    Author,
    Book,
    BookAuthor,
    Library,
    LibraryAdmin,
    LibraryBook,
    LibraryUser,
    Reservation,
    Role,
    Status,
)
from app.domain.repository import AsyncRepository


class BookRepository(AsyncRepository[Book]):
    pass


class AuthorRepository(AsyncRepository[Author]):
    pass


class LibraryRepository(AsyncRepository[Library]):
    pass


class ReservationRepository(AsyncRepository[Reservation]):
    pass


class StatusRepository(AsyncRepository[Status]):
    pass


class RoleRepository(AsyncRepository[Role]):
    pass


class LibraryUserRepository(AsyncRepository[LibraryUser]):
    async def get_by_username_or_email(self, login: str):
        try:
            if "@" in login:
                return await self.model.objects.aget(email=login)
            else:
                return await self.model.objects.aget(username=login)
        except self.model.DoesNotExist:
            return None


class LibraryBookRepository(AsyncRepository[LibraryBook]):
    pass


class LibraryAdminRepository(AsyncRepository[LibraryAdmin]):
    async def is_admin(self, user_id: int) -> bool:
        return await self.model.objects.filter(user_id=user_id).aexists()

    async def get_admin_library_ids(self, user_id: int) -> list[int]:
        return [
            admin.library.id
            async for admin in self.model.objects.filter(user_id=user_id)
        ]


class BookAuthorRepository(AsyncRepository[BookAuthor]):
    pass
