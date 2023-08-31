#!/bin/bash

# Install pyenv
if [ ! -d .pyenv ]; then
    git clone https://github.com/pyenv/pyenv.git .pyenv
fi
if [ ! -d .pyenv/plugins/pyenv-update ]; then
    git clone https://github.com/pyenv/pyenv-update.git .pyenv/plugins/pyenv-update
fi
PYENV_ROOT="$(pwd)/.pyenv"
PYENV_PATH="$PYENV_ROOT/bin/pyenv"
eval "$($PYENV_PATH init --path)"
eval "$($PYENV_PATH init -)"
pyenv update

if [ $1 ]; then
    target_dirs="$1"
else
    target_dirs="$(ls */.python-version | xargs dirname)"
fi

for target_dir in $target_dirs; do
    echo "Building $target_dir ..."
    if [ ! -f "$target_dir/.python-version" ]; then
        echo "[ERROR] $target_dir/.python-version does not exists."
        exit 1
    fi
    ./build_with_pyenv.sh "$target_dir"
done
