#!/usr/bin/env bash

source ../venv_proj_judge/.venv/bin/activate \
    && python -m uvicorn proj_judge.wsgi:application --host 0.0.0.0 --port 8044
