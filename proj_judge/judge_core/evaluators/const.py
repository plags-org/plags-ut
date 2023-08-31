"""evaluator 関連の定数定義
"""
import os
from typing import Final

PLAGS_JUDGE_BASE_DIR: Final = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir
)

PYTHON_COMMAND: Final = "python"
FIREJAIL_COMMAND: Final = "firejail"
ENVIRONMENT_ROOT: Final = os.path.join(PLAGS_JUDGE_BASE_DIR, "environments")
LIMITRACE_COMMAND: Final = os.path.join(PLAGS_JUDGE_BASE_DIR, "contrib/limitrace")
TEST_RUNNER_DIR: Final = os.path.join(PLAGS_JUDGE_BASE_DIR, "runners")

STATUS_CODE_OFFSET: Final = 192


FIREJAIL_FAILURE_CODE: Final = 255
