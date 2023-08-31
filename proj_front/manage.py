#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "proj_front.settings")
    try:
        from django.core.management import execute_from_command_line  # pylint:disable=import-outside-toplevel
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    if sys.argv[1:] == ["create_and_test_google_drive_credential"]:
        from app_front.core.google_drive.google_drive_api import (  # pylint:disable=import-outside-toplevel
            get_file_from_google_drive_by_api,
            get_google_drive_config_dir,
            get_or_create_token,
        )

        token = get_or_create_token(get_google_drive_config_dir())
        result = get_file_from_google_drive_by_api("1sVc_hoABlogQvqTMYhckGVnDz5ohHQ91", token=token)
        print("*" * 64)
        print(result)
        print("*" * 64)
        return

    if sys.argv[-1] == "run":
        sys.argv[-1] = "runserver"
        sys.argv.append("8040")

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
