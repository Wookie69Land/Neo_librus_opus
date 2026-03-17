import re
import secrets

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from ninja import Query, Router, Schema
from unidecode import unidecode

from app.api.serializers import LibraryUserSchema, LoginSchema, LogoutSchema, RegisterSchema
from app.domain.models import LibraryAdmin, LibraryUser, SessionToken
from app.domain.repositories import LibraryAdminRepository, LibraryUserRepository

router = Router(tags=["Auth"])
user_repo = LibraryUserRepository(LibraryUser)
admin_repo = LibraryAdminRepository(LibraryAdmin)


class AccountActivationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return str(user.pk) + str(timestamp) + str(user.is_active)


account_activation_token = AccountActivationTokenGenerator()


async def generate_username(first_name, last_name):
    first_name_processed = unidecode(first_name.lower().replace(" ", ""))
    last_name_processed = unidecode(last_name.lower().replace(" ", ""))

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


@router.post("/register", response=LibraryUserSchema, auth=None)
async def register(request, payload: RegisterSchema):
    username = await generate_username(payload.first_name, payload.last_name)

    user = await user_repo.create(
        username=username,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        region=payload.region,
        is_active=False,
    )
    user.set_password(payload.password)
    await user.asave()

    # Send activation email
    token = account_activation_token.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    activation_link = request.build_absolute_uri(f"/api/auth/activate?uid={uid}&token={token}")
    
    send_mail(
        "Activate your account",
        f"Please activate your account by clicking this link: {activation_link}",
        'no-reply.librarius@gmail.com',
        [user.email],
        fail_silently=False,
    )

    return user


@router.get("/activate", auth=None)
async def activate(request, uid: str = Query(...), token: str = Query(...)):
    try:
        uid_decoded = force_str(urlsafe_base64_decode(uid))
        user = await user_repo.get_by_id(int(uid_decoded))
    except (TypeError, ValueError, OverflowError, LibraryUser.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        await user.asave()
        return {"detail": "Account activated successfully"}
    else:
        return 400, {"detail": "Invalid activation link"}


@router.post("/login", response={200: dict, 401: dict}, auth=None)
async def login(request, payload: LoginSchema):
    user = await user_repo.get_by_username_or_email(payload.login)
    if user and user.check_password(payload.password):
        if not user.is_active:
            return 401, {"detail": "Account not activated"}

        # Determine role and library from the last LibraryAdmin entry
        library_admin = await LibraryAdmin.objects.filter(user=user).order_by('added_at').alast()
        if library_admin is None:
            role_part = 0
            library_id_part = 0
        else:
            role_part = library_admin.role_id
            library_id_part = library_admin.library_id

        # Build structured token: user_id-role-library_id-random_hex
        token_key = f"{user.id}-{role_part}-{library_id_part}-{secrets.token_hex(20)}"
        await SessionToken.objects.aupdate_or_create(
            user=user, defaults={"key": token_key}
        )

        return {"token": token_key}
    return 401, {"detail": "Invalid credentials"}


@router.post("/logout", response={200: dict, 409: dict}, auth=None)
async def logout(request, payload: LogoutSchema):
    try:
        session = await SessionToken.objects.aget(user_id=payload.user_id)
        if session.key == payload.token:
            await session.adelete()
            return 200, {"detail": "Logout successful"}
        else:
            return 409, {"detail": "Another session is open for this user"}
    except SessionToken.DoesNotExist:
        return 200, {"detail": "No active session found — already logged out"}
