#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'proj_judge.settings')
    try:
        # pylint: disable=import-outside-toplevel
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    if sys.argv[-1] == 'run':
        # pylint: disable=import-outside-toplevel
        from django.conf import settings
        port = settings.PORT
        sys.argv[-1] = 'runserver'
        sys.argv.append(str(port))

    if sys.argv[-1] == 'rq':
        # pylint: disable=import-outside-toplevel
        from django.conf import settings
        sys.argv[-1] = 'rqworker'
        sys.argv.append(settings.SUBMISSION_QUEUE_NAME)

    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
