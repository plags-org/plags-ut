import dataclasses
import datetime
import functools
from typing import Dict, Final, Iterable, List, Optional, Tuple, Union

from django.db.models.query import QuerySet
from pydantic import BaseModel, ConstrainedStr

from app_front.core.types import Activeness, ColorRGBHex
from app_front.models import Course, CustomEvaluationTag, Organization
from app_front.utils.auth_util import UserAuthorityDict


@dataclasses.dataclass
class CustomEvaluationTagData:
    id: int  # pylint: disable=invalid-name
    organization__id: int
    organization__name: str
    course__id: int
    course__name: str
    activeness: Activeness
    code: str
    description: str
    color: ColorRGBHex
    background_color: ColorRGBHex
    is_visible_to_students: bool
    created_at: datetime.datetime
    created_by__username: str
    updated_at: datetime.date
    updated_by__username: str


def convert_CustomEvaluationTag_to_Data(
    tag: CustomEvaluationTag, organization: Organization, course: Course
) -> CustomEvaluationTagData:
    return CustomEvaluationTagData(
        id=tag.id,
        organization__id=organization.id,
        organization__name=organization.name,
        course__id=course.id,
        course__name=course.name,
        activeness=tag.activeness,
        code=tag.code,
        description=tag.description,
        color=tag.color,
        background_color=tag.background_color,
        is_visible_to_students=tag.is_visible_to_students,
        created_at=tag.created_at,
        created_by__username=tag.created_by.username,
        updated_at=tag.updated_at,
        updated_by__username=tag.updated_by.username,
    )


def _get_custom_evaluation_tags_for_course(
    organization: Organization, course: Course
) -> QuerySet[CustomEvaluationTag]:
    return CustomEvaluationTag.objects.filter(
        organization=organization, course=course
    ).select_related(
        "created_by",
        "updated_by",
    )


def get_custom_evaluation_tags(
    organization: Organization, course: Course
) -> List[CustomEvaluationTagData]:
    return [
        convert_CustomEvaluationTag_to_Data(tag, organization, course)
        for tag in _get_custom_evaluation_tags_for_course(organization, course)
    ]


def get_custom_evaluation_tags_for_students(
    organization: Organization, course: Course
) -> List[CustomEvaluationTagData]:
    return [
        convert_CustomEvaluationTag_to_Data(tag, organization, course)
        for tag in _get_custom_evaluation_tags_for_course(organization, course).filter(
            is_visible_to_students=True
        )
    ]


def get_custom_evaluation_tags_for_authority(
    organization: Organization, course: Course, user_authority: UserAuthorityDict
) -> List[CustomEvaluationTagData]:
    if user_authority.get("can_edit_course"):
        return get_custom_evaluation_tags(organization, course)
    return get_custom_evaluation_tags_for_students(organization, course)


CompatibleTagData = Union[dict, int]
TagName = str
TagDescription = str

StatusName = str
StatusDescription = str


class HTMLColorString(ConstrainedStr):
    min_length = 4
    max_length = 7
    regex = r"^#([0-9a-fA-F]{3}){1,2}$"


class EvaluationTagModel(BaseModel):
    name: str
    description: str
    background_color: HTMLColorString
    font_color: HTMLColorString
    visible: bool

    class Config:
        frozen = True


class CustomEvaluationTagManager:
    __BUILTIN_STATUSES_AND_DESCRIPTIONS: Final[Dict[StatusName, StatusDescription]] = {
        "AS": "All Successful",
        "FE": "Failure Exists",
        "A": "Accepted",
        "WJ": "Waiting for Judgement",
    }
    __BUILTIN_TAGS_AND_DESCRIPTIONS: Final[Dict[TagName, TagDescription]] = {
        # cf. <https://github.com/plags-org/plags_ut_dev/issues/273>
        "BSE": "Backend System Error",
        "ESE": "Evaluation System Error",
        "TLE": "Time Limit Exceeded",
        "PV": "Permission Violation",
        "UA": "Unexpected Abortion",
    }


    @classmethod
    @functools.lru_cache(1)
    def get_builtin_tags_WORKAROUND(cls) -> Tuple[Union[TagName, StatusName], ...]:
        return tuple(cls.__BUILTIN_TAGS_AND_DESCRIPTIONS) + tuple(
            cls.__BUILTIN_STATUSES_AND_DESCRIPTIONS
        )

    @classmethod
    @functools.lru_cache(1)
    def get_builtin_tags(cls) -> Tuple[TagName, ...]:
        return tuple(cls.__BUILTIN_TAGS_AND_DESCRIPTIONS)

    @classmethod
    @functools.lru_cache(1)
    def _get_builtin_tags_and_descriptions_WORKAROUND(
        cls,
    ) -> Dict[TagName, TagDescription]:
        # return cls.__BUILTIN_TAGS_AND_DESCRIPTIONS.copy()
        tags_and_descriptions = cls.__BUILTIN_STATUSES_AND_DESCRIPTIONS.copy()
        tags_and_descriptions.update(cls.__BUILTIN_TAGS_AND_DESCRIPTIONS)
        return tags_and_descriptions

    @classmethod
    def get_builtin_tags_and_descriptions_WORKAROUND(
        cls,
    ) -> Dict[TagName, TagDescription]:
        return cls._get_builtin_tags_and_descriptions_WORKAROUND().copy()

    @classmethod
    def get_builtin_tags_and_descriptions(cls) -> Dict[TagName, TagDescription]:
        return cls.__BUILTIN_TAGS_AND_DESCRIPTIONS.copy()

    @classmethod
    def get_builtin_statuses_and_descriptions(cls) -> Dict[TagName, TagDescription]:
        return cls.__BUILTIN_STATUSES_AND_DESCRIPTIONS.copy()

    @classmethod
    def is_builtin_WORKAROUND(cls, code: str) -> bool:
        return code in cls.get_builtin_tags_WORKAROUND()

    @classmethod
    def is_builtin(cls, code: str, description: Optional[str] = None) -> bool:
        if description is None:
            return code in cls.get_builtin_tags()
        return description == cls.__BUILTIN_TAGS_AND_DESCRIPTIONS.get(code)

    def __init__(
        self,
        custom_evaluation_tags: List[CustomEvaluationTagData],
        user_authority: UserAuthorityDict,
    ):
        self.custom_evaluation_tags = custom_evaluation_tags
        self.cache_student_viewable_tags = set(
            self.get_builtin_tags()
            + tuple(
                tag.code for tag in custom_evaluation_tags if tag.is_visible_to_students
            )
        )
        self.cache_lecturer_viewable_tags = set(
            self.get_builtin_tags() + tuple(tag.code for tag in custom_evaluation_tags)
        )
        self.cache_custom_tags = {tag.code: tag for tag in custom_evaluation_tags}
        self._is_student = not bool(user_authority.get("can_review_submission"))
        self._is_as_manager = user_authority["on_course"].is_as_manager()

    @staticmethod
    def __unify(tag: CompatibleTagData) -> TagName:
        if isinstance(tag, str):
            return tag
        if isinstance(tag, dict):
            return tag["code"]
        raise ValueError(f"Invalid tag: {tag!r}")

    def __is_student_viewable(self, tag: TagName) -> bool:
        return tag in self.cache_student_viewable_tags

    def __is_lecturer_viewable(self, tag: TagName) -> bool:
        return tag in self.cache_lecturer_viewable_tags

    def filter_tags(self, tags: List[CompatibleTagData]) -> Iterable[TagName]:
        unified_tags = map(self.__unify, tags)
        if self._is_as_manager:
            return unified_tags
        if self._is_student:
            return filter(self.__is_student_viewable, unified_tags)
        return filter(self.__is_lecturer_viewable, unified_tags)

    def filter_tags_v2(
        self, tags: List[EvaluationTagModel]
    ) -> Iterable[EvaluationTagModel]:
        if self._is_as_manager:
            return tags
        if self._is_student:
            return (tag for tag in tags if tag.visible)
        return tags

    def get_custom_evaluation_tag_by_code(
        self, code: str
    ) -> Optional[CustomEvaluationTagData]:
        custom_tag = self.cache_custom_tags.get(code)
        if custom_tag is None:
            return None
        if self._is_as_manager:
            return custom_tag
        if self._is_student:
            if not custom_tag.is_visible_to_students:
                return None
            return custom_tag
        return custom_tag
