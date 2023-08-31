from django.http.request import HttpRequest

from app_front.models import User


def get_request_user_safe(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User), (type(user), user)
    return user
