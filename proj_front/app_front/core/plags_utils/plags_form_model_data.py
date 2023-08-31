import abc
import copy
import datetime
from typing import (
    Any,
    ClassVar,
    Dict,
    FrozenSet,
    Generic,
    List,
    Literal,
    Mapping,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from django.db.models.base import Model
from django.forms import BooleanField, Form, HiddenInput
from django.forms.utils import ErrorList
from pydantic.main import BaseModel

from app_front.core.google_drive.utils import get_resource_id_from_url
from app_front.core.plags_utils.structured_form import ItemGroupPlaceholderField
from app_front.forms import (
    FieldName,
    FormChoicesType,
    IsSharedAfterConfirmedEnum,
    MultipleCourseChoiceFormPart,
    RemarksVisibleFromEnum,
    ScoreVisibleFromEnum,
)
from app_front.models import UserAuthorityEnum
from app_front.utils.auth_util import RequestContext
from app_front.utils.exception_util import UserResponsibleException
from app_front.utils.parameter_decoder import from_user_timezone


class KeepAsIsModel(BaseModel):
    keep_as_is: Literal[True]


KeepAsIs = KeepAsIsModel(keep_as_is=True)

_UPDATE_FLAG_POSTFIX = "__update"


CourseName = str


class TargetCourseList(BaseModel):
    target_course_names: List[CourseName]


################################################################
# build_batch_edit_form

TForm = TypeVar("TForm", bound=Form)


def build_batch_edit_form(
    form_name: str,
    form_type: Type[TForm],
    base_type: Type[TForm],
    *,
    include_fields: FrozenSet[FieldName],
    exclude_fields: FrozenSet[FieldName],
    constant_fields: Optional[Dict[FieldName, Any]] = None,
) -> Type[TForm]:
    # assert issubclass(form_type, base_type)
    form = form_type()
    assert not include_fields & exclude_fields, include_fields & exclude_fields
    assert include_fields | exclude_fields == frozenset(form.fields), (
        include_fields | exclude_fields,
        frozenset(form.fields),
    )

    base_types: Tuple[type, ...] = (MultipleCourseChoiceFormPart,)
    if base_type is not Form:
        base_types = (MultipleCourseChoiceFormPart, base_type)

    class _Form(*base_types):
        def __init__(
            self,
            data: Optional[Mapping[str, Any]] = None,
            files: Optional[Mapping[str, Any]] = None,
            auto_id: Optional[Union[bool, str]] = "id_%s",
            prefix: Optional[str] = None,
            initial: Optional[Mapping[str, Any]] = None,
            error_class: Type[ErrorList] = ErrorList,
            label_suffix: Optional[str] = None,
            empty_permitted: bool = False,
            field_order: Optional[Any] = None,
            use_required_attribute: Optional[bool] = None,
            renderer: Any = None,
            *,
            course_choices: FormChoicesType,
        ) -> None:
            super().__init__(
                data,
                files,
                auto_id,
                prefix,
                initial,
                error_class,
                label_suffix,
                empty_permitted,
                field_order,
                use_required_attribute,
                renderer,
                course_choices=course_choices,
            )
            originally_required_fields: Set[FieldName] = set()
            for field_name, field in form.fields.items():
                if field_name not in include_fields:
                    continue
                # 項目グループは更新対象ではない 無視（というか維持）
                if isinstance(field, ItemGroupPlaceholderField):
                    self.fields[field_name] = copy.deepcopy(field)
                    continue

                value_update_field = BooleanField(
                    required=False, label="Update following"
                )
                value_field = copy.deepcopy(field)
                # ATTENTION required なパラメータもそのままだと「更新指定していないのに必須」になってしまい、更新できなくなってしまう
                #     NOTE これを防ぐために、この段階では必須を除去しつつ、 clean() で検証を行う
                if value_field.required:
                    value_field.required = False
                    originally_required_fields.add(field_name)

                self.fields[field_name] = value_field
                self.fields[field_name + _UPDATE_FLAG_POSTFIX] = value_update_field

                if constant_fields is not None and field_name in constant_fields:
                    value_field.widget = HiddenInput()
                    value_field.initial = constant_fields[field_name]
                    value_update_field.widget = HiddenInput()
                    value_update_field.initial = True

            class BatchEditFormContext(BaseModel):
                originally_required_fields: FrozenSet[FieldName]

            self.__batch_edit_form_context = BatchEditFormContext(
                originally_required_fields=frozenset(originally_required_fields)
            )

        def clean(self) -> dict:
            cleaned_data = super().clean()
            # ATTENTION required であったパラメータの update_flag が立っていた場合に、必須であるとエラーを返す
            for (
                required_field_name
            ) in self.__batch_edit_form_context.originally_required_fields:
                update_flag = cleaned_data.get(
                    required_field_name + _UPDATE_FLAG_POSTFIX
                )
                if not update_flag:
                    continue
                required_field = cleaned_data.get(required_field_name)
                if not required_field:
                    self.add_error(
                        required_field_name, "This field is required for update."
                    )
            # NOTE 更新指定されているフィールドがなければ無意味なリクエストとなるのでエラーとする
            num_update_field = sum(
                field_name.endswith(_UPDATE_FLAG_POSTFIX)
                and bool(cleaned_data.get(field_name))
                for field_name in self.fields
            )
            if not num_update_field:
                self.add_error(None, "No fields to update.")
            return cleaned_data

    _Form.__name__ = form_name

    return _Form


################################################################
# ModelFormFieldConverter

TModelField = TypeVar("TModelField")
TFormField = TypeVar("TFormField")


class ModelFormFieldConverter(Generic[TModelField, TFormField], metaclass=abc.ABCMeta):
    @classmethod
    def form_of_model(
        cls, context: RequestContext, model_value: TModelField
    ) -> TFormField:
        raise NotImplementedError

    @classmethod
    def model_of_form(
        cls, context: RequestContext, form_value: TFormField
    ) -> TModelField:
        raise NotImplementedError


TIdentity = TypeVar("TIdentity")


class IdentityFieldConverter(
    Generic[TIdentity], ModelFormFieldConverter[TIdentity, TIdentity]
):
    @classmethod
    def form_of_model(
        cls, context: RequestContext, model_value: TIdentity
    ) -> TIdentity:
        return model_value

    @classmethod
    def model_of_form(cls, context: RequestContext, form_value: TIdentity) -> TIdentity:
        return form_value


TOptionalDatetime = TypeVar(
    "TOptionalDatetime", datetime.datetime, Optional[datetime.datetime]
)


class DatetimeConverter(ModelFormFieldConverter[datetime.datetime, datetime.datetime]):
    @classmethod
    def form_of_model(
        cls, context: RequestContext, model_value: datetime.datetime
    ) -> datetime.datetime:
        return model_value

    @classmethod
    def model_of_form(
        cls, context: RequestContext, form_value: datetime.datetime
    ) -> datetime.datetime:
        user_timezone = context.request.user.timezone
        return from_user_timezone(user_timezone, form_value)


class OptionalDatetimeConverter(
    ModelFormFieldConverter[TOptionalDatetime, TOptionalDatetime]
):
    @classmethod
    def form_of_model(
        cls, context: RequestContext, model_value: TOptionalDatetime
    ) -> TOptionalDatetime:
        return model_value

    @classmethod
    def model_of_form(
        cls, context: RequestContext, form_value: TOptionalDatetime
    ) -> TOptionalDatetime:
        user_timezone = context.request.user.timezone
        if form_value is None:
            return form_value
        return from_user_timezone(user_timezone, form_value)


class OptionalDriveResourceIDConverter(ModelFormFieldConverter[str, str]):
    @classmethod
    def form_of_model(cls, context: RequestContext, model_value: str) -> str:
        return model_value

    @classmethod
    def model_of_form(cls, context: RequestContext, form_value: str) -> str:
        drive_resource_id = get_resource_id_from_url(form_value)
        if form_value and not drive_resource_id:
            raise UserResponsibleException("Invalid drive resource ID was given")
        return drive_resource_id


class IsSharedAfterConfirmedConverter(ModelFormFieldConverter[Optional[bool], str]):
    @classmethod
    def form_of_model(cls, context: RequestContext, model_value: Optional[bool]) -> str:
        return IsSharedAfterConfirmedEnum.from_db_value(model_value).name

    @classmethod
    def model_of_form(cls, context: RequestContext, form_value: str) -> Optional[bool]:
        return IsSharedAfterConfirmedEnum.from_choice(form_value).value


# ATTENTION アノテーションは UserAuthorityEnum になっているが、DB保持値は str なのでこれも str である
class ScoreVisibleFromConverter(
    ModelFormFieldConverter[Optional[UserAuthorityEnum], str]
):
    @classmethod
    def form_of_model(
        cls, context: RequestContext, model_value: Optional[UserAuthorityEnum]
    ) -> str:
        value = ScoreVisibleFromEnum.from_db_value(model_value).value
        if value is None:
            return "default"
        return value

    @classmethod
    def model_of_form(
        cls, context: RequestContext, form_value: str
    ) -> Optional[UserAuthorityEnum]:
        return ScoreVisibleFromEnum.from_choice(form_value).value


# ATTENTION アノテーションは UserAuthorityEnum になっているが、DB保持値は str なのでこれも str である
class RemarksVisibleFromConverter(
    ModelFormFieldConverter[Optional[UserAuthorityEnum], str]
):
    @classmethod
    def form_of_model(
        cls, context: RequestContext, model_value: Optional[UserAuthorityEnum]
    ) -> str:
        value = RemarksVisibleFromEnum.from_db_value(model_value).value
        if value is None:
            return "default"
        return value

    @classmethod
    def model_of_form(
        cls, context: RequestContext, form_value: str
    ) -> Optional[UserAuthorityEnum]:
        return RemarksVisibleFromEnum.from_choice(form_value).value


################################################################
# PlagsFormModelData

TPlagsDatabaseModel = TypeVar("TPlagsDatabaseModel", bound=Model)
TPlagsFormData = TypeVar("TPlagsFormData", bound="PlagsFormData")
TPlagsFormModelData = TypeVar("TPlagsFormModelData", bound="PlagsFormModelData")

TField = Any
TFieldsDiff = Dict[str, Tuple[TField, TField]]  # field_name: (current, incoming)


class PlagsFormData(BaseModel):
    "Django.Form を Pydantic.BaseModel へマッピングする機構"

    # Django.Form.FormField.name -> BaseModel.field.name
    __key_translations__: ClassVar[Dict[str, str]] = {}
    # Django.Form.FormField.value -> BaseModel.field.value
    __field_converters__: ClassVar[Dict[str, Type[ModelFormFieldConverter]]] = {}

    def to_form_initial(self, context: RequestContext) -> dict:
        return {
            self.__key_translations__.get(key, key): self.__field_converters__.get(
                key, IdentityFieldConverter
            ).form_of_model(context, value)
            for key, value in self.dict().items()
        }

    @classmethod
    def from_form_cleaned_data(
        cls: Type[TPlagsFormData], context: RequestContext, cleaned_data: Dict[str, Any]
    ) -> TPlagsFormData:
        reversed_translations: Dict[str, str] = {
            v: k for k, v in cls.__key_translations__.items()
        }
        return cls(
            **{
                (
                    original_key := reversed_translations.get(key, key)
                ): cls.__field_converters__.get(
                    original_key, IdentityFieldConverter
                ).model_of_form(
                    context, value
                )
                for key, value in cleaned_data.items()
            }
        )

    @classmethod
    def from_form_cleaned_data_for_patch(
        cls: Type[TPlagsFormData], context: RequestContext, cleaned_data: Dict[str, Any]
    ) -> TPlagsFormData:
        reversed_translations: Dict[str, str] = {
            v: k for k, v in cls.__key_translations__.items()
        }
        cleaned_data_fields = cls._get_cleaned_data_fields_for_patch(cleaned_data)
        # NOTE フィールドの充足性はPydanticに調べてもらう
        return cls(
            **{
                (
                    model_field_name := reversed_translations.get(
                        field_name, field_name
                    )
                ): cls.__field_converters__.get(
                    model_field_name, IdentityFieldConverter
                ).model_of_form(
                    context, cleaned_data[field_name]
                )
                if update_flag
                else KeepAsIs
                for field_name, update_flag in cleaned_data_fields.items()
            }
        )

    @classmethod
    def _get_cleaned_data_fields_for_patch(
        cls, cleaned_data: Dict[str, Any]
    ) -> Dict[FieldName, bool]:
        fields_for_patch: Dict[FieldName, bool] = {}
        for field_name in cleaned_data:
            # NOTE see `build_batch_edit_form` function
            if field_name.endswith(_UPDATE_FLAG_POSTFIX):
                patch_field_name = field_name[: -len(_UPDATE_FLAG_POSTFIX)]
                assert patch_field_name in cleaned_data, patch_field_name
                assert not patch_field_name.endswith(_UPDATE_FLAG_POSTFIX), field_name
                update_flag = cleaned_data[field_name]
                assert isinstance(update_flag, bool), update_flag
                fields_for_patch[patch_field_name] = update_flag
        return fields_for_patch


class PlagsFormModelData(PlagsFormData, Generic[TPlagsDatabaseModel]):
    "Pydantic.BaseModel を Django.Model へマッピングする機構"

    __readonly_fields__: ClassVar[FrozenSet[str]] = frozenset()

    @classmethod
    def from_model(
        cls: Type[TPlagsFormModelData], record: TPlagsDatabaseModel
    ) -> TPlagsFormModelData:
        return cls(**{field: getattr(record, field) for field in cls.__fields__})

    def apply_to_model(self, record: TPlagsDatabaseModel) -> TPlagsDatabaseModel:
        """引数で受け取ったレコードのフィールドを上書きする ATTENTION 破壊的関数なので注意"""
        for field in self.__fields__:
            if field in self.__readonly_fields__:
                continue
            setattr(record, field, getattr(self, field))
        return record

    def apply_to_model_for_patch(
        self, record: TPlagsDatabaseModel
    ) -> TPlagsDatabaseModel:
        """引数で受け取ったレコードのフィールドを上書きする ATTENTION 破壊的関数なので注意"""
        for field in self.__fields__:
            if field in self.__readonly_fields__:
                continue
            value = getattr(self, field)
            if value == KeepAsIs:
                continue
            setattr(record, field, value)
        return record

    @staticmethod
    def strong_equal(v1: Any, v2: Any) -> bool:
        return type(v1) is type(v2) and v1 == v2

    def detect_diffs(
        self: TPlagsFormModelData, incoming: TPlagsFormModelData
    ) -> TFieldsDiff:
        return {
            field: (current_value, incoming_value)
            for field in self.__fields__
            if field not in self.__readonly_fields__
            and not self.strong_equal(
                current_value := getattr(self, field),
                incoming_value := getattr(incoming, field),
            )
        }

    def detect_diffs_for_patch(
        self: TPlagsFormModelData, incoming: TPlagsFormModelData
    ) -> TFieldsDiff:
        return {
            field: (current_value, incoming_value)
            for field in self.__fields__
            if field not in self.__readonly_fields__
            and not self.strong_equal(
                current_value := getattr(self, field),
                incoming_value := getattr(incoming, field),
            )
            and incoming_value != KeepAsIs
        }
