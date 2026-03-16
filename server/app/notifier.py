"""
Daily summary notifier.
Collects content from all configured sources, sends to AI, posts to notification channel.
"""

import json
from datetime import date
from pathlib import Path

from app.sources import FilesSource
from app.providers import get_provider
from app.notifications import get_notifier

DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
STATE_FILE = Path("/app/data/state.json")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"last_open_ended_sent": None}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _build_prompt(content: str, today_str: str, include_open_ended: bool) -> str:
    open_ended_rule = (
        "4. List any open-ended or undated tasks (things to do with no specific date)."
        if include_open_ended
        else "4. Do NOT include open-ended or undated tasks — only items relevant to today or this week."
    )
    return f"""Analyze the following notes. Today is {today_str}.

Notes:
---
{content}
---

Evaluate:
1. Is there anything to do today or specific to today?
2. Are there any upcoming deadlines or important dates in the next 2-3 days?
3. Is there anything urgent that needs attention?
{open_ended_rule}

RULES:
- Always respond in English regardless of the notes language.
- Ignore any item marked as done, completed, resolved, finished, halloldu, tamamlandı, bitti, closed.
- If NONE of the above apply, respond with exactly: NO_NOTES_FOR_TODAY
- Otherwise format as a Slack/Discord message using markdown: **bold**, _italic_, • bullets.
- One line per item stating when/why it matters. No intro sentence."""


def run_daily(config: dict) -> None:
    today = date.today()

    schedule = config.get("schedule", {})
    if schedule.get("weekdays_only", True) and today.weekday() >= 5:
        print("Weekend — skipping.")
        return

    interval = schedule.get("open_ended_interval_days", 3)
    state = load_state()
    last_sent = state.get("last_open_ended_sent")
    if last_sent:
        from datetime import date as _date
        days_since = (today - _date.fromisoformat(last_sent)).days
        include_open_ended = days_since >= interval
    else:
        include_open_ended = True

    # Collect from all sources
    source_contents = []
    for source_cfg in config.get("sources", [{"type": "files"}]):
        if source_cfg["type"] == "files":
            content = FilesSource().fetch()
            if content:
                source_contents.append(content)
        # Future: github, jira, email sources go here

    if not source_contents:
        print("All sources empty — skipping.")
        return

    combined = "\n\n".join(source_contents)
    day_name = DAYS_EN[today.weekday()]
    today_str = f"{today.strftime('%B %d, %Y')} ({day_name})"
    prompt = _build_prompt(combined, today_str, include_open_ended)

    provider = get_provider(config.get("ai", {}))
    response = provider.complete(prompt, max_tokens=800)

    notifier = get_notifier(config.get("notification", {}))

    if "NO_NOTES_FOR_TODAY" in response.text:
        msg = f"📋 *Daily Summary — {today_str}*\n_No reminders for today._"
    else:
        msg = f"📋 *Daily Summary — {today_str}*\n\n{response.text}"
        if include_open_ended:
            state["last_open_ended_sent"] = today.isoformat()
            save_state(state)

    notifier.send(msg)
    print(f"Daily summary sent. ({response.model})")
