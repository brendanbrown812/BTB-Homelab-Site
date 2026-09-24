from urllib.parse import urlparse

import httpx

from app.core.config import get_settings


def _is_discord_webhook_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"discord.com", "www.discord.com"}
        and parsed.path.startswith("/api/webhooks/")
    )


async def send_prediction_deadline_notification() -> str:
    settings = get_settings()
    webhook_url = settings.discord_predictions_webhook_url.strip()
    if not webhook_url:
        return "not_configured"
    if not _is_discord_webhook_url(webhook_url):
        raise RuntimeError("DISCORD_PREDICTIONS_WEBHOOK_URL is not a valid Discord webhook URL")

    predictions_url = f"{settings.public_site_url.rstrip('/')}/predictions"
    payload = {
        "username": "BTB Predictions",
        "content": f"Predictions close in 12 hours, don't forget to submit your picks {predictions_url}",
        "allowed_mentions": {"parse": []},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, params={"wait": "true"}, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise RuntimeError("Could not send the Discord predictions reminder") from error
    return "sent"
