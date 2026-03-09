import re

from ninja import Router, Schema

from app.api.serializers import LibraryUserSchema, LoginSchema, RegisterSchema
from app.domain.models import LibraryAdmin, LibraryUser
from app.domain.repositories import LibraryAdminRepository, LibraryUserRepository

router = Router(tags=["Auth"])
user_repo = LibraryUserRepository(LibraryUser)
admin_repo = LibraryAdminRepository(LibraryAdmin)

class LoginResponseSchema(Schema):
    user: LibraryUserSchema
    is_admin: bool

async def generate_username(first_name, last_name):
    first_name_processed = first_name.lower().replace(" ", "")
    last_name_processed = last_name.lower().replace(" ", "")

    base_username = f"{first_name_processed[0]}{last_name_processed}"

    existing_users = LibraryUser.objects.filter(username__startswith=base_username)

    if await existing_users.acount() == 0:
        return base_username
    else:
        # Find the highest number appended to a similar username
        max_number = 0
        async for user in existing_users:
            match = re.match(rf"{base_username}(\d*)", user.username)
            if match:
                number_str = match.group(1)
                if number_str:
                    number = int(number_str)
                    if number > max_number:
                        max_number = number
        return f"{base_username}{max_number + 1}"

@router.post("/register", response=LibraryUserSchema)
async def register(request, payload: RegisterSchema):
    username = await generate_username(payload.first_name, payload.last_name)

    user = await user_repo.create(
        username=username,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        region=payload.region,
    )
    user.set_password(payload.password)
    await user.asave()

    return user

@router.post("/login", response=LoginResponseSchema)
async def login(request, payload: LoginSchema):
    user = await user_repo.get_by_username_or_email(payload.login)
    if user and user.check_password(payload.password):
        is_admin = await admin_repo.is_admin(user.id)
        return LoginResponseSchema(user=user, is_admin=is_admin)
    return 401, {"detail": "Invalid credentials"}

