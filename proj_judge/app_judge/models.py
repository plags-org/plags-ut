import os
import pathlib
from typing import Final

from django.conf import settings
from django.db.models import (
    DateTimeField,
    FileField,
    Index,
    IntegerField,
    Model,
    TextField,
)
from django.utils.timezone import now

_APP_NAME: Final = os.path.split(pathlib.Path(os.path.abspath(__file__)).parent)[1]


# class Agency(Model):
#     name = TextField(max_length=255, unique=True)
#     description = TextField(max_length=255, default='')

#     class Meta:
#         db_table = f'{_APP_NAME}_agencies'
#         indexes = (
#             Index(fields=('name', )),
#         )


def get_submission_file_upload_path(
    instance: "Submission", submission_file: str
) -> str:
    return os.path.join(
        settings.DATABASE_SUBMISSION_FILE_ROOT_PATH, str(instance.id), submission_file
    )


class Submission(Model):
    # input
    # agency = ForeignKey(Agency, PROTECT)
    agency_name = TextField(max_length=64)
    agency_department_name = TextField(max_length=256)
    exercise_concrete_name = TextField(max_length=64)
    exercise_concrete_version = TextField(max_length=64)
    exercise_concrete_directory_hash = TextField(max_length=64)

    submission_file = FileField(
        upload_to=get_submission_file_upload_path, max_length=250
    )

    front_submission_id = IntegerField()

    # additional data
    submitted_host_ip = TextField(max_length=15)
    submitted_host = TextField(max_length=255)
    # NOTE これは採点サーバーへの到着時刻なので、front にはもっと早く到着している
    submitted_at = DateTimeField(default=now)
    api_version = TextField(max_length=255)

    # output
    evaluated_at = DateTimeField(null=True)
    evaluation_result_json = TextField(max_length=65535, null=True)

    class Meta:
        db_table = f"{_APP_NAME}_submissions"
        indexes = (
            # input
            Index(
                fields=(
                    "agency_name",
                    "agency_department_name",
                    "exercise_concrete_name",
                    "exercise_concrete_version",
                    "exercise_concrete_directory_hash",
                )
            ),
        )
