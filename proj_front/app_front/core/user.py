from typing import Optional

from app_front.models import User


def get_username_nullable(user: Optional[User]) -> Optional[str]:
    return user.username if user else None
