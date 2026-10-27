"""Protected business connector encryption key resolver.

One stable Fernet key is required across backend and workers. Never generate keys
at runtime; changing the key makes existing connector ciphertext unreadable.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet

class EncryptionKeyUnavailable(Exception):
    """Safe error without secret material."""


def get_business_fernet() -> Fernet:
    inline = os.getenv("BUSINESS_CONFIG_ENCRYPTION_KEY", "")
    filename = os.getenv("BUSINESS_CONFIG_ENCRYPTION_KEY_FILE", "")
    if inline and filename:
        raise EncryptionKeyUnavailable("BUSINESS_ENCRYPTION_KEY_AMBIGUOUS")
    if filename:
        path = Path(filename)
        try:
            metadata = path.stat()
            if not path.is_file() or metadata.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                raise EncryptionKeyUnavailable("BUSINESS_ENCRYPTION_KEY_FILE_INSECURE")
            if metadata.st_size > 4096:
                raise EncryptionKeyUnavailable("BUSINESS_ENCRYPTION_KEY_FILE_INVALID")
            inline = path.read_text(encoding="ascii").strip()
        except EncryptionKeyUnavailable:
            raise
        except (OSError, UnicodeError, ValueError):
            raise EncryptionKeyUnavailable("BUSINESS_ENCRYPTION_KEY_FILE_UNAVAILABLE") from None
    try:
        return Fernet(inline.encode("ascii"))
    except (ValueError, TypeError, UnicodeError):
        raise EncryptionKeyUnavailable("BUSINESS_ENCRYPTION_KEY_MISSING") from None
