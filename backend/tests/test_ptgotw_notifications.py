import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.features.ptgotw.models import PTGWriteup
from app.features.ptgotw.notifications import send_writeup_published_notification


class PTGOTWNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_discord_notification_links_directly_to_writeup(self):
        writeup = PTGWriteup(id=uuid.uuid4(), year=2026, week=4)
        settings = SimpleNamespace(
            disable_outbound_notifications=False,
            discord_ptgotw_webhook_url="https://discord.com/api/webhooks/123/token",
            public_site_url="https://btb.example.com/",
        )
        response = Mock()
        response.raise_for_status = Mock()
        client = AsyncMock()
        client.post.return_value = response
        client_context = AsyncMock()
        client_context.__aenter__.return_value = client

        with patch(
            "app.features.ptgotw.notifications.get_settings", return_value=settings,
        ), patch(
            "app.features.ptgotw.notifications.httpx.AsyncClient", return_value=client_context,
        ):
            result = await send_writeup_published_notification(writeup, "The Writer")

        self.assertEqual(result, "sent")
        request = client.post.await_args
        self.assertEqual(request.args[0], settings.discord_ptgotw_webhook_url)
        self.assertEqual(
            request.kwargs["json"]["content"],
            f"The Writer has published their week 4 writeup. Read it here: https://btb.example.com/ptgotw/{writeup.id}",
        )
        self.assertEqual(request.kwargs["json"]["allowed_mentions"], {"parse": []})

    async def test_notifications_disabled_never_constructs_an_http_client(self):
        writeup = PTGWriteup(id=uuid.uuid4(), year=2026, week=4)
        settings = SimpleNamespace(
            disable_outbound_notifications=True,
            discord_ptgotw_webhook_url="https://discord.com/api/webhooks/real-looking/token",
            public_site_url="https://btb.example.com/",
        )

        with patch(
            "app.features.ptgotw.notifications.get_settings", return_value=settings,
        ), patch("app.features.ptgotw.notifications.httpx.AsyncClient") as client:
            result = await send_writeup_published_notification(writeup, "The Writer")

        self.assertEqual(result, "disabled")
        client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
