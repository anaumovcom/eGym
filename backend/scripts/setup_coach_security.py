"""Explicit local setup; secrets entered in terminal, never command arguments or source."""

import getpass
import hashlib
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet


def main() -> None:
    root = Path.home() / ".local/share/egym/coach-security"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise SystemExit("Private directory permissions required (0700)")
    password = getpass.getpass("New Coach operator password (at least 12 characters): ")
    if len(password) < 12 or password != getpass.getpass("Confirm operator password: "):
        raise SystemExit("Password mismatch or too short")
    salt = secrets.token_hex(16)
    encoded = f"scrypt${salt}$" + hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    password = ""
    # Never overwrite master key: existing ciphertext would become unrecoverable.
    master = root / "master.key"
    if not master.exists():
        fd = os.open(master, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(Fernet.generate_key())
    target = root / "operator.hash"
    temporary = root / f"operator-{secrets.token_hex(8)}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(encoded)
    os.replace(temporary, target)
    print(f"COACH_OPERATOR_HASH_FILE={target}\nCOACH_MASTER_KEY_FILE={master}")
    print("Set these paths in the backend environment. No provider requests made.")


if __name__ == "__main__":
    main()