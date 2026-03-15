import re
import secrets

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from ninja import Query, Router, Schema
from unidecode import unidecode

from app.api.serializers import LibraryUserSchema, LoginSchema, RegisterSchema
from app.domain.models import LibraryAdmin, LibraryUser, SessionToken
from app.domain.repositories import LibraryAdminRepository, LibraryUserRepository

router = Router(tags=["Auth"])
user_repo = LibraryUserRepository(LibraryUser)
admin_repo = LibraryAdminRepository(LibraryAdmin)


class AccountActivationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return str(user.pk) + str(timestamp) + str(user.is_active)


account_activation_token = AccountActivationTokenGenerator()


class LoginResponseSchema(Schema):
    user: LibraryUserSchema
    is_admin: bool
    token: str


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


@router.post("/login", response=LoginResponseSchema, auth=None)
async def login(request, payload: LoginSchema):
    user = await user_repo.get_by_username_or_email(payload.login)
    if user and user.check_password(payload.password):
        if not user.is_active:
            return 401, {"detail": "Account not activated"}

        # Create or update the session token
        token_key = secrets.token_hex(20)
        await SessionToken.objects.aupdate_or_create(
            user=user, defaults={"key": token_key}
        )

        admin_library_ids = await admin_repo.get_admin_library_ids(user.id)
        is_admin = len(admin_library_ids) > 0
        
        return LoginResponseSchema(user=user, is_admin=is_admin, token=token_key)
    return 401, {"detail": "Invalid credentials"}


@router.post("/logout")
async def logout(request):
    try:
        token = await SessionToken.objects.aget(user=request.auth)
        await token.adelete()
        return {"detail": "Logout successful"}
    except SessionToken.DoesNotExist:
        return 401, {"detail": "Invalid token"}
