# Noteward

> Smart daily notes reminder with automatic sensitive data protection.

Noteward watches your notes folder, encrypts sensitive data automatically, syncs to a server, and sends you a daily AI-powered summary via Slack or Discord — without ever exposing your secrets.

## How It Works

```
Your notes folder
  └── watcher.py        ← watches for changes
        │ detects secrets → encrypts locally
        │ syncs files (without secrets) → server
        └── Server
              ├── Daily summary → Slack / Discord
              └── Bot commands  → !get <secret-name>
```

**Security model:**
- Secrets are encrypted locally with a `data_key`
- `data_key` is wrapped with your master password (never stored plain)
- Only ciphertext ever leaves your machine
- Server holds key in RAM only (`/dev/shm`) — lost on reboot
- Recovery key stored locally as your offline backup

## Quick Start

**Requirements:** Python 3.8+

```bash
curl -fsSL https://raw.githubusercontent.com/Uruba-Software/noteward/main/install.py -o /tmp/nw-install.py && python3 /tmp/nw-install.py
```

That's it. The installer handles everything else (including Docker if missing).

The installer will ask you:
1. Which folder to watch
2. Local or remote server
3. Slack or Discord
4. Claude, ChatGPT, or Ollama
5. Daily summary time
6. Master password

That's it. Then start watching:

```bash
cd ~/your-notes-folder
python watcher.py
```

## Bot Commands

In your Slack/Discord channel:

| Command | Description |
|---------|-------------|
| `!help` | List all commands |
| `!status` | Show lock state |
| `!unlock <password>` | Load key into RAM |
| `!lock` | Remove key from RAM |
| `!list` | List stored secret names |
| `!get <name>` | Retrieve a secret value |
| `!reset <old> <new>` | Change master password |
| `!sendkey <base64>` | Inject key from local machine |

## Automatic Secret Detection

Write anything in your notes — sensitive values are detected and encrypted automatically:

```
# Before saving:
github token: ghp_abc123...
api key: sk-ant-api03-...
my server password: s3cr3t!

# After watcher processes it:
github token: [secret:github-token]
api key: [secret:anthropic-api-key]
my server password: [secret:my-server-password]
```

To bypass detection on a line, add `# nosecret`:
```
example token: not-a-real-secret # nosecret
```

## Recovery

If you forget your master password:

```bash
cd ~/your-notes-folder
python watcher.py --recover
```

This uses the recovery key at `.noteward/recovery.key`. Keep this file backed up somewhere safe (password manager recommended).

## Configuration

Config lives at `{notes_dir}/.noteward/config.yml`. See `config.example.yml` for all options.

## Supported Providers

**AI:** Claude (Anthropic) · ChatGPT (OpenAI) · Ollama (local)

**Notifications:** Slack · Discord

**Sources (current):** Notes files

**Sources (roadmap):** GitHub · Jira · Email

## License

MIT
