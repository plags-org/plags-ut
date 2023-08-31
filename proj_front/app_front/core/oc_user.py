from typing import Iterable, List, Tuple, Union

from django.db.models.query import QuerySet

from app_front.models import (
    Course,
    CourseUser,
    Organization,
    OrganizationUser,
    User,
    UserAuthorityEnum,
)

UserAuthorityCode = str

AVAILABLE_FACULTY_USER_AUTHORITY_CHOICES = UserAuthorityEnum.as_choices(
    UserAuthorityEnum.MANAGER,
    UserAuthorityEnum.LECTURER,
)
FACULTY_USER_DEFAULT_AUTHORITY_CHOICE: UserAuthorityCode = UserAuthorityEnum(
    UserAuthorityEnum.LECTURER
).value

AVAILABLE_STUDENT_USER_AUTHORITY_CHOICES = UserAuthorityEnum.as_choices(
    UserAuthorityEnum.STUDENT,
    UserAuthorityEnum.ASSISTANT,
)
STUDENT_USER_DEFAULT_AUTHORITY_CHOICE: UserAuthorityCode = UserAuthorityEnum(
    UserAuthorityEnum.STUDENT
).value


def get_sorted_organization_users(
    organization: Organization,
) -> Iterable[OrganizationUser]:
    return (
        OrganizationUser.objects.filter(organization=organization)
        .order_by("-authority", "user__username")
        .select_related("user")
    )


def get_sorted_course_users(course: Course) -> Iterable[CourseUser]:
    return (
        CourseUser.objects.filter(course=course)
        .order_by("-authority", "user__username")
        .select_related("user")
    )


def get_sorted_course_students(course: Course) -> Iterable[CourseUser]:
    return (
        CourseUser.objects.filter(
            course=course,
            # NOTE 権限ではなく教員ユーザーか学生ユーザーかで分岐するようにした
            user__is_faculty=False,
            # authority__in=(
            #     UserAuthorityEnum(UserAuthorityEnum.STUDENT).value,
            #     UserAuthorityEnum(UserAuthorityEnum.ASSISTANT).value,
            # ),
        )
        .order_by("-authority", "user__username")
        .select_related("user")
    )


def get_sorted_course_faculties(course: Course) -> Iterable[CourseUser]:
    return (
        CourseUser.objects.filter(
            course=course,
            # NOTE 権限ではなく教員ユーザーか学生ユーザーかで分岐するようにした
            user__is_faculty=True,
            # authority__in=(
            #     UserAuthorityEnum(UserAuthorityEnum.LECTURER).value,
            #     UserAuthorityEnum(UserAuthorityEnum.MANAGER).value,
            # ),
        )
        .order_by("-authority", "user__username")
        .select_related("user")
    )


UserChoices = List[Tuple[Union[int, str], str]]


def get_oc_user_choices(
    oc_users: Union[Iterable[OrganizationUser], Iterable[CourseUser]]
) -> UserChoices:
    return [
        (
            ocu.user.id,
            f"[{ocu.authority.split('_', maxsplit=1)[-1]}] {ocu.user.username}",
        )
        for ocu in oc_users
    ]


def get_non_oc_user_choices(
    oc_users: Union[Iterable[OrganizationUser], Iterable[CourseUser]]
) -> UserChoices:
    oc_usernames = {u.user.username for u in oc_users}
    model_users = User.objects.filter(is_staff=False).all()
    non_oc_user_choices = [
        (u.id, u.username) for u in model_users if u.username not in oc_usernames
    ]
    return non_oc_user_choices


def get_non_oc_student_choices(
    oc_users: Union[Iterable[OrganizationUser], Iterable[CourseUser]]
) -> UserChoices:
    oc_usernames = {u.user.username for u in oc_users}
    model_users = User.objects.filter(is_staff=False, is_faculty=False).all()
    non_oc_user_choices = [
        (u.id, u.username) for u in model_users if u.username not in oc_usernames
    ]
    return non_oc_user_choices


def get_non_oc_faculty_choices(
    oc_users: Union[Iterable[OrganizationUser], Iterable[CourseUser]]
) -> UserChoices:
    oc_usernames = {u.user.username for u in oc_users}
    model_users = User.objects.filter(is_staff=False, is_faculty=True).all()
    non_oc_user_choices = [
        (u.id, u.username) for u in model_users if u.username not in oc_usernames
    ]
    return non_oc_user_choices


def get_active_course_students(course: Course) -> QuerySet[CourseUser]:
    student_authority = UserAuthorityEnum(UserAuthorityEnum.STUDENT).value
    return CourseUser.objects.filter(
        course=course, is_active=True, authority=student_authority
    )


def get_active_course_users(course: Course) -> QuerySet[CourseUser]:
    return CourseUser.objects.filter(course=course, is_active=True)
