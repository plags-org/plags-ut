#!/bin/bash

pytest --cov=app_front --cov-report=html --cov-report=term "$@"
