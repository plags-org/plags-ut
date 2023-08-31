import inspect
import traceback
from typing import Dict, List

from django.contrib import messages
from django.http.request import HttpRequest

from app_front.core.application_version import (
    APPLICATION_VERSION,
    ApplicationDataVersion,
    get_current_application_data_version,
    update_application_data_version,
)
from app_front.core.types import Failure, IsSuccess, Success
from app_front.data_migration.types import ApplicationDataMigrationHandler

# from app_front.data_migration.v2_6_0_to_v2_7_0 import (
#     ApplicationMigrationHandlerV2_6_0_To_V_2_7_0,
# )
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.utils.console_message import Tee, TeeSubPhase

_MIGRATION_HANDLERS: Dict[ApplicationDataVersion, ApplicationDataMigrationHandler] = {
    handler.FROM_VERSION: handler
    for handler in (
        # ApplicationMigrationHandlerV2_6_0_To_V_2_7_0(),
    )
}


def migrate_data(request: HttpRequest, tee: Tee, verbose: bool = False) -> IsSuccess:
    # NOTE どうせ短期的にはボタン押すの実装者一人だけなのであとまわし

    tee.phase("collecting information")

    handlers: List[ApplicationDataMigrationHandler] = []
    application_data_version = get_current_application_data_version()
    while application_data_version in _MIGRATION_HANDLERS:
        handler = _MIGRATION_HANDLERS[application_data_version]
        migration_title = f"from {handler.FROM_VERSION} to {handler.TO_VERSION}"
        doc = inspect.getdoc(handler.handle) or "(No documentation)"
        tee.info(f"Found migration {migration_title}: {doc}")

        handlers.append(handler)
        application_data_version = handler.TO_VERSION
        if application_data_version == APPLICATION_VERSION:
            tee.info("ApplicationVersion reached the current application version")
            break
        # KNOWLEDGE 本番では verbose フラグをつけながら一段階ずつ実施していくので、
        #     まとめて実行しないほうが結局使いやすかった。
        break
    tee.info(
        f"ApplicationVersion after migration processes: {application_data_version}"
    )

    if not handlers:
        tee.warning("No migration plan")
        messages.warning(request, f"No migration plan from {application_data_version}")
        return Failure

    tee.phase("Phase: perform migration")
    for handler in handlers:
        tee.info(f"Migrating {migration_title}: {doc}")
        try:
            with TeeSubPhase(tee):
                handler.handle(tee, verbose=verbose)
        except Exception:  # pylint: disable=broad-except
            # こけたので中断
            SLACK_NOTIFIER.error(
                f"Migration failed: {handler.FROM_VERSION=}",
                tracebacks=traceback.format_exc(),
            )
            messages.error(
                request,
                f"Migration {migration_title} failed",
            )
            tee.critical(traceback.format_exc())
            return Failure

        if verbose:
            tee.info(f"Migration {migration_title} skipped (verbose=True)")
        else:
            update_application_data_version(handler.TO_VERSION)
            tee.info(f"Migration {migration_title} completed")
    return Success
