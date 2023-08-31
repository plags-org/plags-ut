import dataclasses
import datetime
import enum
from typing import Any, Dict, List, Literal, Optional, Tuple, TypeVar, Union

from django.db.models.query import QuerySet
from pydantic import BaseModel

from app_front.core.judge_util import send_submission_to_judger
from app_front.core.types import ExerciseName
from app_front.core.user import get_username_nullable
from app_front.models import (
    Course,
    Exercise,
    Submission,
    SubmissionTypeEnum,
    User,
    UserAuthorityEnum,
)
from app_front.utils.auth_util import RequestContext, UserAuthorityDict
from app_front.utils.time_util import get_current_datetime


def _can_user_view_submission_score(
    user_authority: UserAuthorityDict, submission: Submission
) -> bool:
    """ユーザーがその権限において score を閲覧可能であるかを判定"""
    exercise: Exercise = submission.exercise
    return exercise.calculated_score_visible_from() <= user_authority["on_course"]


def _can_context_view_submission_score(
    context: RequestContext, submission: Submission
) -> bool:
    """ユーザーがその権限において score を閲覧可能であるかを判定"""
    exercise: Exercise = submission.exercise
    return exercise.calculated_score_visible_from() <= context.user_authority_on_course


def _can_user_view_submission_remarks(
    user_authority: UserAuthorityDict, submission: Submission
) -> bool:
    """ユーザーがその権限において remarks を閲覧可能であるかを判定"""
    exercise: Exercise = submission.exercise
    return exercise.calculated_remarks_visible_from() <= user_authority["on_course"]


def _can_context_view_submission_remarks(
    context: RequestContext, submission: Submission
) -> bool:
    """ユーザーがその権限において remarks を閲覧可能であるかを判定"""
    exercise: Exercise = submission.exercise
    return (
        exercise.calculated_remarks_visible_from() <= context.user_authority_on_course
    )


class ReviewSubmissionAuthorityParams(BaseModel):
    is_confirmable: bool
    can_view_submission_score: bool
    can_view_submission_remarks: bool
    user_authority_on_course: UserAuthorityEnum
    score_visible_from: UserAuthorityEnum
    remarks_visible_from: UserAuthorityEnum

    @classmethod
    def make_from_auth_dict(
        cls, user_authority: UserAuthorityDict, submission: Submission
    ) -> "ReviewSubmissionAuthorityParams":
        submission_exercise: Exercise = submission.exercise

        is_confirmable = user_authority["can_confirm_submission"]
        can_view_submission_score = _can_user_view_submission_score(
            user_authority, submission
        )
        can_view_submission_remarks = _can_user_view_submission_remarks(
            user_authority, submission
        )
        user_authority_on_course = user_authority["on_course"]
        score_visible_from = submission_exercise.calculated_score_visible_from()
        remarks_visible_from = submission_exercise.calculated_remarks_visible_from()

        return ReviewSubmissionAuthorityParams(
            is_confirmable=is_confirmable,
            can_view_submission_score=can_view_submission_score,
            can_view_submission_remarks=can_view_submission_remarks,
            user_authority_on_course=user_authority_on_course,
            score_visible_from=score_visible_from,
            remarks_visible_from=remarks_visible_from,
        )

    @classmethod
    def make_from_context(
        cls, context: RequestContext, submission: Submission
    ) -> "ReviewSubmissionAuthorityParams":
        submission_exercise: Exercise = submission.exercise

        is_confirmable = context.user_authority.can_confirm_submission
        can_view_submission_score = _can_context_view_submission_score(
            context, submission
        )
        can_view_submission_remarks = _can_context_view_submission_remarks(
            context, submission
        )
        user_authority_on_course = context.user_authority_on_course
        score_visible_from = submission_exercise.calculated_score_visible_from()
        remarks_visible_from = submission_exercise.calculated_remarks_visible_from()

        return ReviewSubmissionAuthorityParams(
            is_confirmable=is_confirmable,
            can_view_submission_score=can_view_submission_score,
            can_view_submission_remarks=can_view_submission_remarks,
            user_authority_on_course=user_authority_on_course,
            score_visible_from=score_visible_from,
            remarks_visible_from=remarks_visible_from,
        )


class SubmissionReviewData(BaseModel):
    id: int
    is_confirmed: bool
    review_grade: Optional[int]
    review_comment: str
    reviewer_remarks: str


# 更新をスキップするための指定子
# NOTE str を継承しないことで、 JSON からの変換を拒絶できることを利用して、
#      Pythonコード側からのみ「SKIP_UPDATE」機能の利用を可能にする。
class SpecialValueEnum(enum.Enum):
    SKIP_UPDATE = "__skip_update__"


class SubmissionConfirmData(BaseModel):
    is_confirmed: Union[bool, Literal[SpecialValueEnum.SKIP_UPDATE]]
    review_grade: Union[Optional[int], Literal[SpecialValueEnum.SKIP_UPDATE]]
    review_comment: Union[str, Literal[SpecialValueEnum.SKIP_UPDATE]]
    reviewer_remarks: Union[str, Literal[SpecialValueEnum.SKIP_UPDATE]]

    @classmethod
    def from_review_data(
        cls,
        review_data: SubmissionReviewData,
        *,
        authority_params: ReviewSubmissionAuthorityParams,
    ) -> "SubmissionConfirmData":
        # 確定権限がなければ更新をスキップ
        is_confirmed: Union[
            bool, Literal[SpecialValueEnum.SKIP_UPDATE]
        ] = review_data.is_confirmed
        if not authority_params.is_confirmable:
            is_confirmed = SpecialValueEnum.SKIP_UPDATE

        # score の閲覧権限がなければ当然編集権限もない
        review_grade: Union[
            Optional[int], Literal[SpecialValueEnum.SKIP_UPDATE]
        ] = review_data.review_grade
        if not authority_params.can_view_submission_score:
            review_grade = SpecialValueEnum.SKIP_UPDATE

        # remarks の閲覧権限がなければ当然編集権限もない
        reviewer_remarks: Union[
            str, Literal[SpecialValueEnum.SKIP_UPDATE]
        ] = review_data.reviewer_remarks
        if not authority_params.can_view_submission_remarks:
            reviewer_remarks = SpecialValueEnum.SKIP_UPDATE

        return SubmissionConfirmData(
            is_confirmed=is_confirmed,
            review_grade=review_grade,
            review_comment=review_data.review_comment,
            reviewer_remarks=reviewer_remarks,
        )


def _is_skip_update(value: Union[Any, Literal[SpecialValueEnum.SKIP_UPDATE]]) -> bool:
    return value == SpecialValueEnum.SKIP_UPDATE


def confirm_submission(
    submission: Submission, request_user: User, data: SubmissionConfirmData
) -> Tuple[Submission, List[str], List[str]]:
    updated_items: List[str] = []
    updated_fields: List[str] = []
    current_datetime = get_current_datetime()

    TIsChanged = TypeVar("TIsChanged")

    def is_changed(
        current: TIsChanged,
        updated: Union[TIsChanged, Literal[SpecialValueEnum.SKIP_UPDATE]],
    ) -> bool:
        if _is_skip_update(updated):
            return False
        return current != updated


    if is_changed(submission.is_lecturer_evaluation_confirmed, data.is_confirmed):
        submission.is_lecturer_evaluation_confirmed = data.is_confirmed
        submission.confirmed_at = current_datetime
        submission.confirmed_by = request_user
        updated_items.append("Confirm")
        updated_fields.extend(
            (
                "is_lecturer_evaluation_confirmed",
                "confirmed_at",
                "confirmed_by",
            )
        )

    if is_changed(submission.lecturer_grade, data.review_grade):
        submission.lecturer_grade = data.review_grade
        updated_items.append("Score")
        updated_fields.append("lecturer_grade")

    if is_changed(submission.lecturer_comment, data.review_comment):
        submission.lecturer_comment = data.review_comment
        submission.lecturer_comment_updated_at = current_datetime
        submission.lecturer_comment_updated_by = request_user
        updated_items.append("Comment")
        updated_fields.extend(
            (
                "lecturer_comment",
                "lecturer_comment_updated_at",
                "lecturer_comment_updated_by",
            )
        )

    if is_changed(submission.reviewer_remarks, data.reviewer_remarks):
        submission.reviewer_remarks = data.reviewer_remarks
        submission.reviewer_remarks_updated_at = current_datetime
        submission.reviewer_remarks_updated_by = request_user
        updated_items.append("Remarks")
        updated_fields.extend(
            (
                "reviewer_remarks",
                "reviewer_remarks_updated_at",
                "reviewer_remarks_updated_by",
            )
        )

    return submission, updated_items, updated_fields


class RejudgeException(Exception):
    def __init__(self, submission_id: int) -> None:
        super().__init__(submission_id)
        self.submission_id = submission_id


class RejudgeOnNonAutoEvalException(RejudgeException):
    pass


class RejudgeOnTrialException(RejudgeException):
    pass


def rejudge_submission(submission: Submission, request_user: User) -> Submission:
    # トライアル提出に対するrejudgeはサポートしない（コピペして投げ直せば済むため）
    if submission.submission_type == SubmissionTypeEnum.TRIAL:
        raise RejudgeOnTrialException(submission.id)

    exercise = submission.exercise

    # is_autograde が当初評価でも現在設定でも False であれば、再評価をする意味はない
    if not submission.is_autograded_exercise and not exercise.is_autograde:
        raise RejudgeOnNonAutoEvalException(submission.id)

    # ATTENTION Exercise.is_autograde はユーザーによって変更される可能性がある
    rejudged_submission: Submission = Submission.objects.create(
        organization=submission.organization,
        course=submission.course,
        submission_parcel=None,
        # NOTE 再評価では再評価時点での最新の課題設定を用いる
        exercise=exercise,
        exercise_version=exercise.latest_version,
        exercise_concrete_hash=exercise.latest_concrete_hash,
        is_autograded_exercise=exercise.is_autograde,
        submitted_at=submission.submitted_at,
        submitted_by=submission.submitted_by,
        submission_file=submission.submission_file,
        submission_format=submission.submission_format,
        submission_type=submission.submission_type,
        rejudge_original_submission=submission,
        rejudge_deep_original_submission=submission.rejudge_deep_original_submission
        or submission,
        rejudge_deep_original_submission_parcel=submission.rejudge_deep_original_submission_parcel  # noqa:E501
        or submission.submission_parcel,
        rejudge_requested_at=get_current_datetime(),
        rejudge_requested_by=request_user,
    )
    rejudged_submission.update_latest_flag_eventually()

    # 現在設定で自動評価が有効であれば行う
    # ATTENTION 当初評価で True -> 現在設定で False という状況でのredjugeも考えられる
    if submission.exercise.is_autograde:
        send_submission_to_judger(rejudged_submission)

    return rejudged_submission


def get_id_nullable(obj: Optional[Any]) -> Optional[int]:
    return obj.id if obj else None


@dataclasses.dataclass
class SubmissionEvaluationData:
    # NOTE Django Model との互換性のため
    id: int  # pylint: disable=invalid-name
    submission_parcel_id: Optional[int]
    exercise__name: str
    exercise__calculated_score_visible_from: UserAuthorityEnum
    exercise__calculated_remarks_visible_from: UserAuthorityEnum
    is_autograded_exercise: bool
    submitted_at: datetime.datetime
    submitted_by__username: str
    submission_format: str
    submission_type: int
    is_latest_submission: bool
    is_delayed_submission: bool
    lecturer_grade: Optional[int]
    lecturer_comment: str
    is_lecturer_evaluation_confirmed: bool
    confirmed_at: Optional[datetime.datetime]
    confirmed_by__username: Optional[str]
    reviewer_remarks: str
    reviewer_remarks_updated_at: Optional[datetime.datetime]
    reviewer_remarks_updated_by__username: Optional[str]
    lecturer_assigned__username: Optional[str]

    is_evaluation_exists: bool
    external_submission_id: Optional[int]
    evaluated_at: Optional[datetime.datetime]
    overall_status: Optional[str]
    observed_statuses: Optional[str]
    overall_grade: Optional[int]

    @staticmethod
    def from_submission(submission: Submission) -> "SubmissionEvaluationData":
        submission_exercise: Exercise = submission.exercise
        return SubmissionEvaluationData(
            id=submission.id,
            submission_parcel_id=get_id_nullable(submission.submission_parcel),
            exercise__name=submission_exercise.name,
            exercise__calculated_score_visible_from=submission_exercise.calculated_score_visible_from(),  # noqa:E501
            exercise__calculated_remarks_visible_from=submission_exercise.calculated_remarks_visible_from(),  # noqa:E501
            is_autograded_exercise=submission.is_autograded_exercise,
            submitted_at=submission.submitted_at,
            submitted_by__username=submission.submitted_by.username,
            submission_format=submission.submission_format,
            submission_type=submission.submission_type,
            is_latest_submission=submission.is_latest_submission,
            is_delayed_submission=submission.is_submission_delayed(),
            lecturer_grade=submission.lecturer_grade,
            lecturer_comment=submission.lecturer_comment,
            is_lecturer_evaluation_confirmed=submission.is_lecturer_evaluation_confirmed,  # noqa:E501
            confirmed_at=submission.confirmed_at,
            confirmed_by__username=get_username_nullable(submission.confirmed_by),
            reviewer_remarks=submission.reviewer_remarks,
            reviewer_remarks_updated_at=submission.reviewer_remarks_updated_at,
            reviewer_remarks_updated_by__username=get_username_nullable(
                submission.reviewer_remarks_updated_by
            ),
            lecturer_assigned__username=get_username_nullable(
                submission.lecturer_assigned
            ),
            is_evaluation_exists=bool(submission.external_submission_id),
            external_submission_id=submission.external_submission_id,
            evaluated_at=submission.evaluated_at,
            overall_status=submission.overall_status,
            observed_statuses=submission.observed_statuses,
            overall_grade=submission.overall_grade,
        )


def get_user_submissions(
    request_user: User, course: Course, exercise: Exercise
) -> QuerySet[Submission]:
    """
    ログインユーザーに閲覧が許されている提出物のリストを得る
    """
    return Submission.objects.filter(
        course=course,
        exercise=exercise,
        submitted_by=request_user,
    ).order_by("-submitted_at")


@dataclasses.dataclass
class _SubmissionSummaryData:
    id: int
    exercise__name: str
    submitted_at: datetime.datetime
    overall_status: Optional[str]

    @staticmethod
    def from_submission(submission: Submission) -> "_SubmissionSummaryData":
        return _SubmissionSummaryData(
            id=submission.id,
            exercise__name=submission.exercise.name,
            submitted_at=submission.submitted_at,
            overall_status=submission.overall_status,
        )


def get_exercise_submissions_for_course_top(
    course: Course, request_user: User
) -> Dict[ExerciseName, _SubmissionSummaryData]:
    """
    course/top 画面での課題提出状況表示用
    """
    submissions = (
        Submission.objects.filter(
            course=course,
            submitted_by=request_user,
            submission_type=SubmissionTypeEnum.NORMAL,
        )
        .select_related(
            "exercise",
            "exercise__course",
        )
        .only(
            "id",
            "exercise__name",
            "exercise__checks_at",
            "exercise__closes_at",
            "exercise__course__exercise_default_closes_at",
            "is_lecturer_evaluation_confirmed",
            "lecturer_grade",
            "overall_grade",
            "submitted_at",
            "overall_status",
        )
    )

    exercise_submissions: Dict[str, _SubmissionSummaryData] = {}
    for submission in map(_SubmissionSummaryData.from_submission, submissions):
        exercise__name = submission.exercise__name
        if exercise__name not in exercise_submissions:
            exercise_submissions[exercise__name] = submission
            continue
        # NOTE Courseごとに設定項目を作ることになるかもしれない
        if exercise_submissions[exercise__name].submitted_at < submission.submitted_at:
            exercise_submissions[exercise__name] = submission

    return exercise_submissions


def is_submission_visible_to_user(
    submission: Submission, user: User, is_reviewer: bool
) -> bool:
    """提出があるユーザーにとって可視であるかを判定する"""
    # NOTE submissionのロールを提出者のものとする場合、レコードアクセス権の拡張に該当する
    #     NOTE 拡張部分: ロールを複数設定して、ユーザー個人ごとのロールもつくるか
    #     NOTE 拡張部分: 「アクセス権計算式」のような概念を導入する
    # レビュワー級にはすべて可視
    if is_reviewer:
        return True
    # 学生級でも自分の提出であれば可視
    if submission.submitted_by == user:
        return True
    # 学生級で他人の提出であっても、承認済みであり、承認後公開設定があれば可視
    if (
        submission.is_lecturer_evaluation_confirmed
        and submission.exercise.calculated_is_shared_after_confirmed()
    ):
        return True
    return False


@dataclasses.dataclass
class ExportFormatSubmission:
    exercise: str
    submitted_by: str
    submitted_at: str
    delayed: bool
    confirmed: bool
    remarks: str
    score: Optional[int]
    comment: str
    system_score: Optional[int]
