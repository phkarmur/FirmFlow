from django.conf import settings
from django.core.files.storage import FileSystemStorage


def private_storage():
    """
    Storage for task attachments: a folder that Nginx / Django static serving never exposes.
    Files are only streamed by the authenticated download endpoint (spec §5.8 F2).
    Swap this for an S3/MinIO storage later without changing callers (spec D10).
    """
    return FileSystemStorage(location=str(settings.PRIVATE_MEDIA_ROOT), base_url=None)
