from typing import Optional

from app_front.models import TransitoryUser


def get_transitory_user_for_email(email: str) -> Optional[TransitoryUser]:
    # 最も作成時刻の新しい、emailが一致するもののを採用する
    return TransitoryUser.objects.filter(email=email).order_by("-registered_at").first()
