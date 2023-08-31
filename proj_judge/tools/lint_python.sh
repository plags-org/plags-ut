#!/usr/bin/env bash

set -eu
function catch { code=$?; exit $((code)); }
trap catch ERR
trap 'echo "Failed at command > $BASH_COMMAND"' ERR
trap 'echo "Processing command > $BASH_COMMAND"' DEBUG

# Force $0 to be "./tools/lint_python.sh" to avoid confusion
EXPECT_SCRIPT_PATH="./tools/lint_python.sh"
if [[ "$0" != "$EXPECT_SCRIPT_PATH" ]]; then
  echo "Please run as '$EXPECT_SCRIPT_PATH'"
  exit 1
fi

# Constants
CODE_ANALYSIS_DIR=".code_analysis"

# If called with "--git-add" or "-a" option, git add generated files and exit.
while [[ $# -gt 0 ]]; do
  case $1 in
    -a|--git-add)
        git add "$CODE_ANALYSIS_DIR/flake8.log"
        git add "$CODE_ANALYSIS_DIR/mypy.log"
        # git add "$CODE_ANALYSIS_DIR/bandit.log"
        git add "$CODE_ANALYSIS_DIR/pylint.log"
        echo "✍  (local) > git commit -m 'cmd[judge]: $0'"
        exit 0
      ;;
    *)
        echo "Unknown option: $1"
        exit 1
      ;;
  esac
done

mkdir -p "$CODE_ANALYSIS_DIR"

readarray -t TARGET_SOURCE_LIST < <(git ls-files app_judge/ judge_core/ proj_judge/ | grep .py$)

time flake8 --statistics "${TARGET_SOURCE_LIST[@]}" | tee "$CODE_ANALYSIS_DIR/flake8.log"
# NOTE 出力順序が mypy 内部でのスキャン順であってアルファベット順ではなくて困るので sort で矯正
# cf. <https://github.com/python/mypy/issues/2144>
time mypy "${TARGET_SOURCE_LIST[@]}" \
    | sort -k1,1 --stable --version-sort \
    | tee "$CODE_ANALYSIS_DIR/mypy.log"
# time bandit "${TARGET_SOURCE_LIST[@]}" | tee "$CODE_ANALYSIS_DIR/bandit.log"
# NOTE 並列化すると出力順序の再現性が失われる 悲しい
time pylint --jobs=1 "${TARGET_SOURCE_LIST[@]}" | tee "$CODE_ANALYSIS_DIR/pylint.log"

echo "✍  (local) > $0 --git-add"
