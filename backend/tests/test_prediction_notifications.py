import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.features.predictions.notifications import send_prediction_deadline_notification


class PredictionNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_discord_reminder_links_directly_to_predictions(self):
        settings = SimpleNamespace(
            discord_predictions_webhook_url="https://discord.com/api/webhooks/123/token",
            public_site_url="https://btb.example.com/",
        )
        response = Mock()
        response.raise_for_status = Mock()
        client = AsyncMock()
        client.post.return_value = response
        client_context = AsyncMock()
        client_context.__aenter__.return_value = client

        with patch(
            "app.features.predictions.notifications.get_settings", return_value=settings,
        ), patch(
            "app.features.predictions.notifications.httpx.AsyncClient", return_value=client_context,
        ):
            result = await send_prediction_deadline_notification()

        self.assertEqual(result, "sent")
        request = client.post.await_args
        self.assertEqual(request.args[0], settings.discord_predictions_webhook_url)
        self.assertEqual(
            request.kwargs["json"]["content"],
            "Predictions close in 12 hours, don't forget to submit your picks https://btb.example.com/predictions",
        )
        self.assertEqual(request.kwargs["json"]["allowed_mentions"], {"parse": []})

    async def test_invalid_webhook_url_fails_before_request(self):
        settings = SimpleNamespace(
            discord_predictions_webhook_url="https://example.com/not-discord",
            public_site_url="https://btb.example.com",
        )
        with patch("app.features.predictions.notifications.get_settings", return_value=settings):
            with self.assertRaisesRegex(RuntimeError, "not a valid Discord webhook URL"):
                await send_prediction_deadline_notification()


if __name__ == "__main__":
    unittest.main()
