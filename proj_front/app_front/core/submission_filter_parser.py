import dataclasses
import enum
import re
import typing

from pydantic.fields import Field
from pydantic.main import BaseModel
from pyparsing import (
    CharsNotIn,
    Literal,
    OneOrMore,
    Optional,
    ParseException,
    ParseExpression,
    ParseFatalException,
    ParserElement,
    ParseResults,
    Regex,
    Suppress,
    Word,
    delimitedList,
    nums,
)
from typing_extensions import TypeAlias

from app_front.utils.exception_util import (
    UserResponsibleException,
    UserResponsibleExceptionDetail,
)

_TNullable = typing.TypeVar("_TNullable")


class Nullable(typing.Generic[_TNullable]):
    def __init__(
        self,
        value_type: typing.Type[_TNullable],
        value: typing.Optional[_TNullable] = None,
    ) -> None:
        super().__init__()
        self.value_type: typing.Type[_TNullable] = value_type
        self.value: typing.Optional[_TNullable] = value

    def __eq__(self, other: typing.Any) -> bool:
        if not isinstance(other, Nullable):
            return False
        if self.value_type is not other.value_type:
            return False
        if self.is_null() != other.is_null():
            return False
        if self.is_null() is other.is_null() is True:
            return True
        return self.value == other.value

    def to_obj(self) -> dict:
        return dict(value=self.value)

    def is_null(self) -> bool:
        return self.value is None


class NullableInt(BaseModel):
    value: typing.Optional[int]

    def is_null(self) -> bool:
        return self.value is None


@typing.final
@dataclasses.dataclass(frozen=True)
class SubmissionFilterQueryParserOptions:
    source_path: str = "(unspecified)"
    debug_mode: bool = False

    @property
    @classmethod
    def DEFAULT(cls) -> "SubmissionFilterQueryParserOptions":
        return cls()


@enum.unique
class TypeFilterEnum(enum.IntEnum):
    # 10: 通常の提出
    NORMAL = 10
    # 20: トライアル提出
    TRIAL = 20
    # 70: システムによる試験提出
    SYSTEM = 70


@enum.unique
class StatusFilterEnum(str, enum.Enum):
    AS = "AS"
    FE = "FE"
    A = "A"
    WJ = "WJ"


TagCode: TypeAlias = str
TagFilterValue: TypeAlias = typing.Tuple[TagCode, ...]

ScoreFilterValue: TypeAlias = NullableInt

UserName: TypeAlias = str


@enum.unique
class UserGroupEnum(str, enum.Enum):
    SELF = "(self)"
    STUDENT = "(student)"
    NON_STUDENT = "(non-student)"
    CURRENT_STUDENT = "(current-student)"


SubmittedByFilterValue: TypeAlias = typing.Union[UserGroupEnum, UserName]


ExerciseName: TypeAlias = str


@enum.unique
class StringMatchMode(str, enum.Enum):
    EXACT = "exact"
    PREFIX = "prefix"
    POSTFIX = "postfix"
    INCLUDE = "include"


@enum.unique
class ExerciseMatchMode(str, enum.Enum):
    EXACT = StringMatchMode.EXACT
    PREFIX = StringMatchMode.PREFIX


class ExerciseFilterValue(BaseModel):
    exercise_name: ExerciseName
    match_mode: ExerciseMatchMode

    def to_source(self) -> str:
        if self.match_mode == ExerciseMatchMode.EXACT:
            return f"{self.exercise_name}$"
        if self.match_mode == ExerciseMatchMode.PREFIX:
            return self.exercise_name
        raise ValueError(self.match_mode)


@enum.unique
class ReferenceQuantifierEnum(str, enum.Enum):
    ANY = "(any)"
    NONE = "(none)"



UserNameOrAnyOrNone: TypeAlias = typing.Union[ReferenceQuantifierEnum, UserName]

LatestFilterValue: TypeAlias = bool
DelayedFilterValue: TypeAlias = bool
CommentedFilterValue: TypeAlias = bool
CommentedByFilterValue: TypeAlias = UserNameOrAnyOrNone
RemarkedByFilterValue: TypeAlias = UserNameOrAnyOrNone
ConfirmedFilterValue: TypeAlias = bool
ConfirmedByFilterValue: TypeAlias = UserName
RejudgedFilterValue: TypeAlias = bool
RejudgedByFilterValue: TypeAlias = UserName

CommentFilterValue: TypeAlias = str
RemarksFilterValue: TypeAlias = str

LimitFilterValue: TypeAlias = int

DateTime: TypeAlias = str

SinceFilterValue: TypeAlias = DateTime
UntilFilterValue: TypeAlias = DateTime


class SubmissionFilterQueryElementBase(typing.Protocol):
    value: typing.Any
    type: str


@dataclasses.dataclass
class SubmissionFilterQueryTypeElement(SubmissionFilterQueryElementBase):
    value: TypeFilterEnum
    type: typing.Literal["type"] = "type"


@dataclasses.dataclass
class SubmissionFilterQueryStatusElement(SubmissionFilterQueryElementBase):
    value: StatusFilterEnum
    type: typing.Literal["status"] = "status"


@dataclasses.dataclass
class SubmissionFilterQueryTagElement(SubmissionFilterQueryElementBase):
    value: TagFilterValue
    type: typing.Literal["tag"] = "tag"


@dataclasses.dataclass
class SubmissionFilterQueryScoreElement(SubmissionFilterQueryElementBase):
    value: ScoreFilterValue
    type: typing.Literal["score"] = "score"


@dataclasses.dataclass
class SubmissionFilterQuerySubmittedByElement(SubmissionFilterQueryElementBase):
    value: SubmittedByFilterValue
    type: typing.Literal["submitted_by"] = "submitted_by"


@dataclasses.dataclass
class SubmissionFilterQueryExerciseElement(SubmissionFilterQueryElementBase):
    value: ExerciseFilterValue
    type: typing.Literal["exercise"] = "exercise"


@dataclasses.dataclass
class SubmissionFilterQueryLatestElement(SubmissionFilterQueryElementBase):
    value: LatestFilterValue
    type: typing.Literal["latest"] = "latest"


@dataclasses.dataclass
class SubmissionFilterQueryDelayedElement(SubmissionFilterQueryElementBase):
    value: DelayedFilterValue
    type: typing.Literal["delayed"] = "delayed"


@dataclasses.dataclass
class SubmissionFilterQueryCommentedElement(SubmissionFilterQueryElementBase):
    value: CommentedFilterValue
    type: typing.Literal["commented"] = "commented"


@dataclasses.dataclass
class SubmissionFilterQueryCommentedByElement(SubmissionFilterQueryElementBase):
    value: CommentedByFilterValue
    type: typing.Literal["commented_by"] = "commented_by"


@dataclasses.dataclass
class SubmissionFilterQueryRemarkedByElement(SubmissionFilterQueryElementBase):
    value: RemarkedByFilterValue
    type: typing.Literal["remarked_by"] = "remarked_by"


@dataclasses.dataclass
class SubmissionFilterQueryConfirmedElement(SubmissionFilterQueryElementBase):
    value: ConfirmedFilterValue
    type: typing.Literal["confirmed"] = "confirmed"


@dataclasses.dataclass
class SubmissionFilterQueryConfirmedByElement(SubmissionFilterQueryElementBase):
    value: ConfirmedByFilterValue
    type: typing.Literal["confirmed_by"] = "confirmed_by"


@dataclasses.dataclass
class SubmissionFilterQueryRejudgedElement(SubmissionFilterQueryElementBase):
    value: RejudgedFilterValue
    type: typing.Literal["rejudged"] = "rejudged"


@dataclasses.dataclass
class SubmissionFilterQueryRejudgedByElement(SubmissionFilterQueryElementBase):
    value: RejudgedByFilterValue
    type: typing.Literal["rejudged_by"] = "rejudged_by"


@dataclasses.dataclass
class SubmissionFilterQueryCommentElement(SubmissionFilterQueryElementBase):
    value: bool
    type: typing.Literal["comment"] = "comment"


@dataclasses.dataclass
class SubmissionFilterQueryRemarksElement(SubmissionFilterQueryElementBase):
    value: bool
    type: typing.Literal["remarks"] = "remarks"


@dataclasses.dataclass
class SubmissionFilterQueryLimitElement(SubmissionFilterQueryElementBase):
    value: bool
    type: typing.Literal["limit"] = "limit"


@dataclasses.dataclass
class SubmissionFilterQuerySinceElement(SubmissionFilterQueryElementBase):
    value: bool
    type: typing.Literal["since"] = "since"


@dataclasses.dataclass
class SubmissionFilterQueryUntilElement(SubmissionFilterQueryElementBase):
    value: bool
    type: typing.Literal["until"] = "until"


SubmissionFilterQueryElementType: TypeAlias = typing.Union[
    SubmissionFilterQueryTypeElement,
    SubmissionFilterQueryStatusElement,
    SubmissionFilterQueryTagElement,
    SubmissionFilterQueryScoreElement,
    SubmissionFilterQuerySubmittedByElement,
    SubmissionFilterQueryExerciseElement,
    SubmissionFilterQueryLatestElement,
    SubmissionFilterQueryDelayedElement,
    SubmissionFilterQueryCommentedElement,
    SubmissionFilterQueryCommentedByElement,
    SubmissionFilterQueryRemarkedByElement,
    SubmissionFilterQueryConfirmedElement,
    SubmissionFilterQueryRejudgedByElement,
    SubmissionFilterQueryRejudgedElement,
    SubmissionFilterQueryConfirmedByElement,
    SubmissionFilterQueryCommentElement,
    SubmissionFilterQueryRemarksElement,
    SubmissionFilterQueryLimitElement,
    SubmissionFilterQuerySinceElement,
    SubmissionFilterQueryUntilElement,
]

FilterExprActionFunc: TypeAlias = typing.Callable[
    [ParseResults], SubmissionFilterQueryElementType
]


class SubmissionFilterQueryIntermediateData(BaseModel):
    type: typing.List[TypeFilterEnum] = Field(default_factory=list)
    status: typing.List[StatusFilterEnum] = Field(default_factory=list)
    tag: typing.List[TagFilterValue] = Field(default_factory=list)
    score: typing.List[ScoreFilterValue] = Field(default_factory=list)
    submitted_by: typing.List[SubmittedByFilterValue] = Field(default_factory=list)
    exercise: typing.List[ExerciseFilterValue] = Field(default_factory=list)
    latest: typing.List[LatestFilterValue] = Field(default_factory=list)
    delayed: typing.List[DelayedFilterValue] = Field(default_factory=list)
    commented: typing.List[CommentedFilterValue] = Field(default_factory=list)
    commented_by: typing.List[CommentedByFilterValue] = Field(default_factory=list)
    remarked_by: typing.List[RemarkedByFilterValue] = Field(default_factory=list)
    confirmed: typing.List[ConfirmedFilterValue] = Field(default_factory=list)
    confirmed_by: typing.List[ConfirmedByFilterValue] = Field(default_factory=list)
    rejudged: typing.List[RejudgedFilterValue] = Field(default_factory=list)
    rejudged_by: typing.List[RejudgedByFilterValue] = Field(default_factory=list)
    comment: typing.List[CommentFilterValue] = Field(default_factory=list)
    remarks: typing.List[RemarksFilterValue] = Field(default_factory=list)
    limit: typing.List[LimitFilterValue] = Field(default_factory=list)
    since: typing.List[SinceFilterValue] = Field(default_factory=list)
    until: typing.List[UntilFilterValue] = Field(default_factory=list)


class SubmissionFilterQueryData(BaseModel):
    type: typing.Optional[TypeFilterEnum]
    status: typing.Optional[StatusFilterEnum]
    tag: typing.Optional[TagFilterValue]
    score: typing.Optional[ScoreFilterValue]
    submitted_by: typing.Optional[SubmittedByFilterValue]
    exercise: typing.Optional[ExerciseFilterValue]
    latest: typing.Optional[LatestFilterValue]
    delayed: typing.Optional[DelayedFilterValue]
    commented: typing.Optional[CommentedFilterValue]
    commented_by: typing.Optional[CommentedByFilterValue]
    remarked_by: typing.Optional[RemarkedByFilterValue]
    confirmed: typing.Optional[ConfirmedFilterValue]
    confirmed_by: typing.Optional[ConfirmedByFilterValue]
    rejudged: typing.Optional[RejudgedFilterValue]
    rejudged_by: typing.Optional[RejudgedByFilterValue]
    comment: typing.Optional[CommentFilterValue]
    remarks: typing.Optional[RemarksFilterValue]
    limit: typing.Optional[LimitFilterValue]
    since: typing.Optional[SinceFilterValue]
    until: typing.Optional[UntilFilterValue]


class SubmissionFilterQueryParserError(UserResponsibleException):
    def __init__(self, detail: UserResponsibleExceptionDetail, **kwargs) -> None:
        super().__init__(detail, **kwargs)
        self.error_message = str(detail)


class SubmissionFilterQueryParser:
    def __init__(
        self,
        *,
        options: SubmissionFilterQueryParserOptions = SubmissionFilterQueryParserOptions.DEFAULT,
    ) -> None:
        self._options = options
        self._syntax = self._initialize_syntax()

    def _initialize_syntax(self) -> ParserElement:
        # failure_catcher = CharsNotIn(" ")
        # failure_catcher.setFailAction
        # type_value = Literal("10") ^ Literal("20") ^ Literal("70") ^ failure_catcher
        def failure_catcher(
            s: str, loc: int, _expr: ParseExpression, err: ParseException
        ) -> typing.NoReturn:
            raise ParseFatalException(err.msg, loc)

        def make_literal(name: str, expr: ParseExpression) -> ParseExpression:
            expr.setName(name)
            return expr

        def make_value(name: str, expr: ParseExpression) -> ParseExpression:
            expr.setName(name)
            expr.setFailAction(failure_catcher)
            return expr

        def make_filter_expr(
            name: str, value_expr: ParseExpression, parse_action: FilterExprActionFunc
        ) -> ParseExpression:
            expr = Suppress(name + ":") + value_expr
            expr.setName(name + "_expr")
            expr.setParseAction(parse_action)
            return expr

        def make_action(
            result_type: typing.Type[SubmissionFilterQueryElementType],
            preprocessor: typing.Callable[[ParseResults], typing.Any] = lambda x: x,
        ) -> FilterExprActionFunc:
            def _parse_action(tokens: ParseResults) -> SubmissionFilterQueryElementType:
                return result_type(value=preprocessor(tokens))

            return _parse_action

        def first_token(tokens: ParseResults) -> typing.Any:
            return tokens[0]

        type_value = make_value(
            "type_value", Literal("10") | Literal("20") | Literal("70")
        )
        type_expr_action = make_action(
            SubmissionFilterQueryTypeElement, lambda t: int(t[0])
        )
        type_expr = make_filter_expr("type", type_value, type_expr_action)

        status_value = make_value(
            "status_value", Literal("AS") | Literal("FE") | Literal("A") | Literal("WJ")
        )
        status_expr_action = make_action(
            SubmissionFilterQueryStatusElement, first_token
        )
        status_expr = make_filter_expr("status", status_value, status_expr_action)

        tag_code = make_value("tag_code", Regex(r"[0-9A-Za-z]{1,16}", flags=re.ASCII))
        tag_value = make_value("tag_value", delimitedList(tag_code, ","))
        tag_expr_action = make_action(SubmissionFilterQueryTagElement, tuple)
        tag_expr = make_filter_expr("tag", tag_value, tag_expr_action)

        int_expr = make_literal("int_expr", Optional("-") + Word(nums))
        int_expr.setParseAction(
            lambda tokens: Nullable(int, int("".join(tokens))).to_obj()
        )
        null_expr = make_literal("null_expr", Literal("(null)"))
        null_expr.setParseAction(
            lambda _tokens: ParseResults([Nullable(int, None).to_obj()])
        )

        score = make_literal("score", int_expr.copy())
        score_value = make_value("score_value", score | null_expr)
        score_expr_action = make_action(SubmissionFilterQueryScoreElement, first_token)
        score_expr = make_filter_expr("score", score_value, score_expr_action)

        username = make_literal("username", Regex(r"[\w]{4,32}", flags=re.ASCII))
        self_expr = make_literal("self_expr", Literal("(self)"))
        self_expr.setParseAction(lambda _tokens: UserGroupEnum.SELF)
        student_expr = make_literal("student_expr", Literal("(student)"))
        student_expr.setParseAction(lambda _tokens: UserGroupEnum.STUDENT)
        non_student_expr = make_literal("non_student_expr", Literal("(non-student)"))
        non_student_expr.setParseAction(lambda _tokens: UserGroupEnum.NON_STUDENT)
        current_student_expr = make_literal(
            "current_student_expr", Literal("(current-student)")
        )
        current_student_expr.setParseAction(
            lambda _tokens: UserGroupEnum.CURRENT_STUDENT
        )
        submitted_by_value = make_value(
            "submitted_by_value",
            username
            | self_expr
            | student_expr
            | non_student_expr
            | current_student_expr,
        )
        submitted_by_expr_action = make_action(
            SubmissionFilterQuerySubmittedByElement, first_token
        )
        submitted_by_expr = make_filter_expr(
            "submitted_by", submitted_by_value, submitted_by_expr_action
        )

        def exercise_expr_preprocessor(tokens: ParseResults) -> ExerciseFilterValue:
            return ExerciseFilterValue(
                exercise_name=tokens[0],
                match_mode=ExerciseMatchMode.PREFIX
                if len(tokens) == 1
                else ExerciseMatchMode.EXACT,
            )

        exercise_name = make_literal(
            "exercise_name", Regex(r"[a-zA-Z0-9_-]{1,64}", flags=re.ASCII)
        )
        exercise_value = make_value("exercise_value", exercise_name + Optional("$"))
        exercise_expr_action = make_action(
            SubmissionFilterQueryExerciseElement, exercise_expr_preprocessor
        )
        exercise_expr = make_filter_expr(
            "exercise", exercise_value, exercise_expr_action
        )

        true_expr = make_literal("true_expr", Literal("true") | Literal("1"))
        true_expr.setParseAction(lambda _tokens: True)
        false_expr = make_literal("false_expr", Literal("false") | Literal("0"))
        false_expr.setParseAction(lambda _tokens: False)
        boolean_expr = make_literal("boolean_expr", true_expr | false_expr)
        boolean_expr.setParseAction(lambda _tokens: _tokens[0])

        latest_value = make_value("latest_value", boolean_expr.copy())
        latest_expr_action = make_action(
            SubmissionFilterQueryLatestElement, first_token
        )
        latest_expr = make_filter_expr("latest", latest_value, latest_expr_action)

        delayed_value = make_value("delayed_value", boolean_expr.copy())
        delayed_expr_action = make_action(
            SubmissionFilterQueryDelayedElement, first_token
        )
        delayed_expr = make_filter_expr("delayed", delayed_value, delayed_expr_action)

        any_expr = make_literal("any_expr", Literal("(any)"))
        any_expr.setParseAction(lambda _tokens: ReferenceQuantifierEnum.ANY)
        none_expr = make_literal("none_expr", Literal("(none)"))
        none_expr.setParseAction(lambda _tokens: ReferenceQuantifierEnum.NONE)
        username_or_quantifier = make_literal(
            "username_or_quantifier", username | any_expr | none_expr
        )

        commented_value = make_value("commented_value", boolean_expr.copy())
        commented_expr_action = make_action(
            SubmissionFilterQueryCommentedElement, first_token
        )
        commented_expr = make_filter_expr(
            "commented", commented_value, commented_expr_action
        )

        commented_by_value = make_value(
            "commented_by_value", username_or_quantifier.copy()
        )
        commented_by_expr_action = make_action(
            SubmissionFilterQueryCommentedByElement, first_token
        )
        commented_by_expr = make_filter_expr(
            "commented_by", commented_by_value, commented_by_expr_action
        )

        remarked_by_value = make_value(
            "remarked_by_value", username_or_quantifier.copy()
        )
        remarked_by_expr_action = make_action(
            SubmissionFilterQueryRemarkedByElement, first_token
        )
        remarked_by_expr = make_filter_expr(
            "remarked_by", remarked_by_value, remarked_by_expr_action
        )

        confirmed_value = make_value("confirmed_value", boolean_expr.copy())
        confirmed_expr_action = make_action(
            SubmissionFilterQueryConfirmedElement, first_token
        )
        confirmed_expr = make_filter_expr(
            "confirmed", confirmed_value, confirmed_expr_action
        )

        confirmed_by_value = make_value("confirmed_by_value", username.copy())
        confirmed_by_expr_action = make_action(
            SubmissionFilterQueryConfirmedByElement, first_token
        )
        confirmed_by_expr = make_filter_expr(
            "confirmed_by", confirmed_by_value, confirmed_by_expr_action
        )

        rejudged_value = make_value("rejudged_value", boolean_expr.copy())
        rejudged_expr_action = make_action(
            SubmissionFilterQueryRejudgedElement, first_token
        )
        rejudged_expr = make_filter_expr(
            "rejudged", rejudged_value, rejudged_expr_action
        )

        rejudged_by_value = make_value("rejudged_by_value", username.copy())
        rejudged_by_expr_action = make_action(
            SubmissionFilterQueryRejudgedByElement, first_token
        )
        rejudged_by_expr = make_filter_expr(
            "rejudged_by", rejudged_by_value, rejudged_by_expr_action
        )

        raw_safe_string = make_literal("raw_safe_string", CharsNotIn(' "'))
        raw_safe_string.setParseAction(first_token)
        quoted_string = make_literal(
            "quoted_string", Suppress('"') + Regex(r'([^"]|"")*') + Suppress('"')
        )
        quoted_string.setParseAction(lambda tokens: tokens[0].replace('""', '"'))
        comment_value = make_value("comment_value", raw_safe_string | quoted_string)
        comment_expr_action = make_action(
            SubmissionFilterQueryCommentElement, first_token
        )
        comment_expr = make_filter_expr("comment", comment_value, comment_expr_action)

        remarks_value = make_value("remarks_value", raw_safe_string | quoted_string)
        remarks_expr_action = make_action(
            SubmissionFilterQueryRemarksElement, first_token
        )
        remarks_expr = make_filter_expr("remarks", remarks_value, remarks_expr_action)

        uint_expr = make_literal("uint_expr", Word(nums))
        uint_expr.setParseAction(lambda tokens: int(tokens[0]))
        limit_value = make_value("limit_value", uint_expr.copy())
        limit_expr_action = make_action(SubmissionFilterQueryLimitElement, first_token)
        limit_expr = make_filter_expr("limit", limit_value, limit_expr_action)

        datetime_expr = make_literal(
            "datetime_expr",
            Regex(r"\d{4}-\d{2}-\d{2}(T\d{2}(:\d{2}(:\d{2})?)?)?", flags=re.ASCII),
        )
        datetime_expr.setParseAction(first_token)
        since_value = make_value("since_value", datetime_expr.copy())
        since_expr_action = make_action(SubmissionFilterQuerySinceElement, first_token)
        since_expr = make_filter_expr("since", since_value, since_expr_action)
        until_value = make_value("until_value", datetime_expr.copy())
        until_expr_action = make_action(SubmissionFilterQueryUntilElement, first_token)
        until_expr = make_filter_expr("until", until_value, until_expr_action)

        keyword_value_pair = make_literal(
            "keyword_value_pair",
            (
                type_expr
                | status_expr
                | tag_expr
                | score_expr
                | submitted_by_expr
                | exercise_expr
                | latest_expr
                | delayed_expr
                | commented_expr
                | commented_by_expr
                | remarked_by_expr
                | confirmed_expr
                | confirmed_by_expr
                | rejudged_expr
                | rejudged_by_expr
                | comment_expr
                | remarks_expr
                | limit_expr
                | since_expr
                | until_expr
            ),
        )
        # NOTE 以下のようにする手もあったが、エラーメッセージがややわかりにくく変わってしまう場合があったので
        #      `parse` で前処理（ `str.strip` ）を行うことにした。
        # syntax = delimitedList(Optional(keyword_value_pair), " ")
        syntax = delimitedList(keyword_value_pair, OneOrMore(Regex(r"\s")))
        syntax.leaveWhitespace()
        syntax.setWhitespaceChars("")
        return syntax

    @staticmethod
    def _collect(
        elements: typing.List[SubmissionFilterQueryElementType],
    ) -> SubmissionFilterQueryIntermediateData:
        data = SubmissionFilterQueryIntermediateData()
        for element in elements:
            getattr(data, element.type).append(element.value)
        return data

    @classmethod
    def _get_precedes(cls, s: str, pos: int, length: int) -> str:
        assert length >= 4
        if pos < length:
            return s[:pos]
        return "..." + s[(pos - length + 3) : pos]

    @classmethod
    def _get_follows(cls, s: str, pos: int, length: int) -> str:
        assert length >= 4
        if len(s) - pos < length:
            return s[pos:]
        return s[pos : (pos + length - 3)] + "..."

    @classmethod
    def _get_precedes_follows(
        cls, s: str, pos: int, length: int, sep: str = "(!)"
    ) -> str:
        return (
            cls._get_precedes(s, pos, length) + sep + cls._get_follows(s, pos, length)
        )

    def parse(self, query: str) -> SubmissionFilterQueryIntermediateData:
        query = query.strip()
        if not query:
            return SubmissionFilterQueryIntermediateData()
        try:
            return self._collect(
                self._syntax.parseString(query, parseAll=True).asList()
            )
        except (ParseException, ParseFatalException) as exc:
            error_message = (
                f"{exc.msg} (at char {exc.loc}); "
                + self._get_precedes_follows(query, exc.loc, 16)
            )
            raise SubmissionFilterQueryParserError(error_message) from exc


_options = SubmissionFilterQueryParserOptions()
_parser = SubmissionFilterQueryParser(options=_options)


def parse_submission_filter_query(query: str) -> SubmissionFilterQueryIntermediateData:
    return _parser.parse(query)
