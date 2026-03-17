from ninja.security import HttpBearer

from app.domain.models import SessionToken


class BearerTokenAuth(HttpBearer):
    async def authenticate(self, request, token):
        try:
            session_token = await SessionToken.objects.select_related("user").aget(
                key=token
            )
            return session_token
        except SessionToken.DoesNotExist:
            return None


auth = BearerTokenAuth()
