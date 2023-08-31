from abc import abstractmethod
from typing import ClassVar, Protocol

from app_front.core.application_version import ApplicationDataVersion
from app_front.utils.console_message import Tee


class ApplicationDataMigrationHandler(Protocol):
    FROM_VERSION: ClassVar[ApplicationDataVersion]
    TO_VERSION: ClassVar[ApplicationDataVersion]

    @classmethod
    @abstractmethod
    def handle(cls, tee: Tee, *, verbose: bool = False) -> None:
        raise NotImplementedError
