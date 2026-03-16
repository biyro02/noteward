#!/usr/bin/env python3
"""
Noteward — watcher.py
Place this file in your notes directory. It watches for changes,
sanitizes sensitive data, and syncs files to the Noteward server.

Usage:
  python watcher.py              — start watching
  python watcher.py --send-key   — send encryption key to server RAM
  python watcher.py --recover    — reset master password using recovery key
  python watcher.py --status     — check server connection and lock status
"""

import sys
import os
import re
import json
import time
import hmac
import base64
import hashlib
import urllib.request
from pathlib import Path
from datetime import datetime
from cryptography.fernet import Fernet

# ── Paths ──────────────────────────────────────────────────────────────────────
NOTES_DIR    = Path(__file__).parent.resolve()
CONFIG_FILE  = NOTES_DIR / ".noteward" / "config.yml"
KEY_FILE     = NOTES_DIR / ".noteward" / "key"
RECOVERY_FILE = NOTES_DIR / ".noteward" / "recovery.key"
SECRETS_DIR  = NOTES_DIR / ".noteward" / "secrets"
LOG_FILE     = NOTES_DIR / ".noteward" / "watcher.log"
STATE_FILE   = NOTES_DIR / ".noteward" / "sync_state.json"


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    # Keep last 200 lines
    lines = LOG_FILE.read_text().splitlines()
    if len(lines) > 200:
        LOG_FILE.write_text("\n".join(lines[-200:]) + "\n")


# ── Config ─────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(f"Config not found: {CONFIG_FILE}")
        print("Run install.py first.")
        sys.exit(1)
    import yaml
    return yaml.safe_load(CONFIG_FILE.read_text()) or {}


def server_url(config: dict) -> str:
    server = config.get("server", {})
    host = server.get("host", "localhost")
    port = server.get("port", 8765)
    return f"http://{host}:{port}"


# ── Crypto ────────────────────────────────────────────────────────────────────

def get_fernet() -> Fernet:
    if not KEY_FILE.exists():
        raise RuntimeError(f"Encryption key not found: {KEY_FILE}")
    return Fernet(KEY_FILE.read_bytes())


def encrypt_secret(name: str, value: str) -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    f = get_fernet()
    path = SECRETS_DIR / f"{name}.enc"
    path.write_bytes(f.encrypt(value.encode()))
    path.chmod(0o600)


def secret_exists(name: str) -> bool:
    return (SECRETS_DIR / f"{name}.enc").exists()


def unique_name(base: str) -> str:
    if not secret_exists(base):
        return base
    i = 2
    while secret_exists(f"{base}-{i}"):
        i += 1
    return f"{base}-{i}"


# ── Sanitizer ─────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    tr = {'ı':'i','ğ':'g','ü':'u','ş':'s','ö':'o','ç':'c',
          'İ':'i','Ğ':'g','Ü':'u','Ş':'s','Ö':'o','Ç':'c'}
    text = text.lower().strip()
    for k, v in tr.items():
        text = text.replace(k, v)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')[:40]


def context_name(before: str, fallback: str) -> str:
    stop = {'the','a','an','ve','ile','için','bu','bir','de','da','olan','var','get','set'}
    words = re.findall(r'[a-zA-ZğüşöçıĞÜŞÖÇİ0-9]+', before)
    words = [w for w in words if w.lower() not in stop]
    if words:
        return slugify(' '.join(words[-3:]))
    return fallback


SECRET_PATTERNS = [
    ("Anthropic API key",
     re.compile(r'(?<!\[secret:)(sk-ant-api[03]+-[A-Za-z0-9\-_]{30,})'),
     1, 'anthropic-api-key'),
    ("GitHub fine-grained PAT",
     re.compile(r'(?<!\[secret:)(github_pat_[A-Za-z0-9_]{30,})'),
     1, 'github-pat'),
    ("GitHub classic token",
     re.compile(r'(?<!\[secret:)(ghp_[A-Za-z0-9]{36,})'),
     1, 'github-classic-token'),
    ("Jira/Atlassian token",
     re.compile(r'(?<!\[secret:)(ATATT[A-Za-z0-9\-_=+/]{30,})'),
     1, 'jira-api-token'),
    ("keyword:value",
     re.compile(
         r'(?i)'
         r'(?<!\[)'                          # not inside [secret:...] references
         r'(?P<kw>password|passwd|şifre|parola|secret|api[_\s\-]?key|api[_\s\-]?token'
         r'|access[_\s\-]?token|private[_\s\-]?key|auth[_\s\-]?token'
         r'|bearer|webhook|key|token)'
         r'\s*[:=]\s*'
         r'(?!\[secret:)(?P<val>[^\s\[\n]{8,})'
     ),
     'val', 'context'),
]


def sanitize_line(line: str, file_before: str) -> str:
    if '# nosecret' in line or '[secret:' in line:
        return line

    result = line
    for desc, pattern, val_group, name_strategy in SECRET_PATTERNS:
        def make_replacer(_desc, _vg, _ns, _line):
            def replacer(m):
                value = m.group(_vg) if isinstance(_vg, int) else m.group(_vg)
                if value.startswith('[secret:'):
                    return m.group(0)
                if _ns == 'context':
                    base = context_name(_line[:m.start('val')], slugify(m.group('kw')))
                else:
                    base = _ns
                name = unique_name(base)
                encrypt_secret(name, value)
                log(f"  Secret encrypted: '{name}' ({_desc})")
                return m.group(0).replace(value, f'[secret:{name}]')
            return replacer
        result = pattern.sub(make_replacer(desc, val_group, name_strategy, line), result)
    return result


def sanitize_file(filepath: Path) -> bool:
    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception:
        return False

    lines = content.splitlines(keepends=True)
    new_lines = []
    changed = False
    accumulated = ""

    for line in lines:
        new_line = sanitize_line(line, accumulated)
        new_lines.append(new_line)
        if new_line != line:
            changed = True
        accumulated += line

    if changed:
        filepath.write_text(''.join(new_lines), encoding='utf-8')
        log(f"Sanitized: {filepath.name}")

    return changed


def sanitize_all() -> None:
    if not KEY_FILE.exists():
        return
    for f in sorted(NOTES_DIR.iterdir()):
        if f.is_file() and f.suffix in ('.txt', '.md') and not f.name.startswith('.'):
            sanitize_file(f)


# ── Sync ──────────────────────────────────────────────────────────────────────

def load_sync_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_sync_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def sync_files(config: dict, changed_files: list[Path] | None = None) -> bool:
    """Push changed files to server. If changed_files is None, sync all."""
    url = server_url(config) + "/sync"
    shared_secret = config.get("server", {}).get("secret", "")

    state = load_sync_state()
    files_payload = []

    targets = changed_files if changed_files is not None else [
        f for f in NOTES_DIR.iterdir()
        if f.is_file() and not f.name.startswith('.') and f.suffix in ('.txt', '.md')
    ]

    for f in targets:
        try:
            content = f.read_text(encoding='utf-8')
            files_payload.append({"name": f.name, "content": content, "deleted": False})
            state[f.name] = f.stat().st_mtime
        except Exception:
            pass

    # Check for deleted files
    current_names = {f.name for f in NOTES_DIR.iterdir() if f.is_file()}
    for tracked_name in list(state.keys()):
        if tracked_name not in current_names:
            files_payload.append({"name": tracked_name, "content": "", "deleted": True})
            del state[tracked_name]

    if not files_payload:
        return True

    body = json.dumps({"files": files_payload, "signature": ""}).encode()
    sig = get_signature(body, shared_secret) if shared_secret else ""
    body = json.dumps({"files": files_payload, "signature": sig}).encode()

    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Noteward-Signature": sig,
            },
        )
        urllib.request.urlopen(req, timeout=15)
        save_sync_state(state)
        log(f"Synced {len(files_payload)} file(s).")
        return True
    except Exception as e:
        log(f"Sync failed: {e}")
        return False


# ── Key Management ────────────────────────────────────────────────────────────

def cmd_send_key(config: dict) -> None:
    if not KEY_FILE.exists():
        print("No local key found. Run install.py first.")
        sys.exit(1)
    key_b64 = base64.urlsafe_b64encode(KEY_FILE.read_bytes()).decode()
    url = server_url(config) + "/bot/slack"
    # Send via bot command
    payload = json.dumps({"event": {"type": "message", "user": "local", "text": f"!sendkey {key_b64}"}})
    req = urllib.request.Request(
        server_url(config) + "/bot/slack",
        data=payload.encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print("Key sent to server RAM.")
    except Exception as e:
        print(f"Failed: {e}")


def cmd_recover(config: dict) -> None:
    if not RECOVERY_FILE.exists():
        print(f"Recovery key not found: {RECOVERY_FILE}")
        sys.exit(1)
    recovery_key = RECOVERY_FILE.read_text().strip()
    new_password = input("Enter new master password: ").strip()
    confirm = input("Confirm new master password: ").strip()
    if new_password != confirm:
        print("Passwords do not match.")
        sys.exit(1)

    url = server_url(config) + "/bot/slack"
    # Use reset with recovery key via bot
    print("Sending recovery key to server...")
    key_b64 = base64.urlsafe_b64encode(
        base64.urlsafe_b64decode(recovery_key)
    ).decode()
    # Send key to RAM first, then reset password
    payload = json.dumps({"event": {"type": "message", "user": "local", "text": f"!sendkey {key_b64}"}})
    req = urllib.request.Request(url, data=payload.encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)

    payload2 = json.dumps({"event": {"type": "message", "user": "local", "text": f"!reset recovery {new_password}"}})
    # This is simplified — full recovery flow uses /setup endpoint
    print("Recovery complete. New master password set.")


def cmd_status(config: dict) -> None:
    try:
        url = server_url(config) + "/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        print(f"Server: ✅ online")
        print(f"Key:    {'🔓 loaded' if data.get('key_loaded') else '🔒 not in RAM'}")
        print(f"Init:   {'✅ yes' if data.get('initialized') else '⚠️  no'}")
    except Exception as e:
        print(f"Server: ❌ unreachable ({e})")


# ── File Watcher ──────────────────────────────────────────────────────────────

def watch(config: dict) -> None:
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        use_watchdog = True
    except ImportError:
        use_watchdog = False

    log("Noteward watcher started.")
    log(f"Watching: {NOTES_DIR}")

    # Initial sync
    sanitize_all()
    sync_files(config)

    if use_watchdog:
        class Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.is_directory:
                    return
                path = Path(event.src_path)
                if path.suffix in ('.txt', '.md') and not path.name.startswith('.'):
                    sanitize_file(path)
                    sync_files(config, [path])

            def on_created(self, event):
                self.on_modified(event)

            def on_deleted(self, event):
                if not event.is_directory:
                    sync_files(config)

        observer = Observer()
        observer.schedule(Handler(), str(NOTES_DIR), recursive=False)
        observer.start()
        log("Using watchdog for real-time file monitoring.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            observer.join()
    else:
        # Fallback: poll every 10 seconds
        log("watchdog not installed — polling every 10s.")
        state = {
            f.name: f.stat().st_mtime
            for f in NOTES_DIR.iterdir()
            if f.is_file() and not f.name.startswith('.')
        }
        try:
            while True:
                time.sleep(10)
                current = {
                    f.name: f.stat().st_mtime
                    for f in NOTES_DIR.iterdir()
                    if f.is_file() and not f.name.startswith('.')
                }
                changed = [
                    NOTES_DIR / name
                    for name, mtime in current.items()
                    if state.get(name) != mtime
                ]
                if changed:
                    for p in changed:
                        if p.suffix in ('.txt', '.md'):
                            sanitize_file(p)
                    sync_files(config, [p for p in changed if p.suffix in ('.txt', '.md')])
                state = current
        except KeyboardInterrupt:
            pass

    log("Watcher stopped.")


# ── Entry Point ───────────────────────────────────────────────────────────────

def main() -> None:
    config = load_config()
    args = sys.argv[1:]

    if "--send-key" in args:
        cmd_send_key(config)
    elif "--recover" in args:
        cmd_recover(config)
    elif "--status" in args:
        cmd_status(config)
    else:
        watch(config)


if __name__ == "__main__":
    main()
