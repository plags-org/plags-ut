import datetime
from typing import List, Optional, Tuple

from django.db.models import QuerySet
from pydantic import BaseModel
from typing_extensions import TypeAlias

from app_front.models import Course, Organization, User, UserAuthorityEnum
from app_front.utils.auth_util import ContextUserAuthority, UserAuthorityDict
from app_front.utils.exception_util import SystemLogicalError
from app_front.utils.parameter_decoder import (
    CourseInfo,
    get_course_info,
    get_course_info_published,
)

_CourseChoices: TypeAlias = Tuple[Tuple[str, str], ...]


def get_courses(organization: Organization) -> QuerySet:
    return Course.objects.filter(organization=organization, is_active=True)


def get_deleted_courses(organization: Organization) -> QuerySet:
    return Course.objects.filter(organization=organization, is_active=False)


def get_course_choices(organization: Organization) -> _CourseChoices:
    courses: List[Course] = list(get_courses(organization))
    return tuple((course.name, course.title) for course in courses)


def to_course_choices(courses: QuerySet[Course]) -> _CourseChoices:
    return tuple((course.name, course.title) for course in courses)


def get_courses_and_choices(
    organization: Organization,
) -> Tuple[List[Course], _CourseChoices]:
    courses: List[Course] = list(get_courses(organization))
    return courses, tuple((course.name, course.title) for course in courses)


def is_course_visible_to_user_authority(
    course: Course, user_authority: ContextUserAuthority
) -> bool:
    """コースがユーザーにとって可視であるかを判定する"""
    if user_authority.can_view_course:
        return True
    if user_authority.can_view_course_published:
        return course.begins_to_ends()
    return False


def get_course_info_for_authority(
    organization: Organization, course: Course, user_authority: UserAuthorityDict
) -> CourseInfo:
    if user_authority.get("can_view_course"):
        return get_course_info(organization, course)
    if user_authority.get("can_view_course_published"):
        return get_course_info_published(organization, course)
    raise SystemLogicalError("Should never come here")


class CourseCreateData(BaseModel):
    name: str
    title: str
    body: str
    is_registerable: bool
    begins_at: datetime.datetime
    opens_at: datetime.datetime
    checks_at: Optional[datetime.datetime]
    closes_at: datetime.datetime
    ends_at: datetime.datetime
    is_shared_after_confirmed: bool
    score_visible_from: UserAuthorityEnum
    remarks_visible_from: UserAuthorityEnum


def create_course(
    data: CourseCreateData, organization: Organization, request_user: User
) -> Course:
    return Course.objects.create(
        organization=organization,
        name=data.name,
        created_by=request_user,
        is_active=True,
        is_active_updated_by=request_user,
        title=data.title,
        body=data.body,
        is_registerable=data.is_registerable,
        exercise_default_begins_at=data.begins_at,
        exercise_default_opens_at=data.opens_at,
        exercise_default_checks_at=data.checks_at,
        exercise_default_closes_at=data.closes_at,
        exercise_default_ends_at=data.ends_at,
        exercise_default_is_shared_after_confirmed=data.is_shared_after_confirmed,
        exercise_default_score_visible_from=data.score_visible_from,
        exercise_default_remarks_visible_from=data.remarks_visible_from,
        edited_by=request_user,
    )
