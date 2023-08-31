from typing import AbstractSet, Any, Callable, Dict, List, Optional


class SettingValidationError(Exception):
    pass


class _SettingNamePath:
    def __init__(self, route: Optional[List[str]] = None):
        self.route = route if route else []

    def __getitem__(self, key: str) -> "_SettingNamePath":
        return _SettingNamePath(self.route + [key])

    def __str__(self) -> str:
        if not self.route:
            return "(root)"
        return ".".join(self.route)


class SchemaAsserter:
    def __init__(self, error_prefix: str) -> None:
        self.error_prefix = error_prefix

    def assert_string64(self, setting: Any, route: _SettingNamePath) -> None:
        assert all(
            (isinstance(setting, str), len(setting) <= 64)
        ), f'{self.error_prefix} setting "{route}" must be String64, got "{setting}"'

    def assert_object_keys(
        self,
        setting: Any,
        route: _SettingNamePath,
        required_key_set: AbstractSet[str],
        optional_key_set: AbstractSet[str] = frozenset(),
    ) -> None:
        assert isinstance(
            setting, dict
        ), f'{self.error_prefix} setting "{route}" must be JSON Object'

        setting_keys_set = set(setting.keys())

        missing_keys = []
        for key in required_key_set:
            if key in setting_keys_set:
                setting_keys_set.remove(key)
            else:
                missing_keys.append(key)

        for key in optional_key_set:
            if key in setting_keys_set:
                setting_keys_set.remove(key)

        extra_keys = setting_keys_set

        assert not all(
            (missing_keys, extra_keys)
        ), f'{self.error_prefix} setting "{route}" misses "{missing_keys}" , has extra "{extra_keys}"'
        assert (
            not missing_keys
        ), f'{self.error_prefix} setting "{route}" misses "{missing_keys}"'
        assert (
            not extra_keys
        ), f'{self.error_prefix} setting "{route}" has extra "{extra_keys}"'

    def assert_children(
        self,
        setting: Any,
        route: _SettingNamePath,
        key_loader: Dict[str, Callable[[Any, _SettingNamePath], Any]],
    ) -> Dict[str, Any]:
        return {
            key: loader(setting[key], route[key]) for key, loader in key_loader.items()
        }
