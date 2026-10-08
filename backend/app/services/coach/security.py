"""Fail-closed operator sessions and encrypted server vault. No env-key fallback."""

import hashlib
import hmac
import os
import secrets
import stat
import time
from collections import OrderedDict
from pathlib import Path

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.orm import Session
from starlette.requests import HTTPConnection

from app.core.config import get_settings
from app.models.coach import CoachCredential, CoachOperatorSession

COOKIE = "egym_coach_operator"
SESSION_SECONDS = 900
_login_limits: OrderedDict[str, tuple[float, int]] = OrderedDict()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def protected_file(path: str | None) -> bytes:
    if not path:
        raise HTTPException(503, "secure_storage_unavailable")
    target = Path(path).expanduser()
    # Resolve prohibited roots without opening or listing any private files.
    repo = Path(__file__).resolve().parents[4]
    media = Path(get_settings().media_root).resolve()
    if not target.is_absolute() or target.is_symlink() or target.resolve().is_relative_to(repo) or target.resolve().is_relative_to(media):
        raise HTTPException(503, "secure_storage_unavailable")
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise HTTPException(503, "secure_storage_unavailable")
            data = file.read(4097)
            if len(data) > 4096:
                raise HTTPException(503, "secure_storage_unavailable")
            return data.strip()
    except OSError:
        raise HTTPException(503, "secure_storage_unavailable") from None


def safe_request(request: HTTPConnection, *, mutation: bool = True) -> None:
    # No trust in Forwarded/X-Forwarded-Proto. TLS must terminate at trusted app boundary.
    if request.headers.get("forwarded") or request.headers.get("x-forwarded-proto"):
        raise HTTPException(403, "forwarded_transport_denied")
    local = request.url.hostname in {"localhost", "127.0.0.1", "::1"} and request.client is not None and request.client.host in {"127.0.0.1", "::1", "testclient"}
    scheme = {"ws": "http", "wss": "https"}.get(request.url.scheme, request.url.scheme)
    if scheme != "https" and not local:
        raise HTTPException(403, "https_required")
    origin = request.headers.get("origin")
    own_origin = f"{scheme}://{request.url.netloc}"
    if mutation and (not origin or origin not in [own_origin, *get_settings().cors_origins]):
        raise HTTPException(403, "origin_denied")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "origin_denied")


def operator_version() -> tuple[str, str]:
    encoded = protected_file(get_settings().coach_operator_hash_file).decode("ascii")
    return encoded, digest(encoded)


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${value}"


def login(db: Session, request: Request, password: str) -> str:
    safe_request(request)
    now = time.time()
    address = request.client.host if request.client else "unknown"
    since, count = _login_limits.get(address, (now, 0))
    if now - since >= 60:
        since, count = now, 0
    _login_limits[address] = (since, count + 1)
    _login_limits.move_to_end(address)
    while len(_login_limits) > 1024:
        _login_limits.popitem(last=False)
    if count >= 5:
        raise HTTPException(429, "login_rate_limited")
    encoded, version = operator_version()
    try:
        algorithm, salt, expected = encoded.split("$")
        valid = algorithm == "scrypt" and hmac.compare_digest(
            hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex(), expected,
        )
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        raise HTTPException(401, "operator_auth_required")
    db.execute(delete(CoachOperatorSession).where(CoachOperatorSession.expires_at <= now))
    # Bounded session pool; no unlimited login-created rows.
    from sqlalchemy import func, select

    if db.scalar(select(func.count()).select_from(CoachOperatorSession)) >= 64:
        raise HTTPException(429, "operator_sessions_full")
    token = secrets.token_urlsafe(32)
    db.add(CoachOperatorSession(digest=digest(token), auth_version=version, expires_at=now + SESSION_SECONDS))
    db.commit()
    return token


def authorize(db: Session, request: Request) -> None:
    safe_request(request, mutation=request.method not in {"GET", "HEAD"})
    token = request.cookies.get(COOKIE, "")
    session = db.get(CoachOperatorSession, digest(token)) if token else None
    _, version = operator_version()
    if session is None or session.expires_at <= time.time() or not hmac.compare_digest(session.auth_version, version):
        raise HTTPException(401, "operator_auth_required")


def cipher() -> Fernet:
    try:
        return Fernet(protected_file(get_settings().coach_master_key_file))
    except ValueError:
        raise HTTPException(503, "secure_storage_unavailable") from None


def credential_status(db: Session) -> dict:
    row = db.get(CoachCredential, 1)
    available = False
    try:
        cipher()
        available = True
    except HTTPException:
        pass
    return {"configured": bool(row and row.ciphertext and not row.disabled), "credentialVersion": row.version if row else 0,
            "source": "server-vault", "storageAvailable": available, "lastCheckStatus": row.last_check if row else "not_checked"}


def read_credential(db: Session) -> tuple[str, int]:
    row = db.get(CoachCredential, 1)
    if not row or row.disabled or not row.ciphertext:
        raise HTTPException(409, "credential_unavailable")
    try:
        return cipher().decrypt(row.ciphertext.encode()).decode(), row.version
    except (InvalidToken, UnicodeError):
        raise HTTPException(503, "secure_storage_unavailable") from None


async def metadata_check(key: str) -> str:
    # Fixed whitelist URL, no inference, redirects or provider body/error forwarding.
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as client:
            async with client.stream("GET", "https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"}) as response:
                return "auth_ok_models_not_verified" if response.status_code == 200 else "auth_failed" if response.status_code in {401, 403} else "provider_unavailable"
    except Exception:
        return "provider_unavailable"