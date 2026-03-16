#!/usr/bin/env python3
"""
Noteward — install.py
Cross-platform installer. Run once to set up everything.
Requires Python 3.8+.
"""

import os
import sys
import json
import shutil
import base64
import subprocess
import platform
from pathlib import Path

MIN_PYTHON = (3, 8)
REQUIRED_PACKAGES = ["cryptography", "pyyaml", "watchdog"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def c(text, color):
    colors = {"green": "\033[92m", "yellow": "\033[93m", "red": "\033[91m",
              "bold": "\033[1m", "reset": "\033[0m"}
    if sys.stdout.isatty():
        return f"{colors.get(color, '')}{text}{colors['reset']}"
    return text


def ok(msg):   print(c(f"  ✓ {msg}", "green"))
def warn(msg): print(c(f"  ⚠ {msg}", "yellow"))
def err(msg):  print(c(f"  ✗ {msg}", "red")); sys.exit(1)
def header(msg): print(f"\n{c(msg, 'bold')}")


def ask(prompt, default="", password=False) -> str:
    display = f"{prompt} [{default}]: " if default else f"{prompt}: "
    if password:
        import getpass
        val = getpass.getpass(display).strip()
    else:
        val = input(display).strip()
    return val or default


def ask_choice(prompt, options: list[tuple[str, str]]) -> str:
    print(f"\n{prompt}")
    for i, (key, label) in enumerate(options, 1):
        print(f"  [{i}] {label}")
    while True:
        choice = input("  Choice: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1][0]
        print("  Invalid choice, try again.")


def run(cmd: list, check=True, capture=False):
    return subprocess.run(cmd, check=check,
                          capture_output=capture, text=True)


# ── Checks ─────────────────────────────────────────────────────────────────────

def check_python():
    if sys.version_info < MIN_PYTHON:
        err(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required. "
            f"Current: {sys.version_info.major}.{sys.version_info.minor}")
    ok(f"Python {sys.version_info.major}.{sys.version_info.minor}")


def install_packages():
    header("Installing Python dependencies...")
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg.replace("-", "_"))
            ok(f"{pkg} already installed")
        except ImportError:
            print(f"  Installing {pkg}...")
            run([sys.executable, "-m", "pip", "install", pkg, "--quiet"])
            ok(f"{pkg} installed")


def check_docker() -> bool:
    if shutil.which("docker"):
        try:
            run(["docker", "compose", "version"], capture=True)
            ok("Docker + Compose found")
            return True
        except Exception:
            pass

    system = platform.system()
    warn("Docker not found — needed for server deployment.")

    if system == "Linux":
        answer = ask("  Install Docker automatically? (y/n)", "y")
        if answer.lower() != "y":
            err("Docker is required. Install it manually and re-run install.py.")
        print("  Installing Docker...")
        run(["sh", "-c", "curl -fsSL https://get.docker.com | sh"])
        # Add current user to docker group
        user = os.environ.get("USER", "")
        if user:
            run(["sudo", "usermod", "-aG", "docker", user], check=False)
        # Try to activate group without logout via newgrp (best-effort)
        run(["sudo", "systemctl", "enable", "--now", "docker"], check=False)
        ok("Docker installed.")
        warn("If you get a 'permission denied' error, log out and back in, then re-run install.py.")
        # Re-check with sudo for the rest of this session
        try:
            run(["sudo", "docker", "compose", "version"], capture=True)
            return True
        except Exception:
            return False

    elif system == "Darwin":
        if shutil.which("brew"):
            answer = ask("  Install Docker via Homebrew? (y/n)", "y")
            if answer.lower() == "y":
                print("  Installing Docker...")
                run(["brew", "install", "--cask", "docker"])
                run(["open", "-a", "Docker"], check=False)
                ok("Docker installed. Wait for Docker Desktop to start, then re-run install.py.")
                sys.exit(0)
        print(c("  → Download Docker Desktop: https://www.docker.com/products/docker-desktop/", "yellow"))
        err("Install Docker Desktop and re-run install.py.")

    else:  # Windows
        print(c("  → Download Docker Desktop: https://www.docker.com/products/docker-desktop/", "yellow"))
        print("  Install Docker Desktop, start it, then re-run install.py.")
        err("Docker Desktop required on Windows.")

    return False


# ── Setup Steps ───────────────────────────────────────────────────────────────

def setup_notes_dir() -> Path:
    header("Notes directory")
    default = str(Path.home() / "Documents")
    notes_dir = ask("Which folder should Noteward watch?", default)
    path = Path(notes_dir).expanduser().resolve()
    if not path.exists():
        create = ask(f"  Folder doesn't exist. Create it? (y/n)", "y")
        if create.lower() == "y":
            path.mkdir(parents=True)
            ok(f"Created: {path}")
        else:
            err("Notes directory required.")
    ok(f"Notes dir: {path}")
    return path


def setup_server(notes_dir: Path) -> dict:
    header("Deployment mode")
    mode = ask_choice("Where should the server run?", [
        ("remote", "Remote server (VPS / Hetzner)"),
        ("local",  "Local (Docker on this machine)"),
    ])

    server_cfg = {"mode": mode, "port": 8765}

    if mode == "remote":
        server_cfg["host"] = ask("Server IP or hostname")
        default_key = str(Path.home() / ".ssh" / "id_rsa")
        server_cfg["ssh_key"] = ask("SSH private key path", default_key)

        # Generate shared secret
        import secrets
        shared = secrets.token_hex(32)
        server_cfg["secret"] = shared
        ok(f"Shared secret generated.")
    else:
        server_cfg["host"] = "localhost"
        import secrets
        server_cfg["secret"] = secrets.token_hex(32)

    return server_cfg


def setup_notification() -> dict:
    header("Notification channel")
    ntype = ask_choice("Where should notifications be sent?", [
        ("slack",   "Slack"),
        ("discord", "Discord"),
    ])

    cfg = {"type": ntype}

    if ntype == "slack":
        print(c("  Webhook URL → slack.com/apps → Incoming WebHooks → Add to Slack → select channel", "yellow"))
        cfg["webhook_url"] = ask("  Slack webhook URL")
        cfg["channel"] = ask("  Channel name", "self-notifications")
        print()
        print("  Bot token enables two-way commands (!get, !list etc.)")
        print(c("  Bot token → api.slack.com/apps → Create App → OAuth & Permissions → Bot Token (xoxb-...)", "yellow"))
        bot = ask("  Slack bot token (optional, press Enter to skip)", "")
        if bot:
            cfg["bot_token"] = bot
            print(c("  Signing secret → api.slack.com/apps → Basic Information → Signing Secret", "yellow"))
            signing = ask("  Slack signing secret (optional)", "")
            if signing:
                cfg["signing_secret"] = signing
    else:
        print(c("  Webhook URL → Discord server → Edit Channel → Integrations → Webhooks → New Webhook", "yellow"))
        cfg["webhook_url"] = ask("  Discord webhook URL")
        cfg["channel"] = ask("  Channel ID or name", "")

    return cfg


def setup_ai() -> dict:
    header("AI provider")
    provider = ask_choice("Which AI provider?", [
        ("claude",  "Claude (Anthropic)"),
        ("openai",  "ChatGPT (OpenAI)"),
        ("ollama",  "Ollama (local model)"),
    ])

    cfg = {"provider": provider}

    if provider == "claude":
        print(c("  → console.anthropic.com → API Keys → Create Key", "yellow"))
        cfg["api_key"] = ask("  Claude API key")
    elif provider == "openai":
        print(c("  → platform.openai.com → API keys → Create new secret key", "yellow"))
        cfg["api_key"] = ask("  OpenAI API key")
    elif provider == "ollama":
        print()
        print("  Ollama runs locally inside Docker — no GPU required.")
        print("  Recommended CPU-friendly models:")
        print("    [1] llama3.2:1b     (~800 MB, fastest)")
        print("    [2] llama3.2:3b     (~2 GB, better quality)")
        print("    [3] deepseek-r1:1.5b (~1 GB, good reasoning)")
        print("    [4] qwen2.5:1.5b    (~1 GB, multilingual)")
        print("    [5] Custom")
        model_map = {
            "1": "llama3.2:1b",
            "2": "llama3.2:3b",
            "3": "deepseek-r1:1.5b",
            "4": "qwen2.5:1.5b",
        }
        choice = input("  Choice [1]: ").strip() or "1"
        if choice in model_map:
            cfg["model"] = model_map[choice]
        else:
            cfg["model"] = ask("  Model name (e.g. llama3.2:1b)", "llama3.2:1b")

        cfg["ollama_host"] = "http://ollama:11434"  # Docker service name
        cfg["ollama_model"] = cfg["model"]          # passed as OLLAMA_MODEL env
        warn(f"Model '{cfg['model']}' will be downloaded on first server start.")

    return cfg


def setup_schedule() -> dict:
    header("Schedule")
    time_str = ask("  Daily summary time (24h)", "11:00")
    tz = ask("  Timezone", "Europe/Istanbul")
    return {
        "daily_summary": time_str,
        "timezone": tz,
        "weekdays_only": True,
        "open_ended_interval_days": 3,
    }


def setup_encryption(notes_dir: Path) -> tuple[str, str]:
    """Generate data key, ask for master password, write recovery file."""
    header("Security setup")

    print("  Creating encryption key...")
    from cryptography.fernet import Fernet
    data_key = Fernet.generate_key()
    recovery_b64 = base64.urlsafe_b64encode(data_key).decode()

    noteward_dir = notes_dir / ".noteward"
    noteward_dir.mkdir(exist_ok=True)

    key_file = noteward_dir / "key"
    key_file.write_bytes(data_key)
    key_file.chmod(0o600)
    ok("Encryption key created.")

    recovery_file = noteward_dir / "recovery.key"
    recovery_file.write_text(recovery_b64)
    recovery_file.chmod(0o600)
    ok(f"Recovery key saved: {recovery_file}")
    warn("Keep this file safe. You'll need it if you forget your master password.")

    print()
    while True:
        pw = ask("  Set master password", password=True)
        pw2 = ask("  Confirm master password", password=True)
        if pw == pw2 and len(pw) >= 6:
            break
        if pw != pw2:
            warn("Passwords don't match, try again.")
        else:
            warn("Password must be at least 6 characters.")

    ok("Master password set.")
    return pw, recovery_b64


def write_config(notes_dir: Path, config: dict) -> Path:
    import yaml
    noteward_dir = notes_dir / ".noteward"
    noteward_dir.mkdir(exist_ok=True)
    config_file = noteward_dir / "config.yml"
    config_file.write_text(yaml.dump(config, allow_unicode=True, default_flow_style=False))
    config_file.chmod(0o600)
    ok(f"Config written: {config_file}")
    return config_file


def copy_watcher(notes_dir: Path) -> None:
    src = Path(__file__).parent / "watcher.py"
    dst = notes_dir / "watcher.py"
    shutil.copy2(src, dst)
    ok(f"watcher.py copied to: {dst}")


def deploy_server(notes_dir: Path, server_cfg: dict, master_password: str, recovery_b64: str, config: dict = {}) -> None:
    mode = server_cfg.get("mode")
    compose_dir = Path(__file__).parent / "server"

    ai_cfg = config.get("ai", {})
    use_ollama = ai_cfg.get("provider") == "ollama"
    ollama_model = ai_cfg.get("ollama_model", "llama3.2:1b")
    profile_flag = ["--profile", "ollama"] if use_ollama else []
    env_flag = ["-e", f"OLLAMA_MODEL={ollama_model}"] if use_ollama else []

    if mode == "local":
        header("Starting local server (Docker)...")
        run(["docker", "compose", "-f", str(compose_dir / "docker-compose.local.yml")]
            + profile_flag + ["up", "-d", "--build"] + env_flag)
        if use_ollama:
            ok(f"Ollama started. Pulling model '{ollama_model}' in background...")
            warn("First run may take a few minutes while the model downloads.")
        ok("Local server started.")

    elif mode == "remote":
        header("Deploying to remote server...")
        host = server_cfg["host"]
        ssh_key = server_cfg.get("ssh_key", "")
        ssh_opts = ["-i", ssh_key, "-o", "StrictHostKeyChecking=no"] if ssh_key else []

        print("  Copying server files...")
        run(["rsync", "-az"] + (["-e", f"ssh -i {ssh_key}"] if ssh_key else []) +
            [str(compose_dir) + "/", f"root@{host}:/opt/noteward/"])
        ok("Files copied.")

        print("  Starting server on remote...")
        compose_cmd = f"cd /opt/noteward && OLLAMA_MODEL={ollama_model} docker compose " + \
                      (" ".join(profile_flag)) + " up -d --build"
        run(["ssh"] + ssh_opts + [f"root@{host}", compose_cmd])
        if use_ollama:
            warn(f"Model '{ollama_model}' is being pulled on remote. Check with: ssh root@{host} 'docker logs noteward-ollama-pull-1'")
        ok("Remote server started.")

    # Initialize master password on server
    import time, urllib.request
    host = server_cfg.get("host", "localhost")
    port = server_cfg.get("port", 8765)
    url = f"http://{host}:{port}/setup"

    print("  Waiting for server to start...")
    for _ in range(15):
        try:
            urllib.request.urlopen(f"http://{host}:{port}/health", timeout=2)
            break
        except Exception:
            time.sleep(2)

    payload = json.dumps({"master_password": master_password, "recovery_key": recovery_b64}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        ok("Master password initialized on server.")
    except Exception as e:
        warn(f"Could not initialize server password: {e}")
        warn("Run 'python watcher.py --send-key' after the server is up.")


def print_next_steps(notes_dir: Path, server_cfg: dict) -> None:
    header("Setup complete! 🎉")
    print()
    print(c("  Next steps:", "bold"))
    print(f"  1. Start watching:  cd \"{notes_dir}\" && python watcher.py")
    print(f"  2. Check status:    python watcher.py --status")
    print(f"  3. If key is lost:  python watcher.py --send-key")
    print(f"  4. Forgot password: python watcher.py --recover")
    print()
    print(c("  In your Slack/Discord channel:", "bold"))
    print("  !help      — list all bot commands")
    print("  !status    — check lock state")
    print("  !list      — list stored secrets")
    print("  !get <name>  — retrieve a secret")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(c("\n  Noteward Installer", "bold"))
    print("  ─────────────────────────────────")

    check_python()
    install_packages()

    notes_dir = setup_notes_dir()
    server_cfg = setup_server(notes_dir)
    notification_cfg = setup_notification()
    ai_cfg = setup_ai()
    schedule_cfg = setup_schedule()
    master_password, recovery_b64 = setup_encryption(notes_dir)

    config = {
        "notes_dir": str(notes_dir),
        "server": server_cfg,
        "notification": notification_cfg,
        "ai": ai_cfg,
        "schedule": schedule_cfg,
        "security": {
            "max_failed_attempts": 3,
            "alert_on_secret_access": True,
        },
        "sources": [{"type": "files"}],
    }

    write_config(notes_dir, config)
    copy_watcher(notes_dir)

    if check_docker():
        deploy_server(notes_dir, server_cfg, master_password, recovery_b64, config)
    else:
        warn("Docker not found. Install Docker and run 'python install.py --deploy-only'.")

    print_next_steps(notes_dir, server_cfg)


if __name__ == "__main__":
    main()
