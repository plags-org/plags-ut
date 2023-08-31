import itertools
from typing import FrozenSet, Iterable, Tuple

from django.db.models.query import QuerySet

from app_front.core.types import ExerciseName
from app_front.models import Course, Exercise
from app_front.utils.auth_util import ContextUserAuthority, UserAuthorityDict
from app_front.utils.exception_util import SystemLogicalError


def is_exercise_visible_to_user_authority(
    exercise: Exercise, user_authority: ContextUserAuthority
) -> bool:
    """課題がユーザーにとって可視であるかを判定する

    - ATTENTION 直下の `is_exercise_visible_to_user_authority` との一貫性を保つこと。"""
    if user_authority.can_view_exercise:
        return True
    if user_authority.can_view_exercise_until_end:
        return not exercise.ends()
    if user_authority.can_view_exercise_published:
        return exercise.is_published()
    return False


def get_visible_exercises(
    user_authority: UserAuthorityDict, course: Course
) -> Iterable[Exercise]:
    """ユーザー権限にとって可視である課題の一覧を取得する

    - ATTENTION 直上の `is_exercise_visible_to_user_authority` との一貫性を保つこと。
    """
    if user_authority["can_view_exercise"]:
        return (
            Exercise.objects.filter(course=course)
            .select_related(
                "course",
                "created_by",
                "edited_by",
            )
            .order_by("is_draft", "name")
        )
    if user_authority["can_view_exercise_until_end"]:
        exercises: Iterable[Exercise] = (
            Exercise.objects.filter(course=course)
            .select_related("course")
            .order_by("name")
        )
        return filter(lambda exercise: not exercise.ends(), exercises)
    if user_authority["can_view_exercise_published"]:
        non_draft_exercises: Iterable[Exercise] = (
            Exercise.objects.filter(course=course, is_draft=False)
            .select_related("course")
            .order_by("name")
        )
        return filter(lambda exercise: exercise.begins_to_ends(), non_draft_exercises)
    return ()


def get_shared_after_confirmed_exercise_names(
    course: Course,
) -> FrozenSet[ExerciseName]:
    """`is_shared_after_confirmed` が有効な

    - ATTENTION `is_draft` の考慮はこの関数内では行われない。呼び出し元の責任で解釈すべし。
    """
    # course.default によって設定が有効となる課題の条件が変わる
    # KNOWLEDGE WHERE ... IN (1, null) はnullを見つけてくれない 仕方ないのでクエリをふたつに分ける
    true_exercises = Exercise.objects.filter(
        course=course, is_shared_after_confirmed=True
    )
    exercise_iters: Tuple[QuerySet[Exercise], ...] = (true_exercises,)
    if course.exercise_default_is_shared_after_confirmed:
        null_exercises = Exercise.objects.filter(
            course=course, is_shared_after_confirmed__isnull=True
        )
        exercise_iters += (null_exercises,)
    return frozenset(exercise.name for exercise in itertools.chain(*exercise_iters))


def is_trial_on_exercise_allowed(
    exercise: Exercise, user_authority: UserAuthorityDict
) -> bool:
    """トライアル提出が可能であるかを判定"""

    # 必要条件: 自動評価が有効と設定されている
    if not exercise.is_trial_enabled:
        return False

    # 必要条件: 提出権限
    if not user_authority["can_submit_submission"]:
        return False

    # 十分条件: 教員はいつでも試せる
    if user_authority["can_view_exercise"]:
        return True

    # TAは end までは試せる
    if user_authority["can_view_exercise_until_end"]:
        return not exercise.ends()

    # 学生も提出締切後には試せるように
    if user_authority["can_view_exercise_published"]:
        return exercise.closes_to_ends()

    raise SystemLogicalError("Should never come here")
