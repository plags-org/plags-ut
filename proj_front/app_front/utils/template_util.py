import dataclasses
import datetime
import json
import traceback
import urllib.parse
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, TypeVar, Union

from django.conf import settings
from django.db.models import FileField
from django.template.base import FilterExpression, Node, Parser, Token
from django.template.defaulttags import register
from django.template.exceptions import TemplateSyntaxError
from django.utils.safestring import SafeText, mark_safe
from pydantic import ValidationError

from app_front.config.config import APP_CONFIG
from app_front.core.custom_evaluation_tag import (
    CustomEvaluationTagData,
    CustomEvaluationTagManager,
    EvaluationTagModel,
)
from app_front.core.deadlines import get_deadline_status as _get_deadline_status
from app_front.core.exercise import (
    is_trial_on_exercise_allowed as _is_trial_on_exercise_allowed,
)
from app_front.core.judge_util import accepted_to_status as _accepted_to_status
from app_front.core.system_variable import (
    software_name_with_env as _software_name_with_env,
)
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.models import Course, Exercise, Organization, UserAuthorityEnum
from app_front.utils.auth_util import UserAuthorityDict
from app_front.utils.notebook_util import normalize_notebook as _normalize_notebook
from app_front.utils.parameter_decoder import (
    encode_custom_evaluation_tag_id as _encode_custom_evaluation_tag_id,
)
from app_front.utils.parameter_decoder import (
    encode_evaluation_id as _encode_evaluation_id,
)
from app_front.utils.parameter_decoder import (
    encode_submission_id as _encode_submission_id,
)
from app_front.utils.parameter_decoder import (
    encode_submission_parcel_id as _encode_submission_parcel_id,
)

# from django.utils.translation import gettext_lazy as _


@register.filter
def software_name_with_env(_: Any) -> str:
    return _software_name_with_env()


@register.filter
def google_auth_client_id(_: Any) -> str:
    return APP_CONFIG.GOOGLE_AUTH.client_id


@register.filter
def google_auth_hosted_domain(_: Any) -> str:
    return APP_CONFIG.GOOGLE_AUTH.hosted_domain


@register.filter
def web_graphql_endpoint_url(_: Any) -> str:
    protocol = "wss"
    if settings.IS_LOCAL:
        protocol = "ws"
    return protocol + "://" + settings.SERVER_HOSTNAME + "/graphql"


@register.filter
def apply_o_name_to_url(url: str, organization: Organization) -> str:
    return url.replace("{o_name}", organization.name)


@register.filter
def apply_c_name_to_url(url: str, course: Course) -> str:
    return url.replace("{c_name}", course.name)


@register.filter
def apply_e_name_to_url(url: str, exercise: Exercise) -> str:
    return url.replace("{e_name}", exercise.name)


@register.filter
def input_step_prefixing(current_step: int, this_step: int) -> str:
    if current_step > this_step:
        return "✅ "
    if current_step == this_step:
        return "👉 "
    return ""


@register.filter
def to_one_element_list(element: Any) -> List[Any]:
    return [element]


@register.filter
def dict_get(d: Optional[dict], key: str) -> Any:
    if d is None:
        return None
    return d.get(key)


def _to_period(period: datetime.timedelta) -> str:
    if period >= datetime.timedelta(days=366):
        years = period.days / 365.2425
        return f"{years:.02f}y"
    if period >= datetime.timedelta(days=1):
        days = period.total_seconds() / 86400
        return f"{days:.02f}d"
    if period >= datetime.timedelta(seconds=3600):
        hours = period.total_seconds() / 3600
        return f"{hours:.02f}h"
    if period >= datetime.timedelta(seconds=60):
        minutes = period.total_seconds() / 60
        return f"{minutes:.02f}m"
    seconds = period.seconds / 60
    return f"{seconds:.02f}s"


@register.filter
def to_time_remaining(dt: datetime.datetime) -> str:
    if dt is None:
        return None
    # time_remaining = dt - datetime.datetime.now(tz=pytz.timezone(settings.TIME_ZONE))
    time_remaining = dt - datetime.datetime.now(tz=datetime.timezone.utc)
    if time_remaining < datetime.timedelta():
        return "-" + _to_period(-time_remaining)
    return _to_period(time_remaining)


@register.filter
def empty_to_hyphen(data: Any):
    if not data:
        return "-"
    return data


@register.filter
def read_utf8(file_field: FileField) -> str:
    try:
        with file_field.open("r") as file:
            return file.read()
    except Exception:  # pylint: disable=broad-except
        SLACK_NOTIFIER.error(
            f"Template filter error: read_utf8({file_field})",
            tracebacks=traceback.format_exc(),
        )
        return "Detected some trouble now. Try again later ..."


@register.filter
def render_score(score: Optional[int]) -> str:
    if score is None:
        return ""
    return str(score)


@register.filter
def is_authority_lte(
    lhs: Union[UserAuthorityEnum, str], rhs: Union[UserAuthorityEnum, str]
) -> bool:
    # print("is_authority_lte", lhs, rhs)

    def _clean(authority: Union[UserAuthorityEnum, str]) -> UserAuthorityEnum:
        if isinstance(authority, UserAuthorityEnum):
            return authority
        return UserAuthorityEnum(authority)

    return _clean(lhs) <= _clean(rhs)


def is_dataclass_instance(obj):
    # see <https://docs.python.org/ja/3/library/dataclasses.html#dataclasses.is_dataclass>
    return dataclasses.is_dataclass(obj) and not isinstance(obj, type)


class JsonDataclassDatetimeEncoder(json.JSONEncoder):
    def default(self, o):
        if is_dataclass_instance(o):
            return dataclasses.asdict(o)
        if isinstance(o, datetime.datetime):
            return o.timestamp()
        return super().default(o)


@register.filter
def json_encode(some: Any):
    return json.dumps(some, indent=4, cls=JsonDataclassDatetimeEncoder)


@register.filter
def json_load(string: str):
    try:
        # print(f'json_load: {string=}')
        if string in (None, ""):
            return None
        return json.loads(string)
    except json.JSONDecodeError:
        traceback.print_exc()
        print("with following json string:")
        print(repr(string))
        return None


@register.filter
def json_load_status_if_necessary(string: str):
    try:
        # print(f'json_load: {string=}')
        if string in (None, "", "AS", "FE"):
            return string
        return json.loads(string)
    except json.JSONDecodeError:
        traceback.print_exc()
        print("with following json string:")
        print(repr(string))
        return string


ResultTypeT = str


class ResultType:
    PASS: ResultTypeT = "pass"
    FAIL: ResultTypeT = "fail"
    ERROR: ResultTypeT = "error"
    FATAL: ResultTypeT = "fatal"
    UNKNOWN: ResultTypeT = "unknown"

    RESULT_TYPES = {
        PASS: "",
        FAIL: "",
        ERROR: "",
        FATAL: "Lecturer-side trouble",
        UNKNOWN: "Result type for compatibility",
    }

    def __init__(self, result_type: ResultTypeT) -> None:
        if result_type not in self.RESULT_TYPES:
            result_type = "unknown"
        self.result_type = result_type

    def to_html(self) -> SafeText:
        # NOTE XSS対策ヨシ!!
        tooltip = ""
        if message := self.RESULT_TYPES.get(self.result_type, ""):
            tooltip = (
                f'data-bs-toggle="tooltip" data-bs-placement="top" title="{message}"'
            )
        return SafeText(
            f'<span class="result_type result_type_{self.result_type}" {tooltip}>{self.result_type}</span>'
        )


@register.filter
def result_type_as_html(result_type: ResultTypeT) -> SafeText:
    return ResultType(result_type).to_html()


@register.filter
def result_types_as_html(result_types: Iterable[ResultTypeT]) -> SafeText:
    return SafeText(
        "".join(ResultType(result_type).to_html() for result_type in result_types)
    )


@register.filter
def status_of_result_types_as_html(result_types: Iterable[ResultTypeT]) -> SafeText:
    is_successful = all(result_type == ResultType.PASS for result_type in result_types)
    status = JudgeStatus("AS") if is_successful else JudgeStatus("FE")
    return status.to_html()


_SUBMISSION_TYPE_TO_NAME = {
    10: "Normal",
    20: "Trial",
    70: "System",
}


@register.filter
def to_human_readable_submission_type(submission_type: int) -> Optional[str]:
    return _SUBMISSION_TYPE_TO_NAME.get(submission_type)


@register.filter
def accepted_to_status(is_accepted: bool) -> str:
    return _accepted_to_status(is_accepted)


class JudgeStatus:
    def __init__(self, status: Union[dict, str]):
        self.color = None
        self.background_color = None

        builtin_tags_and_descriptions = (
            CustomEvaluationTagManager.get_builtin_tags_and_descriptions_WORKAROUND()
        )

        if isinstance(status, str):
            self.code = status
            self.description = builtin_tags_and_descriptions.get(status, "")
        elif isinstance(status, dict):
            self.code = status["code"]
            self.description = status.get(
                "message"
            ) or builtin_tags_and_descriptions.get(self.code, "")

            # NOTE カスタムだったら color と background_color が指定されているのでこれを処理
            self.color = status.get("color")
            self.background_color = status.get("background_color")
        elif status is None:
            self.code = "WJ"
            self.description = builtin_tags_and_descriptions["WJ"]
        else:
            raise Exception(f"ERROR: invalid status: {status}")

    def is_builtin_WORKAROUND(self) -> bool:
        return CustomEvaluationTagManager.is_builtin_WORKAROUND(self.code)

    def is_builtin(self) -> bool:
        return CustomEvaluationTagManager.is_builtin(self.code, self.description)

    def inject_custom_design(
        self, custom_evaluation_tag: Optional[CustomEvaluationTagData]
    ) -> None:
        if custom_evaluation_tag is None:
            self.color = "#bbbbbb"
            self.background_color = "#333333"
            self.description = "!! Undefined Tag !!"
            return
        self.color = custom_evaluation_tag.color
        self.background_color = custom_evaluation_tag.background_color
        self.description = custom_evaluation_tag.description

    def to_html(self) -> SafeText:
        styles = ";".join(
            ((f"color:{self.color}",) if self.color else tuple())
            + (
                (f"background-color:{self.background_color}",)
                if self.background_color
                else tuple()
            )
        )
        if styles:
            styles = f' style="{styles}" '

        builtin_tag_class = ""
        if self.is_builtin():
            builtin_tag_class = " judge_status_builtin_tag"

        return SafeText(
            f'<span class="judge_status judge_status_{self.code}{builtin_tag_class}"{styles}'
            'data-bs-toggle="tooltip" data-bs-placement="top" '
            f'title="{self.description}">{self.code}</span>'
        )


@register.filter
def status_as_html(status: Union[dict, str]) -> SafeText:
    return JudgeStatus(status).to_html()


@register.filter
def status_set_as_html(
    status_set: Optional[Iterable[Union[dict, str]]],
    manager: CustomEvaluationTagManager,
) -> SafeText:
    # print(f'{status_set=}')
    if not status_set:
        return SafeText("")
    display_status_set = list(map(JudgeStatus, manager.filter_tags(status_set)))
    # print(f'{display_status_set=}')
    for status in display_status_set:
        if not status.is_builtin_WORKAROUND():
            status.inject_custom_design(
                manager.get_custom_evaluation_tag_by_code(status.code)
            )
    return SafeText("".join(status.to_html() for status in display_status_set))


@register.filter
def tag_set_as_html_v2(
    tag_set: Optional[Sequence[dict]], manager: CustomEvaluationTagManager
) -> SafeText:
    # print(f'{tag_set=}')
    if not tag_set:
        return SafeText("")
    tag_list: List[JudgeStatus] = []
    tag_set_clean = []
    for tag_dict in tag_set:
        try:
            tag_set_clean.append(EvaluationTagModel.parse_obj(tag_dict))
        except ValidationError:
            traceback.print_exc()
            SLACK_NOTIFIER.error(
                f"tag_set_as_html_v2 error: tag_dict = {tag_dict!r}",
                tracebacks=traceback.format_exc(),
            )
    for tag in manager.filter_tags_v2(tag_set_clean):
        tag_dict = dict(
            code=tag.name,
            message=tag.description,
            color=tag.font_color,
            background_color=tag.background_color,
        )
        judge_tag = JudgeStatus(tag_dict)
        custom_tag = manager.get_custom_evaluation_tag_by_code(judge_tag.code)
        if custom_tag is not None:
            judge_tag.inject_custom_design(custom_tag)
        tag_list.append(judge_tag)
    return SafeText("".join(tag.to_html() for tag in tag_list))


@register.filter
def to_evaluation_tag_html(custom_evaluation_tag: CustomEvaluationTagData) -> SafeText:
    return JudgeStatus(
        dict(
            code=custom_evaluation_tag.code,
            message=custom_evaluation_tag.description,
            color=custom_evaluation_tag.color,
            background_color=custom_evaluation_tag.background_color,
        )
    ).to_html()


@register.filter
def show_builtin_tags(_: Any) -> SafeText:
    return SafeText(
        "".join(
            JudgeStatus(dict(code=code, message=message)).to_html()
            for code, message in CustomEvaluationTagManager.get_builtin_tags_and_descriptions().items()
        )
    )


@register.filter
def show_builtin_statuses(_: Any) -> SafeText:
    return SafeText(
        "".join(
            JudgeStatus(dict(code=code, message=message)).to_html()
            for code, message in CustomEvaluationTagManager.get_builtin_statuses_and_descriptions().items()
        )
    )


@register.filter
def encode_submission_parcel_id(course: Course, submission_parcel_id: int) -> str:
    return _encode_submission_parcel_id(course, submission_parcel_id)


@register.filter
def encode_submission_id(course: Course, submission_id: int) -> str:
    return _encode_submission_id(course, submission_id)


@register.filter
def encode_evaluation_id(course: Course, evaluation_id: int) -> str:
    return _encode_evaluation_id(course, evaluation_id)


@register.filter
def encode_custom_evaluation_tag_id(
    course: Course, custom_evaluation_tag_id: int
) -> str:
    return _encode_custom_evaluation_tag_id(course, custom_evaluation_tag_id)


@register.filter
def get_deadline_status(
    deadline: Exercise, user_authority: UserAuthorityDict
) -> List[Tuple[str, Optional[datetime.datetime]]]:
    return _get_deadline_status(deadline, user_authority)


@register.filter
def is_trial_on_exercise_allowed(
    exercise: Exercise, user_authority: UserAuthorityDict
) -> bool:
    return _is_trial_on_exercise_allowed(exercise, user_authority)


@register.filter
def normalize_notebook(notebook_json_str: str) -> str:
    try:
        return _normalize_notebook(notebook_json_str)
    except Exception:  # pylint: disable=broad-except
        return notebook_json_str


@register.filter
def build_submission_query_filter_by_exercise(exercise: Exercise, latest: bool) -> str:
    return (
        f"exercise:{exercise.name}$ submitted_by:(current-student)"
        + " latest:true" * latest
    )


@register.filter
def to_submission_filter_query_url_param(filter_expr: str) -> str:
    return "q=" + urllib.parse.quote(filter_expr)


@register.filter
def string_thumbnail(string: str, max_length: int = 16):
    if isinstance(string, str):
        if len(string) <= max_length:
            return string.replace("\n", " ")
        return string[: max_length - 2].replace("\n", " ") + "..."
    return string


@register.filter
def ds_authority(authority: str) -> str:
    """Display Style of Authority"""
    return authority.split("_", maxsplit=1)[-1]


TAuthority = TypeVar("TAuthority", str, Optional[str])


@register.filter
def ds_authority_optional(authority: TAuthority) -> TAuthority:
    """Display Style of Authority"""
    if authority is None:
        return None
    return authority.split("_", maxsplit=1)[-1]


def _escape_submission_filter_help_tooltip_html_impl(content: str) -> str:
    # ATTENTION: `&lt;&zwj; としているのは `&zwj;` を入れないと恐らくインジェクション対策とかでうまくレンダリングされないため。
    # return content.translate({ord("<"): "&lt;&zwj;", ord(">"): "&gt;"})
    # NOTE 結局 code で囲むほうがわかりやすそうだったのでこうした
    return content.translate(
        {
            ord("{"): "<code>",
            ord("}"): "</code>",
            ord("<"): "&lt;&zwj;",
            ord(">"): "&gt;",
            ord(";"): "<br />",
        }
    )


@register.filter
def escape_submission_filter_help_tooltip_html(content: str) -> str:
    content_list = content.split("&")
    return "&amp;".join(
        map(_escape_submission_filter_help_tooltip_html_impl, content_list)
    )


class RestrictNode(Node):
    child_nodelists = ("restricted_nodes",)

    def __init__(
        self,
        subject_name: str,
        permission: str,
        html_info: Dict[str, str],
        subject: FilterExpression,
        restricted_nodes,
    ) -> None:
        self.subject_name: str = subject_name  # for better error message
        self.permission: str = permission
        self.html_info = html_info
        self.subject: FilterExpression = subject
        self.restricted_nodes = restricted_nodes

    @staticmethod
    def get_permission_by_path(subject: Any, permission_path: Sequence[str]) -> bool:
        for permission in permission_path:
            if hasattr(subject, permission):
                subject = getattr(subject, permission)
            else:
                subject = subject.get(permission)
            while callable(subject):
                try:
                    subject = subject()
                except TypeError:
                    subject = False
                    break
        return bool(subject)

    def render(self, context):
        with context.push():
            subject = self.subject.resolve(context)
            # NOTE resolve() may return `string_if_invalid` or None when self.subject is invalid.
            if subject is None or subject == "":
                return SafeText("")
            if isinstance(subject, str) and subject.startswith("INVALID_TAMPLATE"):
                return SafeText(subject)

            permission_path = self.permission.split(".")

            try:
                is_permitted = self.get_permission_by_path(subject, permission_path)

            except (AttributeError, KeyError):
                print(
                    f"[ERROR] RestrictNode.render(): subject {self.subject_name}"
                    f" ( {subject} ) has no permission {self.permission}"
                )
                if settings.DEBUG:
                    raise
                is_permitted = False

            if not is_permitted:
                return SafeText("")

            html_tag = self.html_info.get("tag", "div")
            html_tag_parts = [html_tag]
            if html_id := self.html_info.get("id"):
                html_tag_parts.append(f'id="{html_id}"')
            html_classes = ["restrict", f"restrict__{self.permission}"]
            if settings.DEBUG:
                html_classes.append(f"debug__restrict__{self.permission}")
            if html_class := self.html_info.get("class"):
                html_classes.append(html_class)
            html_tag_parts.append(f'class="{" ".join(html_classes)}"')

            nodelist = []
            nodelist.append(SafeText(f'<{" ".join(html_tag_parts)}>'))
            nodelist.append(
                SafeText(
                    f'<span class="restrict_authority_name">{self.permission}</span>'
                )
            )
            for node in self.restricted_nodes:
                nodelist.append(node.render_annotated(context))
            nodelist.append(SafeText(f"</{html_tag}>"))

            return mark_safe("".join(nodelist))


@register.tag("restrict")
def do_restrict(parser: Parser, token: Token) -> RestrictNode:
    """
    {% restrict <subject> <permission> [<HTML tag> [id <id>] [class <classes>]] %}

    {% restrict user is_staff %}
    {% restrict user is_staff tr %}
    """
    bits: List[str] = token.split_contents()
    if len(bits) not in (3, 4, 6, 8):
        raise TemplateSyntaxError(
            f"'restrict' statements should have unexpected number of words: {token.contents}"
        )

    subject_name: str = bits[1]
    permission: str = bits[2]
    html_info: Dict[str, str] = {}

    subject: FilterExpression = parser.compile_filter(subject_name)

    allowed_keys = ("id", "class")

    def parse_html_args(html_info, key, value):
        if key not in allowed_keys:
            raise TemplateSyntaxError(
                f"'restrict' statement can have only {allowed_keys} keys: {key=}, {value=}"
            )
        html_info[key] = value

    if len(bits) > 3:
        html_info["tag"] = bits[3]
        if len(bits) == 6:
            parse_html_args(html_info, *bits[4:6])
        if len(bits) == 8:
            parse_html_args(html_info, *bits[6:8])

    restricted_nodes = parser.parse(("endrestrict",))
    parser.delete_first_token()

    return RestrictNode(subject_name, permission, html_info, subject, restricted_nodes)
