import logging
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.features.ptgotw.models import PTGWriteup

logger = logging.getLogger(__name__)


def _is_discord_webhook_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"discord.com", "www.discord.com"}
        and parsed.path.startswith("/api/webhooks/")
    )


async def send_writeup_published_notification(writeup: PTGWriteup, display_name: str) -> str:
    settings = get_settings()
    webhook_url = settings.discord_ptgotw_webhook_url.strip()
    if not webhook_url:
        return "not_configured"
    if not _is_discord_webhook_url(webhook_url):
        logger.error("DISCORD_PTGOTW_WEBHOOK_URL is not a valid Discord webhook URL")
        return "failed"

    writeup_url = f"{settings.public_site_url.rstrip('/')}/ptgotw/{writeup.id}"
    payload = {
        "username": "BTB PTGOTW",
        "content": (
            f"{display_name} has published their week {writeup.week} writeup. "
            f"Read it here: {writeup_url}"
        ),
        "allowed_mentions": {"parse": []},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, params={"wait": "true"}, json=payload)
            response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Could not send Discord notification for PTGOTW writeup %s", writeup.id)
        return "failed"
    return "sent"
