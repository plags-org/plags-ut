"""
アプリケーション定数
"""
import os
from typing import Final

DATABASE_SUBMISSION_FILE_ROOT_PATH: Final[str] = "submission_files"
DATABASE_SUBMISSION_PARCEL_FILE_ROOT_PATH: Final[str] = "submission_parcel_files"
DATABASE_JOB_OUTCOME_FILE_ROOT_PATH: Final[str] = "job_outcome_files"
DATABASE_DEVELOP_FILE_ROOT_PATH: Final[str] = "develop_files"

UTOKYO_ECCS_MAIL_DOMAIN = "g.ecc.u-tokyo.ac.jp"
UTOKYO_ECCS_MAIL_DOMAIN_WITH_AT = "@" + UTOKYO_ECCS_MAIL_DOMAIN

CURRENT_GIT_DESCRIBE_FILEPATH = os.path.join("..", "current_git_describe.txt")
