"""Private file storage for prescription images (rule.md §3: never expose images through public URLs).

* Files live under MEDIA_ROOT, which is NOT served by Django or by any URL in config/urls.py.
* `url()` raises on purpose: nothing can accidentally render a link to a prescription.
* Files are created 0600 and folders 0700 (only the app user can read them).
* Images are only ever returned by an authenticated, owner-checked, audited API view (apps/clinical/views.py).

Used through a callable so the migration records `core.storage.get_private_storage`, not a machine-specific path.
"""
from django.core.files.storage import FileSystemStorage


class PrivateFileSystemStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("base_url", None)
        kwargs.setdefault("file_permissions_mode", 0o600)
        kwargs.setdefault("directory_permissions_mode", 0o700)
        super().__init__(*args, **kwargs)

    def url(self, name):
        raise ValueError("Prescription images are private and have no public URL.")


def get_private_storage() -> PrivateFileSystemStorage:
    return PrivateFileSystemStorage()