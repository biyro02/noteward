"""
Noteward Server — FastAPI application entry point.
"""

import os
import yaml
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from app.api import router as api_router

CONFIG_PATH = Path(os.environ.get("NOTEWARD_CONFIG", "/app/data/config.yml"))
_config: dict = {}
_scheduler: BackgroundScheduler | None = None


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return yaml.safe_load(CONFIG_PATH.read_text()) or {}
    return {}


def get_config() -> dict:
    return _config


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _scheduler

    _config = load_config()

    # Start scheduler for daily summaries
    schedule_cfg = _config.get("schedule", {})
    daily_time = schedule_cfg.get("daily_summary", "11:00")
    tz_name = schedule_cfg.get("timezone", "UTC")
    hour, minute = map(int, daily_time.split(":"))
    tz = pytz.timezone(tz_name)

    _scheduler = BackgroundScheduler(timezone=tz)

    from app.notifier import run_daily
    _scheduler.add_job(
        run_daily,
        CronTrigger(hour=hour, minute=minute, timezone=tz),
        args=[_config],
        id="daily_summary",
        replace_existing=True,
    )
    _scheduler.start()
    print(f"Scheduler started. Daily summary at {daily_time} {tz_name}.")

    yield

    _scheduler.shutdown(wait=False)


app = FastAPI(title="Noteward", version="1.0.0", lifespan=lifespan)
app.include_router(api_router)


@app.get("/health")
def health():
    from app import crypto
    return {
        "status": "ok",
        "key_loaded": crypto.is_unlocked(),
        "initialized": crypto.is_initialized(),
    }
