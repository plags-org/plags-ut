"""
Utility definitions
"""
import base64
import dataclasses
import datetime
import random
import urllib.parse
from typing import Any, Tuple, TypedDict

import pytz
from cryptography.hazmat.primitives.ciphers import Cipher, modes
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from django.http.response import Http404
from typing_extensions import TypeAlias

from app_front.models import (
    Course,
    CourseTopNoticeByOrganization,
    CourseUser,
    CustomEvaluationTag,
    Exercise,
    Organization,
    OrganizationUser,
    Submission,
    SubmissionParcel,
    User,
    UserAuthorityEnum,
)


class CourseConcreteDict(TypedDict):
    name: str


@dataclasses.dataclass
class CourseInfo:
    # default: begins_at, opens_at, closes_at, ends_at, edited_at
    # exercise: checks_at
    setting: Course
    # {name: <str>}
    concrete: CourseConcreteDict
    # {<lang>: {title: <str>, body: <markdown>}}
    concrete_cache_docs: Any


class ExerciseConcreteDict(TypedDict):
    name: str


@dataclasses.dataclass
class ExerciseInfo:
    setting: Exercise
    concrete: ExerciseConcreteDict
    concrete_cache_docs: Any
    is_submittable: bool


def get_user(**kwargs) -> User:
    """Get user from parameter"""
    try:
        u_name = kwargs["u_name"]
        user = User.objects.get(username=u_name)
        return user
    except Exception as exc:  # pylint: disable=broad-except
        raise Http404() from exc


def get_organization(**kwargs) -> Organization:
    """Get organization from parameter"""
    try:
        o_name = kwargs["o_name"]
        organization = Organization.objects.get(name=o_name)
        return organization
    except Exception as exc:  # pylint: disable=broad-except
        raise Http404() from exc


def get_course(organization: Organization, **kwargs) -> Tuple[Organization, Course]:
    """Get course from organization and parameter"""
    try:
        c_name = kwargs["c_name"]
        course = Course.objects.get(
            organization=organization, name=c_name, is_active=True
        )
        return organization, course
    except Exception as exc:  # pylint: disable=broad-except
        raise Http404() from exc


def get_exercise(
    organization: Organization, course: Course, **kwargs
) -> Tuple[Organization, Course, Exercise]:
    """Get exercise from organization, course and parameter"""
    try:
        e_name = kwargs["e_name"]
        exercise = Exercise.objects.get(course=course, name=e_name)
        return organization, course, exercise
    except Exception as exc:  # pylint: disable=broad-except
        raise Http404() from exc


SUBMISSION_ID_ENCRYPTION_SALT = b"a\xc2\x1a\xf6\xa0#q\x8e"

_EncryptionKey: TypeAlias = bytes


def encode_some_id_by_encryption_key(
    encryption_key: _EncryptionKey, some_id: int
) -> str:
    some_id_bytes = int.to_bytes(some_id, 8, "little") + SUBMISSION_ID_ENCRYPTION_SALT
    algorithm = AES(encryption_key)
    some_encrypted = Cipher(algorithm, modes.ECB()).encryptor().update(some_id_bytes)
    encoded = str(base64.urlsafe_b64encode(some_encrypted), encoding="ascii")
    return encoded


def decode_some_id_by_encryption_key(
    encryption_key: _EncryptionKey, some_eb64: str
) -> int:
    # NOTE Excel等外部システムに一旦保存するとエスケープされる場合があるようなので追加
    some_eb64 = urllib.parse.unquote(some_eb64)

    some_encrypted = base64.urlsafe_b64decode(some_eb64)

    algorithm = AES(encryption_key)
    some_id_bytes = (
        Cipher(algorithm, modes.ECB()).decryptor().update(some_encrypted)[0:8]
    )

    decoded = int.from_bytes(some_id_bytes, "little")
    return decoded


def encode_submission_parcel_id(course: Course, sp_id: int) -> str:
    return encode_some_id_by_encryption_key(
        course.submission_parcel_id_encryption_key, sp_id
    )


def decode_submission_parcel_id(course: Course, sp_eb64: str) -> int:
    return decode_some_id_by_encryption_key(
        course.submission_parcel_id_encryption_key, sp_eb64
    )


def encode_submission_id(course: Course, s_id: int) -> str:
    return encode_some_id_by_encryption_key(course.submission_id_encryption_key, s_id)


def decode_submission_id(course: Course, s_eb64: str) -> int:
    return decode_some_id_by_encryption_key(course.submission_id_encryption_key, s_eb64)


def encode_evaluation_id(course: Course, ev_id: int) -> str:
    return encode_some_id_by_encryption_key(course.evaluation_id_encryption_key, ev_id)


def decode_evaluation_id(course: Course, ev_eb64: str) -> int:
    return decode_some_id_by_encryption_key(
        course.evaluation_id_encryption_key, ev_eb64
    )


def encode_trial_evaluation_id(course: Course, te_id: int) -> str:
    return encode_some_id_by_encryption_key(
        course.trial_evaluation_id_encryption_key, te_id
    )


def decode_trial_evaluation_id(course: Course, te_eb64: str) -> int:
    return decode_some_id_by_encryption_key(
        course.trial_evaluation_id_encryption_key, te_eb64
    )


def encode_custom_evaluation_tag_id(course: Course, cet_id: int) -> str:
    return encode_some_id_by_encryption_key(
        course.custom_evaluation_tag_id_encryption_key, cet_id
    )


def decode_custom_evaluation_tag_id(course: Course, cet_eb64: str) -> int:
    return decode_some_id_by_encryption_key(
        course.custom_evaluation_tag_id_encryption_key, cet_eb64
    )


def get_submission_parcel(
    organization: Organization, course: Course, **kwargs
) -> Tuple[Organization, Course, SubmissionParcel]:
    """
    Get submission parcel from organization, course and parameter
    """

    try:
        sp_id = decode_submission_parcel_id(course, kwargs["sp_eb64"])

        submission_parcel = SubmissionParcel.objects.get(pk=sp_id)
        assert submission_parcel.organization == organization
        assert submission_parcel.course == course

        return organization, course, submission_parcel

    except Exception as exc:  # pylint: disable=broad-except
        raise Http404() from exc


def get_submission(
    organization: Organization, course: Course, **kwargs
) -> Tuple[Organization, Course, Submission]:
    """
    Get submission from organization, course and parameter
    """

    try:
        s_id = decode_submission_id(course, kwargs["s_eb64"])

        submission = Submission.objects.get(pk=s_id)
        assert submission.organization == organization
        assert submission.course == course

        return organization, course, submission

    except Exception as exc:  # pylint: disable=broad-except
        raise Http404() from exc


def get_custom_evaluation_tag(
    organization: Organization, course: Course, **kwargs
) -> Tuple[Organization, Course, CustomEvaluationTag]:
    """
    Get CustomEvaluationTag from organization, course and parameter
    """
    try:
        cet_id = decode_custom_evaluation_tag_id(course, kwargs["cet_eb64"])

        custom_evaluation_tag = CustomEvaluationTag.objects.get(pk=cet_id)
        assert custom_evaluation_tag.organization == organization
        assert custom_evaluation_tag.course == course

        return organization, course, custom_evaluation_tag

    except Exception as exc:  # pylint: disable=broad-except
        raise Http404() from exc


def get_course_top_notice_by_organization(
    organization: Organization, **kwargs
) -> CourseTopNoticeByOrganization:
    try:
        ctno_id = kwargs["ctno_id"]
        course_top_notice_by_organization = CourseTopNoticeByOrganization.objects.get(
            id=ctno_id
        )
        assert course_top_notice_by_organization.organization == organization
        return course_top_notice_by_organization
    except Exception as exc:
        raise Http404() from exc


def get_organization_course(**kwargs) -> Tuple[Organization, Course]:
    """
    Get course from parameter
    """

    organization = get_organization(**kwargs)
    return get_course(organization, **kwargs)


def get_organization_course_exercise(**kwargs) -> Tuple[Organization, Course, Exercise]:
    """
    Get course, exercise from parameter
    """

    organization, course = get_organization_course(**kwargs)
    return get_exercise(organization, course, **kwargs)


def get_organization_course_submission_parcel(
    **kwargs,
) -> Tuple[Organization, Course, SubmissionParcel]:
    organization, course = get_organization_course(**kwargs)
    return get_submission_parcel(organization, course, **kwargs)


def get_organization_course_submission(
    **kwargs,
) -> Tuple[Organization, Course, Submission]:
    organization, course = get_organization_course(**kwargs)
    return get_submission(organization, course, **kwargs)


def get_organization_course_custom_evaluation_tag(
    **kwargs,
) -> Tuple[Organization, Course, CustomEvaluationTag]:
    """
    Get course from parameter
    """

    organization, course = get_organization_course(**kwargs)
    return get_custom_evaluation_tag(organization, course, **kwargs)


def get_organization_course_top_notice_by_organization(
    **kwargs,
) -> Tuple[Organization, CourseTopNoticeByOrganization]:
    organization = get_organization(**kwargs)
    course_top_notice_by_organization = get_course_top_notice_by_organization(
        organization, **kwargs
    )
    return organization, course_top_notice_by_organization


def get_organization_course_reviewers(organization, course):
    # this condition calculation is a copy of `get_user_authority()` in auth_util
    organization_reviewers = OrganizationUser.objects.filter(
        organization=organization,
        authority__gte=UserAuthorityEnum.ASSISTANT.value,
    )
    course_reviewers = CourseUser.objects.filter(
        course=course,
        authority__gte=UserAuthorityEnum.ASSISTANT.value,
    )
    reviewers = [
        reviewer.user
        for reviewers in (
            organization_reviewers,
            course_reviewers,
        )
        for reviewer in reviewers
    ]

    return reviewers


def get_course_info(organization: Organization, course: Course) -> CourseInfo:
    manikin_concrete = dict(
        name="manikin_concrete_for__" + organization.name + "__" + course.name
    )
    manikin_cache_docs = {
        course.default_lang_i18n: dict(
            title=course.title,
            body=course.body,
        )
    }
    return CourseInfo(course, manikin_concrete, manikin_cache_docs)


def get_course_info_published(organization: Organization, course: Course) -> CourseInfo:
    course_info = get_course_info(organization, course)

    if course.begins_to_ends():
        return course_info

    course_masked = dict(
        name=course.name,
        calculated_begins_at=course.calculated_begins_at(),
        calculated_opens_at=course.calculated_opens_at(),
        calculated_closes_at=course.calculated_closes_at(),
        calculated_ends_at=course.calculated_ends_at(),
        edited_at=course.edited_at,
    )
    default_unreleased_message = dict(
        en="Please wait until the release time below.",
        ja="以下の解放時刻までお待ちください。",
    )
    course_concrete_cache_docs_masked = {
        lang: dict(
            title=content["title"].split(" ", 1)[0],
            body=default_unreleased_message[lang],
        )
        for lang, content in course_info.concrete_cache_docs.items()
    }
    course_info.setting = course_masked
    course_info.concrete_cache_docs = course_concrete_cache_docs_masked
    return course_info


def get_exercise_info(organization: Organization, exercise: Exercise):
    manikin_concrete = dict(
        name="manikin_concrete_for__" + organization.name + "__" + exercise.name
    )
    manikin_cache_docs = {
        exercise.default_lang_i18n: dict(
            title=exercise.title,
            body=exercise.body_ipynb_json,
        )
    }
    return ExerciseInfo(exercise, manikin_concrete, manikin_cache_docs, True)


def get_exercise_info_published(organization: Organization, exercise: Exercise):
    exercise_info = get_exercise_info(organization, exercise)

    if exercise.begins_to_ends():
        if not exercise.opens_to_closes():
            exercise_info.is_submittable = False
        return exercise_info

    exercise_masked = dict(
        name=exercise.name,
        begins_at=exercise.calculated_begins_at(),
        opens_at=exercise.calculated_opens_at(),
        checks_at=exercise.calculated_checks_at(),
        closes_at=exercise.calculated_closes_at(),
        ends_at=exercise.calculated_ends_at(),
        edited_at=exercise.edited_at,
    )
    default_unreleased_message = dict(
        en="Please wait until the release time below.",
        ja="以下の解放時刻までお待ちください。",
    )
    exercise_concrete_cache_docs_masked = {
        lang: dict(
            title=content["title"].split(" ", 1)[0],
            body=default_unreleased_message[lang],
        )
        for lang, content in exercise_info.concrete_cache_docs.items()
    }
    exercise_info.setting = exercise_masked
    exercise_info.concrete_cache_docs = exercise_concrete_cache_docs_masked
    exercise_info.is_submittable = False
    return exercise_info


def generate_activation_pin() -> str:
    return "_".join(f"{x:04x}" for x in random.randint(0, 65535) for _ in range(5))


def generate_verification_token() -> str:
    token_len = 40
    random_int = random.randint(0, 16**token_len - 1)
    return f"{random_int:0{token_len}x}"


def from_user_timezone(user_timezone, input_datetime):
    """
    Convert `input_datetime` (in `user_timezone`) into UTC
    """
    input_datetime = input_datetime.replace(tzinfo=None)
    return user_timezone.localize(input_datetime).astimezone(pytz.utc)


def to_user_timezone(
    user_timezone: datetime.timezone, input_datetime: datetime.datetime
) -> datetime.datetime:
    return input_datetime.astimezone(user_timezone)
