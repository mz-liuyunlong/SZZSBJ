"""Read-only connector encryption configuration preflight; never print the key."""
from app.modules.business_connectors.encryption_key import (
    EncryptionKeyUnavailable,
    get_business_fernet,
)

def main() -> int:
    try:
        get_business_fernet()
    except EncryptionKeyUnavailable as exc:
        print("BUSINESS_CONFIG_ENCRYPTION_PREFLIGHT: " + str(exc))
        return 2
    print("BUSINESS_CONFIG_ENCRYPTION_PREFLIGHT: READY")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
