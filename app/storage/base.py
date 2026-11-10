"""Storage interface and errors for uploaded report files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Iterable, Protocol


class StorageError(Exception):
    """A storage operation failed."""


class StorageNotFound(StorageError):
    """The requested storage key does not exist."""


@dataclass(frozen=True)
class StoredFile:
    key: str
    size_bytes: int


class Storage(Protocol):
    """The only way the application reads or writes report bytes."""

    def save(self, chunks: Iterable[bytes]) -> StoredFile:
        """Write a stream to a new random key and return its size."""
        ...

    def open(self, key: str) -> BinaryIO:
        """Open a stored file for reading."""
        ...

    def delete(self, key: str) -> None:
        """Delete a stored file if it exists."""
        ...
