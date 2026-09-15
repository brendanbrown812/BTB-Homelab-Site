from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def as_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class WeeklySchedule:
    weekday: int
    at: time
    timezone_name: str

    @property
    def label(self) -> str:
        weekday = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[
            self.weekday
        ]
        return f"{weekday} {self.at.strftime('%H:%M')} {self.timezone_name}"

    def next_after(self, value: datetime) -> datetime:
        zone = ZoneInfo(self.timezone_name)
        local = as_utc(value).astimezone(zone)
        days = (self.weekday - local.weekday()) % 7
        candidate = datetime.combine(local.date() + timedelta(days=days), self.at, tzinfo=zone)
        if candidate <= local:
            candidate += timedelta(days=7)
        return candidate.astimezone(timezone.utc)
