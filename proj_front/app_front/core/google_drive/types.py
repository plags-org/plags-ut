import enum


class GoogleDriveFileDownloadMethod(str, enum.Enum):
    API_SERVICE_CREDENTIAL = "API_SERVICE_CREDENTIAL"
    API_TOKEN = "API_TOKEN"
    REQUESTS = "REQUESTS"
