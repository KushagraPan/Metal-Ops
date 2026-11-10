"""File storage behind an interface.

`LocalStorage` is the first implementation. The rest of the application only
depends on the `Storage` protocol and the `get_storage` dependency.
"""

from app.storage.base import (
    Storage,
    StorageError,
    StorageNotFound,
    StoredFile,
)
from app.storage.local import (
    DEFAULT_STORAGE_DIR,
    LocalStorage,
    get_storage,
    storage_dir,
)

__all__ = [
    "DEFAULT_STORAGE_DIR",
    "LocalStorage",
    "Storage",
    "StorageError",
    "StorageNotFound",
    "StoredFile",
    "get_storage",
    "storage_dir",
]
