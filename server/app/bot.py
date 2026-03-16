"""
Bot command handler.
Processes incoming commands from Slack/Discord.
"""

import re
from pathlib import Path
from app import crypto
from app.notifications import get_notifier

# Failed unlock attempts tracking (in-memory, resets on restart)
_failed_attempts: dict[str, int] = {}
_locked = False

ACCESS_LOG = Path("/app/data/access.log")


def _log_access(action: str, user_id: str, detail: str = "") -> None:
    ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    line = f"[{datetime.utcnow().isoformat()}] {action} user={user_id} {detail}\n"
    with open(ACCESS_LOG, "a") as f:
        f.write(line)


def _alert(config: dict, message: str) -> None:
    try:
        get_notifier(config.get("notification", {})).send(f"🚨 *Security Alert*\n{message}")
    except Exception:
        pass


def handle_command(text: str, user_id: str, config: dict) -> str:
    """
    Process a bot command and return the response string.

    Commands:
      !help                     — list commands
      !get <secret-name>        — retrieve a secret (requires unlock)
      !list                     — list secret names
      !unlock <master-password> — unlock key from wrapped key on disk
      !lock                     — remove key from RAM
      !status                   — show lock status
      !sendkey <base64-key>     — inject key directly into RAM (from watcher --send-key)
      !reset <old> <new>        — change master password
    """
    global _locked

    text = text.strip()
    max_attempts = config.get("security", {}).get("max_failed_attempts", 3)
    alert_on_access = config.get("security", {}).get("alert_on_secret_access", True)

    if _locked:
        return "🔒 Bot is locked due to too many failed attempts. Restart the server to unlock."

    # ── !help ──────────────────────────────────────────────────────────────────
    if text == "!help":
        return (
            "*Noteward Commands*\n"
            "• `!status` — show whether key is loaded\n"
            "• `!unlock <password>` — unlock with master password\n"
            "• `!lock` — remove key from RAM\n"
            "• `!list` — list stored secret names\n"
            "• `!get <name>` — retrieve a secret value\n"
            "• `!reset <old-password> <new-password>` — change master password\n"
            "• `!sendkey <base64>` — inject key from local machine"
        )

    # ── !status ────────────────────────────────────────────────────────────────
    if text == "!status":
        status = "🔓 Unlocked" if crypto.is_unlocked() else "🔒 Locked"
        initialized = "✅ Initialized" if crypto.is_initialized() else "⚠️ Not initialized"
        return f"{status} | {initialized}"

    # ── !lock ──────────────────────────────────────────────────────────────────
    if text == "!lock":
        from pathlib import Path
        key_path = Path("/dev/shm/noteward_key")
        if key_path.exists():
            key_path.unlink()
        _log_access("LOCK", user_id)
        return "🔒 Key removed from RAM."

    # ── !unlock <password> ─────────────────────────────────────────────────────
    if text.startswith("!unlock "):
        password = text[8:].strip()
        if crypto.unlock(password):
            _failed_attempts[user_id] = 0
            _log_access("UNLOCK_OK", user_id)
            return "🔓 Unlocked successfully."
        else:
            _failed_attempts[user_id] = _failed_attempts.get(user_id, 0) + 1
            _log_access("UNLOCK_FAIL", user_id)
            if _failed_attempts[user_id] >= max_attempts:
                _locked = True
                _alert(config, f"Too many failed unlock attempts from user `{user_id}`. Bot locked.")
                return "🚫 Too many failed attempts. Bot locked."
            remaining = max_attempts - _failed_attempts[user_id]
            return f"❌ Wrong password. {remaining} attempt(s) remaining."

    # ── !sendkey <base64> ──────────────────────────────────────────────────────
    if text.startswith("!sendkey "):
        key_b64 = text[9:].strip()
        try:
            crypto.send_key(key_b64)
            _log_access("SENDKEY", user_id)
            return "✅ Key loaded into RAM."
        except Exception as e:
            return f"❌ Failed to load key: {e}"

    # ── !list ──────────────────────────────────────────────────────────────────
    if text == "!list":
        if not crypto.is_unlocked():
            return "🔒 Locked. Use `!unlock <password>` first."
        names = crypto.list_secrets()
        if not names:
            return "_No secrets stored._"
        return "📋 *Stored secrets:*\n" + "\n".join(f"• `{n}`" for n in names)

    # ── !get <name> ────────────────────────────────────────────────────────────
    m = re.fullmatch(r"!get\s+([\w\-]+)", text)
    if m:
        if not crypto.is_unlocked():
            return "🔒 Locked. Use `!unlock <password>` first."
        name = m.group(1)
        try:
            value = crypto.get_secret(name)
            if alert_on_access:
                _alert(config, f"Secret `{name}` was accessed by user `{user_id}`.")
            _log_access("GET_SECRET", user_id, f"name={name}")
            return f"`{name}`: `{value}`"
        except KeyError:
            return f"❌ Secret `{name}` not found. Use `!list` to see available secrets."

    # ── !reset <old> <new> ─────────────────────────────────────────────────────
    m = re.fullmatch(r"!reset\s+(\S+)\s+(\S+)", text)
    if m:
        old_pw, new_pw = m.group(1), m.group(2)
        if crypto.reset_password(old_pw, new_pw):
            _log_access("RESET_PASSWORD", user_id)
            return "✅ Master password changed."
        return "❌ Current password is wrong."

    return "_Unknown command. Type `!help` for available commands._"
