from django.db.models.query import QuerySet

from app_front.models import CourseUser, Organization


def get_organization_course_users(organization: Organization) -> QuerySet[CourseUser]:
    return (
        CourseUser.objects.filter(course__organization=organization)
        .order_by("-authority", "user__username", "course__name")
        .select_related(
            "course",
            "user",
            "added_by",
            "is_active_updated_by",
            "authority_updated_by",
        )
    )
