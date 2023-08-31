#!/bin/bash

if [ $1 ]; then
    target_dirs="$1"
else
    target_dirs="$(ls */environment_ready)"
fi

for env_dir in $target_dirs; do
    echo $env_dir
    rm -f "$env_dir/environment_ready"
    if [ -f "$env_dir/build_by_pyenv.sh" ]; then
        rm -rf */venv
    fi
done
