"""
! Use semantic versioning !
"""
import dataclasses

from app_front.models import ApplicationDataVersionHistory


@dataclasses.dataclass(frozen=True)
class ApplicationDataVersion:
    major_version: int
    minor_version: int
    patch_version: int

    def __str__(self) -> str:
        return f"v{self.major_version}.{self.minor_version}.{self.patch_version}"


APPLICATION_MAJOR_VERSION: int = 2
APPLICATION_MINOR_VERSION: int = 7
APPLICATION_PATCH_VERSION: int = 0


APPLICATION_VERSION = ApplicationDataVersion(
    major_version=APPLICATION_MAJOR_VERSION,
    minor_version=APPLICATION_MINOR_VERSION,
    patch_version=APPLICATION_PATCH_VERSION,
)


def get_current_application_data_version() -> ApplicationDataVersion:
    try:
        latest = ApplicationDataVersionHistory.objects.latest("created_at")
        return ApplicationDataVersion(
            major_version=latest.major_version,
            minor_version=latest.minor_version,
            patch_version=latest.patch_version,
        )
    except ApplicationDataVersionHistory.DoesNotExist:
        # 管理していなかった時代（2020.11）に後付で 1.0.0 を採番
        return ApplicationDataVersion(1, 0, 0)


def update_application_data_version(version: ApplicationDataVersion) -> None:
    ApplicationDataVersionHistory.objects.create(
        major_version=version.major_version,
        minor_version=version.minor_version,
        patch_version=version.patch_version,
    )
