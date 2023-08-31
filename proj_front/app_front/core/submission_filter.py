import contextlib
import dataclasses
import datetime
import enum
import json
import re
import time
import typing

from django.db.models.functions import Length
from django.db.models.query import QuerySet
from pydantic.fields import Field
from pydantic.main import BaseModel
from typing_extensions import TypeGuard

from app_front.core.judge_util import fetch_evaluation_result_if_necessary
from app_front.core.oc_user import get_active_course_students
from app_front.core.submission import SubmissionEvaluationData
from app_front.core.submission_filter_parser import (
    DateTime,
    ExerciseFilterValue,
    ExerciseMatchMode,
    ReferenceQuantifierEnum,
    StatusFilterEnum,
    SubmissionFilterQueryData,
    SubmissionFilterQueryIntermediateData,
    SubmissionFilterQueryParserError,
    SubmittedByFilterValue,
    TypeFilterEnum,
    UserGroupEnum,
    UserName,
    parse_submission_filter_query,
)
from app_front.core.types import ExerciseName
from app_front.models import (
    Course,
    CourseUser,
    Exercise,
    Organization,
    Submission,
    User,
    UserAuthorityEnum,
)
from app_front.utils.exception_util import SystemLogicalError


class ErrorModel(BaseModel):
    type: str
    loc: typing.Tuple[str, ...]
    msg: str

    def to_message(self) -> str:
        return f"Error on {self.loc}: {self.type}: {self.msg}"


class WarningModel(BaseModel):
    type: str
    loc: typing.Tuple[str, ...]
    msg: str

    def to_message(self) -> str:
        return f"Warning on {self.loc}: {self.type}: {self.msg}"


@dataclasses.dataclass
class SubmissionFilterQueryQueryBuilderInputContext:
    # readonly
    organization: Organization
    course: Course
    request_user: User
    is_reviewer: bool
    has_perfect_score_visible_authority: bool
    has_perfect_remarks_visible_authority: bool

    # 行が多すぎる場合に自動的に諦めない場合にTrueとする かわりにずっと待たせることになる list_exportで利用
    force_disable_too_many_rows_protection: bool = False

    # single-write cache (set iff its necessary)
    cache_shared_after_confirmed_exercise_names: typing.Optional[
        typing.FrozenSet[ExerciseName]
    ] = None


class _Constant(str, enum.Enum):
    UNSPECIFIED = "UNSPECIFIED"


class SubmissionFilterQueryQueryBuilderOutputContext(BaseModel):
    # writable
    error_list: typing.List[ErrorModel] = Field(default_factory=list)
    warning_list: typing.List[WarningModel] = Field(default_factory=list)

    def is_valid(self) -> bool:
        """
        有効であるか
        """
        return not bool(self.error_list)

    def is_valid_with_guard_query_data(
        self,
        query_data: typing.Union[
            SubmissionFilterQueryData, None, typing.Literal[_Constant.UNSPECIFIED]
        ],
    ) -> TypeGuard[SubmissionFilterQueryData]:
        """
        有効であるか

        `query_data`: 与えられた場合、有効判定と整合しているかの確認も行う
        """
        res = self.is_valid()
        if query_data != _Constant.UNSPECIFIED:
            res_expect = query_data is not None
            assert res is res_expect, (res, res_expect)
        return res


class FilterResultIsEmpty(Exception):
    pass


class SubmissionFilterQueryQueryBuilder:
    @classmethod
    def _interpret_datetime(
        cls,
        input_context: SubmissionFilterQueryQueryBuilderInputContext,
        output_context: SubmissionFilterQueryQueryBuilderOutputContext,
        value: DateTime,
        loc: typing.Tuple[str, ...],
    ) -> typing.Optional[datetime.datetime]:
        """ATTENTION: timezone is not applied in this phase."""
        # NOTE datetime should be one of following format:
        #      1. 'YYYY-MM-DD(_hh(-mm(-ss)?)?)?'
        #      2. '*' (no condition)
        if value == "*":
            return None
        datetime_regex = r"(\d{4})\-(\d{2})\-(\d{2})(T(\d{2})(:(\d{2})(:(\d{2}))?)?)?"
        i_year, i_month, i_date, i_hour, i_minute, i_second = 1, 2, 3, 5, 7, 9
        match = re.fullmatch(datetime_regex, value, flags=re.ASCII)
        if match is None:
            output_context.error_list.append(
                ErrorModel(
                    type="InvalidValue",
                    loc=loc,
                    msg=f"Invalid DateTime expression: {value!r}",
                )
            )
            return None
        try:
            year, month, date, hour, minute, second = (
                int(match[i] or 0)
                for i in (i_year, i_month, i_date, i_hour, i_minute, i_second)
            )
            return input_context.request_user.timezone.localize(
                datetime.datetime(year, month, date, hour, minute, second)
            )
        except ValueError as exc:
            output_context.error_list.append(
                ErrorModel(
                    type="InvalidValue",
                    loc=loc,
                    msg=f"Invalid DateTime value: {value!r} ({exc})",
                )
            )
            return None

    @classmethod
    def _interpret_optional_user(
        cls,
        output_context: SubmissionFilterQueryQueryBuilderOutputContext,
        value: UserName,
        loc: typing.Tuple[str, ...],
    ) -> typing.Optional[User]:
        del output_context, loc
        with contextlib.suppress(User.DoesNotExist):
            return User.objects.get(username=value)
        # output_context.warning_list.append(
        #     WarningModel(
        #         type="UserNotExist", loc=loc, msg=f"User not found: {value!r}"
        #     )
        # )
        return None

    @classmethod
    def _interpret_submitted_by(
        cls,
        input_context: SubmissionFilterQueryQueryBuilderInputContext,
        output_context: SubmissionFilterQueryQueryBuilderOutputContext,
        submitted_by: SubmittedByFilterValue,
    ) -> typing.List[User]:
        if isinstance(submitted_by, UserGroupEnum):
            if submitted_by == UserGroupEnum.SELF:
                return [input_context.request_user]
            student_authority = UserAuthorityEnum(UserAuthorityEnum.STUDENT).value
            # 全学生の提出では、Banされたユーザーのものも見える (これは学生には指定できない値)
            if submitted_by == UserGroupEnum.STUDENT:
                return [
                    course_user.user
                    for course_user in CourseUser.objects.filter(
                        course=input_context.course, authority=student_authority
                    ).select_related("user")
                ]
            # 学生以外の提出では、Banされたユーザーのものも見える (これは学生には指定できない値)
            if submitted_by == UserGroupEnum.NON_STUDENT:
                return [
                    course_user.user
                    for course_user in CourseUser.objects.filter(
                        course=input_context.course
                    )
                    .exclude(authority=student_authority)
                    .select_related("user")
                ]
            # 現学生の提出では、Banされたユーザーのものは見せない (これは学生にも指定できる値)
            if submitted_by == UserGroupEnum.CURRENT_STUDENT:
                return [
                    course_user.user
                    for course_user in get_active_course_students(
                        input_context.course
                    ).select_related("user")
                ]
            raise SystemLogicalError(f"Unexpected {submitted_by=}")
        user = cls._interpret_optional_user(
            output_context, submitted_by, ("submitted_by",)
        )
        if user is None:
            return []
        return [user]

    @classmethod
    def _interpret_exercise(
        cls,
        input_context: SubmissionFilterQueryQueryBuilderInputContext,
        output_context: SubmissionFilterQueryQueryBuilderOutputContext,
        exercise: ExerciseFilterValue,
    ) -> typing.List[Exercise]:
        # NOTE not-open な課題の存在性が漏れる恐れがあるが、気にしないことにした
        del output_context
        if exercise.match_mode == ExerciseMatchMode.EXACT:
            try:
                exercise_list = [
                    Exercise.objects.get(
                        course=input_context.course, name=exercise.exercise_name
                    )
                ]
            except Exercise.DoesNotExist:
                exercise_list = []
        elif exercise.match_mode == ExerciseMatchMode.PREFIX:
            exercise_list = [
                e
                for e in Exercise.objects.filter(course=input_context.course).only(
                    "name"
                )
                if e.name.startswith(exercise.exercise_name)
            ]
        else:
            raise ValueError(exercise.match_mode)
        # if not exercise_list:
        #     output_context.warning_list.append(
        #         WarningModel(
        #             type="ExerciseNotExist",
        #             loc=("exercise",),
        #             msg=f"Exercise not found: {exercise.to_source()!r}",
        #         )
        #     )
        return exercise_list

    @classmethod
    def validate_query_string(
        cls,
        input_context: SubmissionFilterQueryQueryBuilderInputContext,
        query: str,
    ) -> typing.Tuple[
        SubmissionFilterQueryQueryBuilderOutputContext,
        typing.Optional[SubmissionFilterQueryData],
    ]:
        output_context = SubmissionFilterQueryQueryBuilderOutputContext()
        try:
            query_intermediate = parse_submission_filter_query(query)
        except SubmissionFilterQueryParserError as e:
            output_context.error_list.append(
                ErrorModel(type="InvalidSyntax", loc=("query",), msg=e.error_message)
            )
            return output_context, None
        query_data = cls._data_from_intermediate(query_intermediate, output_context)
        cls._validate_filter_authority(input_context, output_context, query_data)
        if not output_context.is_valid():
            return output_context, None
        return output_context, query_data

    @classmethod
    def _data_from_intermediate(
        cls,
        intermediate: SubmissionFilterQueryIntermediateData,
        output_context: SubmissionFilterQueryQueryBuilderOutputContext,
    ) -> SubmissionFilterQueryData:
        data: dict = {}
        for key, value in intermediate.dict().items():
            if not value:
                continue
            if len(value) >= 2:
                output_context.error_list.append(
                    ErrorModel(
                        type="ConditionCollision",
                        loc=(key,),
                        msg=f"Multiple conditions specified for {key}",
                    )
                )
            data[key] = value[0]
        return SubmissionFilterQueryData.parse_obj(data)

    @classmethod
    def _validate_filter_authority(
        cls,
        input_context: SubmissionFilterQueryQueryBuilderInputContext,
        output_context: SubmissionFilterQueryQueryBuilderOutputContext,
        query_data: SubmissionFilterQueryData,
    ) -> None:
        def add_authority_error(filter_name: str) -> None:
            msg = f"Forbidden condition: {filter_name}"
            output_context.error_list.append(
                ErrorModel(type="NoAuthority", loc=(filter_name,), msg=msg)
            )

        # NOTE "score_visible_from" の設定次第では、lecturer 未満の権限のユーザーにとって、
        #      score に閲覧権のない課題が発生しうる。このようなユーザーに対しては絞り込み条件を許さない。
        # NOTE 頑張れば実装できなくもないかもしれないが、実装コストがユーザー価値に見合わないのでやめた。
        if not input_context.has_perfect_score_visible_authority:
            if query_data.score is not None:
                add_authority_error("score")

        # NOTE "remarks_visible_from" の設定次第では、lecturer 未満の権限のユーザーにとって、
        #      remarks に閲覧権のない課題が発生しうる。このようなユーザーに対しては絞り込み条件を許さない。
        if not input_context.has_perfect_remarks_visible_authority:
            if query_data.remarks is not None:
                add_authority_error("remarks")

        # レビュワーには（↑を除き）全権を与える
        if input_context.is_reviewer:
            # NOTE type は隠し機能として提供はする（UIからは隠匿するが）
            return

        # 非レビュワー（学生）は "submitted_by" に (self), (current-student) のみ指定可能。
        # 無指定の場合は (current-student) 指定を補う。
        if query_data.submitted_by is None:
            query_data.submitted_by = UserGroupEnum.CURRENT_STUDENT
        if query_data.submitted_by not in (
            UserGroupEnum.SELF,
            UserGroupEnum.CURRENT_STUDENT,
        ):
            add_authority_error("submitted_by")

        # NOTE comment は非レビュワーにも検索を許す。

        if query_data.commented is not None:
            add_authority_error("commented")
        if query_data.commented_by is not None:
            add_authority_error("commented_by")

        # NOTE "remarks_visible_from" の設定によって秘匿したいのは内容であり、誰が記載したかについては絞り込めてよい。
        if query_data.remarked_by is not None:
            add_authority_error("remarked_by")

        if query_data.confirmed is not None:
            add_authority_error("confirmed")
        if query_data.confirmed_by is not None:
            add_authority_error("confirmed_by")

    @classmethod
    def build_filter_db_query(
        cls,
        input_context: SubmissionFilterQueryQueryBuilderInputContext,
        output_context: SubmissionFilterQueryQueryBuilderOutputContext,
        data: SubmissionFilterQueryData,
        db_conditions: QuerySet[Submission],
    ) -> typing.Tuple[QuerySet[Submission], bool]:
        "apply_on_db_conditions"
        # courseを適用
        db_conditions = db_conditions.filter(course=input_context.course)

        # NOTE 通常の教員には type:20 の存在を秘匿するのでデフォルトでは type:10 だけ出す
        if data.type is None:
            data.type = TypeFilterEnum.NORMAL
        db_conditions = db_conditions.filter(submission_type=data.type)
        # DB側で難しい演算が必要なためPython側で処理するもの（JSON.parse）
        # if data.status:
        #     db_conditions['status'] = data.status
        # if data.tag:
        #     db_conditions['tag'] = ...
        if data.score is not None:
            if data.score.is_null():
                db_conditions = db_conditions.filter(lecturer_grade__isnull=True)
            else:
                db_conditions = db_conditions.filter(lecturer_grade=data.score.value)
        submitted_by_list: typing.List[User] = []
        if data.submitted_by is not None:
            submitted_by_list = cls._interpret_submitted_by(
                input_context, output_context, data.submitted_by
            )
            if not submitted_by_list:
                raise FilterResultIsEmpty
            db_conditions = db_conditions.filter(submitted_by__in=submitted_by_list)
        exercise_list: typing.List[Exercise] = []
        if data.exercise is not None:
            exercise_list = cls._interpret_exercise(
                input_context, output_context, data.exercise
            )
            if not exercise_list:
                raise FilterResultIsEmpty
            db_conditions = db_conditions.filter(exercise__in=exercise_list)
        # 現状ではまだ is_latest_submission の値を信用できないためPythonで行う (no transaction)
        # if data.latest is not None:
        #     db_conditions = db_conditions.filter(is_latest_submission=data.latest)
        # if data.delayed is not None:
        #     db_conditions = db_conditions.filter(is_latest_submission=data.delayed)
        # DB側で難しい演算が必要なためPython側で処理するもの(難しいかは正直謎)
        # if data.comment is not None:
        #     db_conditions = db_conditions.filter(comment__contains=data.comment)
        if data.commented is not None:
            db_conditions = db_conditions.annotate(
                lecturer_comment_len=Length("lecturer_comment")
            )
            if data.commented:
                db_conditions = db_conditions.filter(lecturer_comment_len__gt=0)
            else:
                db_conditions = db_conditions.filter(lecturer_comment_len=0)

        if data.commented_by is not None:
            if isinstance(data.commented_by, ReferenceQuantifierEnum):
                if data.commented_by == ReferenceQuantifierEnum.ANY:
                    db_conditions = db_conditions.filter(
                        lecturer_comment_updated_by__isnull=False
                    )
                elif data.commented_by == ReferenceQuantifierEnum.NONE:
                    db_conditions = db_conditions.filter(
                        lecturer_comment_updated_by__isnull=True
                    )
                else:
                    raise SystemLogicalError(f"Unexpected {data.commented_by=}")
            elif isinstance(data.commented_by, UserName):
                commented_by = cls._interpret_optional_user(
                    output_context, data.commented_by, ("commented_by",)
                )
                if commented_by is None:
                    raise FilterResultIsEmpty
                db_conditions = db_conditions.filter(
                    lecturer_comment_updated_by=commented_by
                )
            else:
                raise SystemLogicalError(f"Unexpected {data.commented_by=}")

        # DB側で難しい演算が必要なためPython側で処理する (本当に難しいかは正直謎)
        # if data.remarks is not None:
        #     ...

        if data.remarked_by is not None:
            if isinstance(data.remarked_by, ReferenceQuantifierEnum):
                if data.remarked_by == ReferenceQuantifierEnum.ANY:
                    db_conditions = db_conditions.filter(
                        reviewer_remarks_updated_by__isnull=False
                    )
                elif data.remarked_by == ReferenceQuantifierEnum.NONE:
                    db_conditions = db_conditions.filter(
                        reviewer_remarks_updated_by__isnull=True
                    )
                else:
                    raise SystemLogicalError(f"Unexpected {data.remarked_by=}")
            elif isinstance(data.remarked_by, UserName):
                remarked_by = cls._interpret_optional_user(
                    output_context, data.remarked_by, ("remarked_by",)
                )
                if remarked_by is None:
                    raise FilterResultIsEmpty
                db_conditions = db_conditions.filter(
                    reviewer_remarks_updated_by=remarked_by
                )
            else:
                raise SystemLogicalError(f"Unexpected {data.remarked_by=}")

        if data.confirmed is not None:
            db_conditions = db_conditions.filter(
                is_lecturer_evaluation_confirmed=data.confirmed
            )
        if data.confirmed_by is not None:
            confirmed_by = cls._interpret_optional_user(
                output_context, data.confirmed_by, ("confirmed_by",)
            )
            if confirmed_by is None:
                raise FilterResultIsEmpty
            db_conditions = db_conditions.filter(confirmed_by=confirmed_by)
        if data.rejudged is not None:
            db_conditions = db_conditions.filter(
                rejudge_requested_by__isnull=not data.rejudged
            )
        if data.rejudged_by is not None:
            rejudged_by = cls._interpret_optional_user(
                output_context, data.rejudged_by, ("rejudged_by",)
            )
            if rejudged_by is None:
                raise FilterResultIsEmpty
            db_conditions = db_conditions.filter(rejudge_requested_by=rejudged_by)
        if data.since is not None:
            since = cls._interpret_datetime(
                input_context, output_context, data.since, ("since",)
            )
            if since is not None:
                db_conditions = db_conditions.filter(submitted_at__gte=since)
        if data.until is not None:
            until = cls._interpret_datetime(
                input_context, output_context, data.until, ("until",)
            )
            if until is not None:
                db_conditions = db_conditions.filter(submitted_at__lt=until)

        def _is_enable_too_many_rows_protection() -> bool:
            if data.limit is not None:
                return False
            # レビュワーでなければすべて許容
            if not input_context.is_reviewer:
                return False
            # レビュワーのデフォルト制約は許容
            if len(exercise_list) == 1 and data.latest is True:
                return False
            # 他にも十分に絞られると思える制約は許容
            disable_conditions = dict(
                status=data.status in (StatusFilterEnum.FE, StatusFilterEnum.WJ),
                tag=data.tag is not None
                and not any(tag in data.tag for tag in ("CO", "CS")),
                submitted_by=len(submitted_by_list) <= 1,
                comment=data.comment is not None,
                remarks=data.remarks is not None,
            )
            # print(disable_conditions)
            if len(exercise_list) == 1 and any(disable_conditions.values()):
                return False
            return True

        # print(exercise_list, self.limit)
        enable_too_many_rows_protection = _is_enable_too_many_rows_protection()
        # print(enable_too_many_rows_protection)

        return db_conditions, enable_too_many_rows_protection

    @classmethod
    def build_python_side_filter(
        cls,
        input_context: SubmissionFilterQueryQueryBuilderInputContext,
        output_context: SubmissionFilterQueryQueryBuilderOutputContext,
        data: SubmissionFilterQueryData,
    ) -> typing.Callable[[SubmissionEvaluationData], bool]:
        "is_python_conditions_satisfied"

        def _filter(submission_evaluation_data: SubmissionEvaluationData) -> bool:
            if data.status is not None:
                if submission_evaluation_data.overall_status != data.status.value:
                    return False
            if data.tag is not None:
                found = False
                observed_statuses_json = submission_evaluation_data.observed_statuses
                if observed_statuses_json is None:
                    return False
                observed_statuses: typing.List[dict] = json.loads(
                    observed_statuses_json
                )
                for tag in observed_statuses:
                    if tag["name"] in data.tag:
                        found = True
                if not found:
                    return False
            if data.latest is not None:
                if data.latest != submission_evaluation_data.is_latest_submission:
                    return False
            if data.delayed is not None:
                if data.delayed != submission_evaluation_data.is_delayed_submission:
                    return False
            if data.comment is not None:
                if submission_evaluation_data.lecturer_comment is None:
                    return False
                if data.comment not in submission_evaluation_data.lecturer_comment:
                    return False
            if data.remarks:
                if submission_evaluation_data.reviewer_remarks is None:
                    return False
                if data.remarks not in submission_evaluation_data.reviewer_remarks:
                    return False
            # 学生ユーザーについては細かい可視性制御が必要
            if not input_context.is_reviewer:
                return cls.is_submission_evaluation_visible_to_student(
                    input_context, output_context, submission_evaluation_data
                )
            return True

        return _filter

    @classmethod
    def is_submission_evaluation_visible_to_student(
        cls,
        input_context: SubmissionFilterQueryQueryBuilderInputContext,
        output_context: SubmissionFilterQueryQueryBuilderOutputContext,
        submission_evaluation_data: SubmissionEvaluationData,
    ) -> bool:
        """
        ATTENTION: `is_submission_visible_to_user` と実装の一貫性を持つこと
        """
        del output_context
        if (
            submission_evaluation_data.submitted_by__username
            == input_context.request_user.username
        ):
            return True
        if not submission_evaluation_data.is_lecturer_evaluation_confirmed:
            return False
        assert input_context.cache_shared_after_confirmed_exercise_names is not None
        if (
            submission_evaluation_data.exercise__name
            in input_context.cache_shared_after_confirmed_exercise_names
        ):
            return True
        return False


class SubmissionEvaluationListResult(BaseModel):
    submission_evaluations: typing.List[SubmissionEvaluationData] = Field(
        default_factory=list
    )
    # クエリ実行でリミットが発動したか
    is_limit_triggered: bool = False
    # 条件が広すぎて自動的にリミット(100)を掛けたか
    is_too_many_rows_protection_triggered: bool = False
    # クエリ処理時間
    elapse_seconds: float = float("nan")


class SubmissionFilterQueryQueryExecutor:
    @staticmethod
    def get_submission_evaluations(
        input_context: SubmissionFilterQueryQueryBuilderInputContext,
        output_context: SubmissionFilterQueryQueryBuilderOutputContext,
        data: SubmissionFilterQueryData,
    ) -> SubmissionEvaluationListResult:
        """ログインユーザーに閲覧が許されている提出物のリストを得る"""
        # NOTE 追加されているのは主に SubmissionEvaluationData へ変換するときに要求されるフィールドでのN+1阻止用
        submissions: QuerySet[Submission] = (
            Submission.objects.order_by("-submitted_at", "-id")
            .select_related(
                "submission_parcel",
                "exercise",
                "exercise__course",
                "submitted_by",
                "confirmed_by",
                "lecturer_comment_updated_by",
                "reviewer_remarks_updated_by",
                "lecturer_assigned",
            )
            .only(
                "id",
                "submission_parcel__id",
                "exercise__name",
                "exercise__course__exercise_default_checks_at",
                "exercise__course__exercise_default_closes_at",
                "exercise__course__exercise_default_ends_at",
                "exercise__checks_at",
                "exercise__closes_at",
                "exercise__course__exercise_default_score_visible_from",
                "exercise__ends_at",
                "exercise__score_visible_from",
                "is_autograded_exercise",
                "submitted_at",
                "submitted_by__username",
                "submission_format",
                "submission_type",
                "is_latest_submission",
                "lecturer_grade",
                "lecturer_comment",
                "lecturer_comment_updated_at",
                "lecturer_comment_updated_by",
                "is_lecturer_evaluation_confirmed",
                "confirmed_at",
                "confirmed_by__username",
                "reviewer_remarks",
                "reviewer_remarks_updated_at",
                "reviewer_remarks_updated_by__username",
                "lecturer_assigned__username",
                "external_submission_id",
                "evaluated_at",
                "overall_status",
                "observed_statuses",
                "overall_grade",
            )
        )

        try:
            (
                submissions,
                enable_too_many_rows_protection,
            ) = SubmissionFilterQueryQueryBuilder.build_filter_db_query(
                input_context, output_context, data, submissions
            )
        except FilterResultIsEmpty:
            return SubmissionEvaluationListResult()

        if input_context.force_disable_too_many_rows_protection:
            enable_too_many_rows_protection = False

        if data.limit == 0:
            return SubmissionEvaluationListResult()

        started_at = time.monotonic()
        is_python_conditions_satisfied = (
            SubmissionFilterQueryQueryBuilder.build_python_side_filter(
                input_context, output_context, data
            )
        )
        submission_evaluations: typing.List[SubmissionEvaluationData] = []
        is_limit_triggered = False
        is_too_many_rows_protection_triggered = False
        for submission in submissions:
            fetch_evaluation_result_if_necessary(
                submission, force=input_context.is_reviewer
            )

            submission_evaluation_data = SubmissionEvaluationData.from_submission(
                submission
            )

            # クエリ条件に合致しなければ飛ばす
            if not is_python_conditions_satisfied(submission_evaluation_data):
                continue

            submission_evaluations.append(submission_evaluation_data)

            if data.limit and len(submission_evaluations) >= data.limit:
                is_limit_triggered = True
                break
            if enable_too_many_rows_protection and len(submission_evaluations) >= 100:
                is_too_many_rows_protection_triggered = True
                break
        finished_at = time.monotonic()

        elapse_seconds = finished_at - started_at

        return SubmissionEvaluationListResult(
            submission_evaluations=submission_evaluations,
            is_limit_triggered=is_limit_triggered,
            is_too_many_rows_protection_triggered=is_too_many_rows_protection_triggered,
            elapse_seconds=elapse_seconds,
        )
