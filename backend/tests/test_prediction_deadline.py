import unittest
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from app.features.predictions.models import PredictionWeek, WeekStatus
from app.features.predictions.routes import _default_lock_at, _migrate_friday_lock_to_thursday


CENTRAL_TIME = ZoneInfo("America/Chicago")


class PredictionDeadlineTests(unittest.TestCase):
    def test_default_deadline_is_thursday_at_seven_central(self):
        wednesday = datetime(2026, 9, 9, 12, tzinfo=CENTRAL_TIME)

        deadline = _default_lock_at(wednesday).astimezone(CENTRAL_TIME)

        self.assertEqual(deadline, datetime(2026, 9, 10, 19, tzinfo=CENTRAL_TIME))

    def test_existing_open_friday_deadline_moves_to_thursday(self):
        week = PredictionWeek(
            season_id=uuid.uuid4(),
            week_number=1,
            lock_at=datetime(2026, 9, 11, 19, tzinfo=CENTRAL_TIME),
            status=WeekStatus.open,
        )

        changed = _migrate_friday_lock_to_thursday(week)

        self.assertTrue(changed)
        self.assertEqual(week.lock_at.astimezone(CENTRAL_TIME), datetime(2026, 9, 10, 19, tzinfo=CENTRAL_TIME))

    def test_finalized_deadline_is_not_changed(self):
        original = datetime(2026, 9, 11, 19, tzinfo=CENTRAL_TIME)
        week = PredictionWeek(
            season_id=uuid.uuid4(),
            week_number=1,
            lock_at=original,
            status=WeekStatus.final,
        )

        changed = _migrate_friday_lock_to_thursday(week)

        self.assertFalse(changed)
        self.assertEqual(week.lock_at, original)


if __name__ == "__main__":
    unittest.main()
