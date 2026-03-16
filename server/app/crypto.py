"""
Noteward — Crypto Layer

Key hierarchy:
  master_password  (user knows, never stored)
       ↓ PBKDF2
  key_encryption_key (KEK)
       ↓ Fernet encrypt
  data_key  (stored encrypted on disk as wrapped_key.bin)
       ↓ Fernet encrypt
  secrets  (stored as .enc files)

RAM key path: /dev/shm/noteward_key  (survives only while server is running)
"""

import os
import base64
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

DATA_DIR      = Path(os.environ.get("NOTEWARD_DATA", "/app/data"))
WRAPPED_KEY   = DATA_DIR / "wrapped_key.bin"
SALT_FILE     = DATA_DIR / "kdf_salt.bin"
RAM_KEY_PATH  = Path("/dev/shm/noteward_key")
SECRETS_DIR   = DATA_DIR / "secrets"


# ── KDF ───────────────────────────────────────────────────────────────────────

def _get_or_create_salt() -> bytes:
    SALT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SALT_FILE.exists():
        salt = os.urandom(32)
        SALT_FILE.write_bytes(salt)
        SALT_FILE.chmod(0o600)
    return SALT_FILE.read_bytes()


def _derive_kek(master_password: str) -> Fernet:
    salt = _get_or_create_salt()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
    return Fernet(key)


# ── Data Key Management ───────────────────────────────────────────────────────

def setup_master_password(master_password: str) -> None:
    """First-time setup: generate data key, wrap with master password."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data_key = Fernet.generate_key()
    kek = _derive_kek(master_password)
    wrapped = kek.encrypt(data_key)
    WRAPPED_KEY.write_bytes(wrapped)
    WRAPPED_KEY.chmod(0o600)
    _store_key_in_ram(data_key)


def unlock(master_password: str) -> bool:
    """Decrypt wrapped key with master password, store in RAM. Returns True on success."""
    if not WRAPPED_KEY.exists():
        return False
    try:
        kek = _derive_kek(master_password)
        data_key = kek.decrypt(WRAPPED_KEY.read_bytes())
        _store_key_in_ram(data_key)
        return True
    except Exception:
        return False


def reset_password(master_password: str, new_password: str) -> bool:
    """Re-wrap data key with new master password. Returns True on success."""
    try:
        kek = _derive_kek(master_password)
        data_key = kek.decrypt(WRAPPED_KEY.read_bytes())
        new_kek = _derive_kek(new_password)
        wrapped = new_kek.encrypt(data_key)
        WRAPPED_KEY.write_bytes(wrapped)
        _store_key_in_ram(data_key)
        return True
    except Exception:
        return False


def reset_password_with_recovery(recovery_key: str, new_password: str) -> bool:
    """Reset master password using recovery key (raw data key, base64)."""
    try:
        data_key = base64.urlsafe_b64decode(recovery_key.strip())
        new_kek = _derive_kek(new_password)
        # Re-generate salt for added security
        salt = os.urandom(32)
        SALT_FILE.write_bytes(salt)
        wrapped = new_kek.encrypt(data_key)
        WRAPPED_KEY.write_bytes(wrapped)
        _store_key_in_ram(data_key)
        return True
    except Exception:
        return False


def is_unlocked() -> bool:
    return RAM_KEY_PATH.exists()


def is_initialized() -> bool:
    return WRAPPED_KEY.exists()


# ── RAM Key ───────────────────────────────────────────────────────────────────

def _store_key_in_ram(data_key: bytes) -> None:
    RAM_KEY_PATH.write_bytes(data_key)
    RAM_KEY_PATH.chmod(0o600)


def send_key(data_key_b64: str) -> None:
    """Accept raw data key from watcher (base64 encoded), store in RAM."""
    data_key = base64.urlsafe_b64decode(data_key_b64.strip())
    _store_key_in_ram(data_key)


def _get_fernet() -> Fernet:
    if not RAM_KEY_PATH.exists():
        raise RuntimeError("Key not in RAM. Unlock with master password first.")
    return Fernet(RAM_KEY_PATH.read_bytes())


def export_recovery_key() -> str:
    """Export raw data key as base64 (used to generate recovery file locally)."""
    if not RAM_KEY_PATH.exists():
        raise RuntimeError("Key not in RAM.")
    return base64.urlsafe_b64encode(RAM_KEY_PATH.read_bytes()).decode()


# ── Secret Storage ────────────────────────────────────────────────────────────

def store_secret(name: str, value: str) -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    f = _get_fernet()
    path = SECRETS_DIR / f"{name}.enc"
    path.write_bytes(f.encrypt(value.encode()))
    path.chmod(0o600)


def get_secret(name: str) -> str:
    path = SECRETS_DIR / f"{name}.enc"
    if not path.exists():
        raise KeyError(f"Secret '{name}' not found.")
    return _get_fernet().decrypt(path.read_bytes()).decode()


def list_secrets() -> list[str]:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in SECRETS_DIR.glob("*.enc"))


def delete_secret(name: str) -> None:
    path = SECRETS_DIR / f"{name}.enc"
    if not path.exists():
        raise KeyError(f"Secret '{name}' not found.")
    path.unlink()
