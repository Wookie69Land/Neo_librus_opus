from ninja.security import HttpBearer

from app.domain.models import SessionToken


class BearerTokenAuth(HttpBearer):
    async def authenticate(self, request, token):
        try:
            # Find the token in the database and prefetch the related user
            session_token = await SessionToken.objects.select_related("user").aget(
                key=token
            )
            return session_token.user
        except SessionToken.DoesNotExist:
            return None


auth = BearerTokenAuth()
