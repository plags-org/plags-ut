from typing import Callable, TypeVar

from django.core.files.base import ContentFile
from typing_extensions import ParamSpec, TypeAlias

from app_front.core.common.profile_context import ProfileContext
from app_front.models import DevelopFileStorage

_PWithProfile = ParamSpec("_PWithProfile")
_TWithProfileReturn = TypeVar("_TWithProfileReturn")
_TWithProfileFunc: TypeAlias = Callable[_PWithProfile, _TWithProfileReturn]


def with_profile(
    save_elapse_threshold: float = 0.0,
) -> Callable[[_TWithProfileFunc], _TWithProfileFunc]:
    def wrapper(func: _TWithProfileFunc) -> _TWithProfileFunc:
        def wrap(
            *args: _PWithProfile.args, **kwargs: _PWithProfile.kwargs
        ) -> _TWithProfileReturn:
            try:
                with ProfileContext() as profile_context:
                    return func(*args, **kwargs)
            finally:
                if profile_context.get_elapsed_seconds() >= save_elapse_threshold:
                    file_storage: DevelopFileStorage = (
                        DevelopFileStorage.objects.create()
                    )
                    file_storage.develop_file = ContentFile("", "profile.prof")
                    file_storage.save()
                    print(file_storage.develop_file.name)
                    profile_context.profile.dump_stats(file_storage.develop_file.name)

        return wrap

    return wrapper
