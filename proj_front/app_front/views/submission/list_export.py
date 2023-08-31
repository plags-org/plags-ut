from typing import ClassVar

from app_front.views.submission.list import ListSubmissionView


class ListExportSubmissionView(ListSubmissionView):
    TEMPLATE_FILE: ClassVar[str] = "submission/list_export.html"
