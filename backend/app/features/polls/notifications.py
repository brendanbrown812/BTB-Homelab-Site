import logging
from datetime import timezone
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.features.polls.models import Poll, PollOption, PollSelectionMode

logger = logging.getLogger(__name__)


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[:limit - 1]}…"


def _is_discord_webhook_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname in {"discord.com", "www.discord.com"} and parsed.path.startswith("/api/webhooks/")


async def send_poll_created_notification(poll: Poll, options: list[PollOption]) -> str:
    settings = get_settings()
    webhook_url = settings.discord_poll_webhook_url.strip()
    if not webhook_url:
        return "not_configured"
    if not _is_discord_webhook_url(webhook_url):
        logger.error("Discord poll webhook URL is not a valid Discord webhook URL")
        return "failed"

    role_id = settings.discord_poll_role_id.strip()
    if role_id and not role_id.isdigit():
        logger.error("DISCORD_POLL_ROLE_ID must contain only the numeric Discord role ID")
        return "failed"

    poll_url = f"{settings.public_site_url.rstrip('/')}/polls"
    option_lines = "\n".join(f"{index}. {option.text}" for index, option in enumerate(options, start=1))
    closes_at = poll.closes_at if poll.closes_at is None or poll.closes_at.tzinfo else poll.closes_at.replace(tzinfo=timezone.utc)
    closes = f"<t:{int(closes_at.astimezone(timezone.utc).timestamp())}:F>" if closes_at else "No closing date"
    payload = {
        "username": "BTB Polls",
        "content": f"<@&{role_id}> A new league poll is open." if role_id else "A new league poll is open.",
        "allowed_mentions": {"parse": [], "roles": [role_id] if role_id else []},
        "embeds": [{
            "title": poll.question,
            "url": poll_url,
            "description": _truncate(poll.description, 2000) if poll.description else None,
            "color": 0xF5C451,
            "fields": [
                {"name": "Options", "value": _truncate(option_lines, 1024), "inline": False},
                {"name": "Response type", "value": "Select one" if poll.selection_mode is PollSelectionMode.single else "Select all that apply", "inline": True},
                {"name": "Closes", "value": closes, "inline": True},
            ],
            "footer": {"text": "Open BTB to cast your vote"},
        }],
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, params={"wait": "true"}, json=payload)
            response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Could not send Discord notification for poll %s", poll.id)
        return "failed"
    return "sent"
