#!/bin/bash

TARGET_DIR="$1"

MY_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$MY_DIR/$TARGET_DIR"

USE_PYTHON_VERSION="$(cat .python-version)"

pyenv install -s $USE_PYTHON_VERSION || exit 1
python -V || exit 1
python -m venv venv || exit 1
source venv/bin/activate || exit 1

pip install -r requirements.txt || exit 1

echo "$(date -Isec)" >> environment_ready

cd -
