from app_front.core.types import OrganizationName
from app_front.models import Organization, User


def create_organization(
    *,
    name: OrganizationName,
    request_user: User,
) -> Organization:
    return Organization.objects.create(
        name=name,
        created_by=request_user,
        is_active=True,
        is_active_updated_by=request_user,
    )
