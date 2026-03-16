"""
Noteward API routes.

POST /sync           — watcher pushes file content
POST /bot/slack      — Slack Events API webhook
POST /bot/discord    — Discord webhook
POST /setup          — first-time master password setup
GET  /health         — health check (in main.py)
"""

import hmac
import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel

from app import crypto
from app.bot import handle_command
from app.main import get_config

router = APIRouter()

NOTES_DIR = Path("/app/data/notes")


# ── Models ─────────────────────────────────────────────────────────────────────

class SyncFile(BaseModel):
    name: str
    content: str
    deleted: bool = False


class SyncPayload(BaseModel):
    files: list[SyncFile]
    signature: str   # HMAC-SHA256(secret, sorted filenames joined)


class SetupPayload(BaseModel):
    master_password: str
    recovery_key: str   # base64 raw data key, stored locally by watcher


# ── Helpers ───────────────────────────────────────────────────────────────────

def _verify_signature(payload_bytes: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _get_secret() -> str:
    return get_config().get("server", {}).get("secret", "")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/sync")
async def sync_files(request: Request):
    """Receive file updates from watcher.py."""
    body = await request.body()
    secret = _get_secret()

    if secret:
        sig = request.headers.get("X-Noteward-Signature", "")
        if not _verify_signature(body, sig, secret):
            raise HTTPException(status_code=401, detail="Invalid signature.")

    import json
    data = json.loads(body)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    for f in data.get("files", []):
        path = NOTES_DIR / f["name"]
        if f.get("deleted"):
            path.unlink(missing_ok=True)
        else:
            path.write_text(f["content"], encoding="utf-8")

    return {"ok": True, "files": len(data.get("files", []))}


@router.post("/setup")
async def setup(payload: SetupPayload):
    """First-time setup: initialize master password and store recovery info."""
    if crypto.is_initialized():
        raise HTTPException(status_code=409, detail="Already initialized. Use /reset to change password.")
    crypto.setup_master_password(payload.master_password)
    return {"ok": True, "message": "Master password set. Keep your recovery key safe."}


@router.post("/bot/slack")
async def slack_webhook(request: Request):
    """Slack Events API endpoint."""
    body = await request.body()
    import json
    data = json.loads(body)

    # Slack URL verification challenge
    if data.get("type") == "url_verification":
        return {"challenge": data["challenge"]}

    config = get_config()
    notifier_cfg = config.get("notification", {})

    # Verify Slack signing secret if configured
    signing_secret = notifier_cfg.get("signing_secret", "")
    if signing_secret:
        ts = request.headers.get("X-Slack-Request-Timestamp", "")
        slack_sig = request.headers.get("X-Slack-Signature", "")
        base = f"v0:{ts}:{body.decode()}"
        expected = "v0=" + hmac.new(signing_secret.encode(), base.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, slack_sig):
            raise HTTPException(status_code=401, detail="Invalid Slack signature.")

    from app.notifications.slack import SlackNotifier
    notifier = SlackNotifier(notifier_cfg)
    parsed = notifier.parse_command(data)
    if parsed:
        user_id, text = parsed
        if text.startswith("!"):
            response = handle_command(text, user_id, config)
            notifier.reply(user_id, response)

    return {"ok": True}


@router.post("/bot/discord")
async def discord_webhook(request: Request):
    """Discord webhook endpoint."""
    body = await request.body()
    import json
    data = json.loads(body)

    # Discord interaction verification (type 1 = PING)
    if data.get("type") == 1:
        return {"type": 1}

    config = get_config()
    notifier_cfg = config.get("notification", {})

    from app.notifications.discord import DiscordNotifier
    notifier = DiscordNotifier(notifier_cfg)
    parsed = notifier.parse_command(data)
    if parsed:
        user_id, text = parsed
        if text.startswith("!"):
            response = handle_command(text, user_id, config)
            notifier.reply(user_id, response)

    return {"ok": True}


@router.post("/notify/now")
async def notify_now():
    """Trigger daily summary immediately (for testing)."""
    from app.notifier import run_daily
    config = get_config()
    run_daily(config)
    return {"ok": True}
