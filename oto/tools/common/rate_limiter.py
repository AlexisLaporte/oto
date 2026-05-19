"""
Rate Limiter with JSON local storage.
Supports multiple services, action types, hourly/daily limits, and active hours scheduling.
"""

import json
import random
import time
import fcntl
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo


class RateLimiter:
    """
    Rate limiter using local JSON storage with support for:
    - Multiple services (linkedin, crunchbase, etc.)
    - Multiple action types per service
    - Hourly and daily limits
    - Active hours scheduling (e.g., 9h-18h Mon-Fri)
    - Humanization (random delays, skip probability)

    Storage location: ~/.cache/otomata/rate_limits.json
    """

    DEFAULT_LIMITS = {
        'max_per_hour': 60,
        'max_per_day': 500,
        'min_delay': 5,
    }

    DEFAULT_SCHEDULE = {
        'active_hours': {'start': 0, 'end': 24},
        'active_days': [0, 1, 2, 3, 4, 5, 6],  # All days
        'timezone': None,  # IANA tz name; None = system local time
        'randomize_delay': True,
        'skip_probability': 0.0,
    }

    def _now(self) -> datetime:
        """Current time in the schedule's timezone (or system local if None)."""
        tz_name = self.schedule.get('timezone')
        if tz_name:
            return datetime.now(ZoneInfo(tz_name))
        return datetime.now()

    def __init__(
        self,
        service: str,
        identity: str = "default",
        action_type: str = "default",
        limits: dict = None,
        schedule: dict = None,
        storage_path: Path = None,
    ):
        """
        Initialize rate limiter.

        Args:
            service: Service name (linkedin, crunchbase, etc.)
            identity: Identity/account name
            action_type: Type of action (profile_visit, search, etc.)
            limits: Override default limits (max_per_hour, max_per_day, min_delay)
            schedule: Override default schedule (active_hours, active_days, etc.)
            storage_path: Override default storage path
        """
        self.service = service
        self.identity = identity
        self.action_type = action_type
        self.limits = {**self.DEFAULT_LIMITS, **(limits or {})}
        self.schedule = {**self.DEFAULT_SCHEDULE, **(schedule or {})}

        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            self.storage_path = Path.home() / ".cache" / "otomata" / "rate_limits.json"

        self._ensure_storage()

    def _ensure_storage(self):
        """Ensure storage directory and file exist."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            self.storage_path.write_text("{}")

    def _load_data(self) -> dict:
        """Load data from JSON file with file locking."""
        try:
            with open(self.storage_path, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    return json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_data(self, data: dict):
        """Save data to JSON file with file locking."""
        with open(self.storage_path, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2, default=str)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _get_key(self) -> tuple:
        """Get the nested key path for this limiter."""
        return (self.service, self.identity, self.action_type)

    def _get_today_str(self) -> str:
        """Get today's date string."""
        return datetime.now().date().isoformat()

    def _get_record(self) -> dict:
        """Get current record for this limiter."""
        data = self._load_data()
        today = self._get_today_str()

        # Navigate to nested structure
        service_data = data.get(self.service, {})
        identity_data = service_data.get(self.identity, {})
        action_data = identity_data.get(self.action_type, {})
        record = action_data.get(today, {})

        return {
            'daily_count': record.get('daily_count', 0),
            'hourly_timestamps': record.get('hourly_timestamps', []),
            'last_request': record.get('last_request'),
        }

    def _update_record(self, record: dict):
        """Update record in storage."""
        data = self._load_data()
        today = self._get_today_str()

        # Initialize nested structure
        if self.service not in data:
            data[self.service] = {}
        if self.identity not in data[self.service]:
            data[self.service][self.identity] = {}
        if self.action_type not in data[self.service][self.identity]:
            data[self.service][self.identity][self.action_type] = {}

        # Clean old dates (keep only last 7 days)
        action_data = data[self.service][self.identity][self.action_type]
        week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
        old_dates = [d for d in action_data.keys() if d < week_ago]
        for d in old_dates:
            del action_data[d]

        # Update today's record
        action_data[today] = record
        self._save_data(data)

    def _clean_hourly_timestamps(self, timestamps: list) -> list:
        """Remove timestamps older than 1 hour."""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)

        cleaned = []
        for ts in timestamps:
            try:
                ts_dt = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
                if ts_dt > hour_ago:
                    cleaned.append(ts if isinstance(ts, str) else ts.isoformat())
            except Exception:
                pass

        return cleaned

    def _is_active_time(self) -> bool:
        """Check if current time is within active hours and days (in schedule TZ)."""
        now = self._now()

        # Check day
        active_days = self.schedule.get('active_days', [0, 1, 2, 3, 4, 5, 6])
        if now.weekday() not in active_days:
            return False

        # Check hour
        active_hours = self.schedule.get('active_hours', {'start': 0, 'end': 24})
        hour = now.hour
        return active_hours['start'] <= hour < active_hours['end']

    def _seconds_until_active(self) -> int:
        """Calculate seconds until next active period (in schedule TZ)."""
        now = self._now()
        active_hours = self.schedule.get('active_hours', {'start': 0, 'end': 24})
        active_days = self.schedule.get('active_days', [0, 1, 2, 3, 4, 5, 6])

        # If today is an active day and we're before active hours
        if now.weekday() in active_days and now.hour < active_hours['start']:
            target = now.replace(hour=active_hours['start'], minute=0, second=0, microsecond=0)
            return int((target - now).total_seconds())

        # Find next active day
        days_ahead = 1
        for _ in range(7):
            next_day = (now.weekday() + days_ahead) % 7
            if next_day in active_days:
                break
            days_ahead += 1

        target = (now + timedelta(days=days_ahead)).replace(
            hour=active_hours['start'], minute=0, second=0, microsecond=0
        )
        return int((target - now).total_seconds())

    def _should_random_skip(self) -> bool:
        """Determine if we should randomly skip this request for humanization."""
        skip_prob = self.schedule.get('skip_probability', 0.0)
        return random.random() < skip_prob

    def can_make_request(self) -> Tuple[bool, int, str]:
        """
        Check if we can make a request.

        Returns:
            (allowed, wait_time_seconds, reason)
        """
        record = self._get_record()
        now = datetime.now()

        # 1. Check active hours
        if not self._is_active_time():
            return False, self._seconds_until_active(), 'outside_active_hours'

        # 2. Check minimum delay since last request
        if record['last_request']:
            try:
                last = datetime.fromisoformat(record['last_request'])
                elapsed = (now - last).total_seconds()

                if elapsed < self.limits['min_delay']:
                    wait_time = int(self.limits['min_delay'] - elapsed) + 1
                    return False, wait_time, 'min_delay'
            except Exception:
                pass

        # 3. Check hourly limit
        hourly_timestamps = self._clean_hourly_timestamps(record['hourly_timestamps'])
        if len(hourly_timestamps) >= self.limits['max_per_hour']:
            oldest = datetime.fromisoformat(hourly_timestamps[0])
            wait_until = oldest + timedelta(hours=1)
            wait_time = int((wait_until - now).total_seconds()) + 1
            return False, max(wait_time, 60), 'hourly_limit'

        # 4. Check daily limit
        if record['daily_count'] >= self.limits['max_per_day']:
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            wait_time = int((tomorrow - now).total_seconds())
            return False, wait_time, 'daily_limit'

        # 5. Random skip for humanization (optional)
        if self._should_random_skip():
            return False, random.randint(60, 180), 'random_skip'

        return True, 0, 'ok'

    def record_request(self):
        """Record that a request was made."""
        record = self._get_record()
        now_iso = datetime.now().isoformat()

        # Update hourly timestamps (clean + add new)
        hourly_timestamps = self._clean_hourly_timestamps(record['hourly_timestamps'])
        hourly_timestamps.append(now_iso)

        record['daily_count'] = record['daily_count'] + 1
        record['hourly_timestamps'] = hourly_timestamps
        record['last_request'] = now_iso

        self._update_record(record)

    def wait_if_needed(self, auto_wait_max: int = 300) -> Optional[int]:
        """
        Wait if rate limit requires it, with humanized random delay.

        Args:
            auto_wait_max: Maximum seconds to auto-wait (default 300s = 5min)

        Returns:
            Seconds waited, or None if limit exceeded (should stop)
        """
        can_proceed, wait_time, reason = self.can_make_request()

        if not can_proceed:
            if reason == 'outside_active_hours':
                print(f"🌙 [{self.service}] Outside active hours. Resume at {self.next_active_time()}")
                return None

            if reason == 'random_skip':
                jitter = random.randint(30, 90)
                print(f"🎲 [{self.service}] Random skip: waiting {jitter}s")
                time.sleep(jitter)
                return jitter

            if wait_time <= auto_wait_max:
                if self.schedule.get('randomize_delay', True):
                    jitter = random.randint(0, 10)
                    wait_time += jitter

                print(f"⏳ [{self.service}] Rate limit ({reason}): waiting {wait_time}s")
                time.sleep(wait_time)
                return wait_time
            else:
                print(f"❌ [{self.service}] Rate limit ({reason}). Wait {wait_time}s until {self.can_make_request_at()}")
                return None

        # Even when allowed, add small random delay for humanization
        if self.schedule.get('randomize_delay', True):
            jitter = random.randint(1, 5)
            time.sleep(jitter)
            return jitter

        return 0

    def next_active_time(self) -> str:
        """Return human-readable time when next active period starts (schedule TZ)."""
        if self._is_active_time():
            return "now"

        seconds = self._seconds_until_active()
        next_time = self._now() + timedelta(seconds=seconds)
        tz_name = self.schedule.get('timezone')
        suffix = f" {tz_name}" if tz_name else ""
        return next_time.strftime("%Y-%m-%d %H:%M") + suffix

    def can_make_request_at(self) -> str:
        """Return human-readable time when next request is allowed."""
        can_proceed, wait_time, _ = self.can_make_request()
        if can_proceed:
            return "now"

        next_time = datetime.now() + timedelta(seconds=wait_time)
        return next_time.strftime("%H:%M:%S")

    def get_stats(self) -> dict:
        """Get current rate limit statistics."""
        record = self._get_record()
        now = datetime.now()

        hourly_timestamps = self._clean_hourly_timestamps(record['hourly_timestamps'])

        last_request_time = None
        if record['last_request']:
            try:
                last = datetime.fromisoformat(record['last_request'])
                seconds_ago = int((now - last).total_seconds())
                last_request_time = f"{seconds_ago}s ago"
            except Exception:
                pass

        can_proceed, _, reason = self.can_make_request()

        return {
            "service": self.service,
            "identity": self.identity,
            "action_type": self.action_type,
            "requests_last_hour": len(hourly_timestamps),
            "requests_today": record['daily_count'],
            "last_request": last_request_time,
            "hourly_limit": self.limits['max_per_hour'],
            "daily_limit": self.limits['max_per_day'],
            "min_delay": self.limits['min_delay'],
            "can_request": can_proceed,
            "reason": reason if not can_proceed else None,
            "is_active_time": self._is_active_time(),
        }

    def reset(self):
        """Reset rate limit counters for this identity and action type."""
        data = self._load_data()
        today = self._get_today_str()

        try:
            del data[self.service][self.identity][self.action_type][today]
            self._save_data(data)
            print(f"✅ Rate limiter reset for {self.service}/{self.identity}/{self.action_type}")
        except KeyError:
            print(f"ℹ️  No data to reset for {self.service}/{self.identity}/{self.action_type}")


# Preset configurations for common services
class LinkedInRateLimiter(RateLimiter):
    """LinkedIn-specific rate limiter with conservative defaults."""

    ACCOUNT_PRESETS = {
        'free': {
            'profile_visit': {'max_per_hour': 10, 'max_per_day': 80, 'min_delay': 45},
            'search_export': {'max_per_hour': 80, 'max_per_day': 1000, 'min_delay': 5},
            'company_scrape': {'max_per_hour': 200, 'max_per_day': 2000, 'min_delay': 2},
        },
        'premium': {
            'profile_visit': {'max_per_hour': 12, 'max_per_day': 100, 'min_delay': 30},
            'search_export': {'max_per_hour': 100, 'max_per_day': 1000, 'min_delay': 5},
            'company_scrape': {'max_per_hour': 200, 'max_per_day': 2000, 'min_delay': 2},
        },
        'sales_navigator': {
            'profile_visit': {'max_per_hour': 15, 'max_per_day': 150, 'min_delay': 20},
            'search_export': {'max_per_hour': 150, 'max_per_day': 2500, 'min_delay': 3},
            'company_scrape': {'max_per_hour': 300, 'max_per_day': 3000, 'min_delay': 2},
        },
    }

    def __init__(
        self,
        identity: str = "default",
        action_type: str = "profile_visit",
        account_type: str = "free",
        **kwargs,
    ):
        limits = self.ACCOUNT_PRESETS.get(account_type, self.ACCOUNT_PRESETS['free']).get(
            action_type, self.ACCOUNT_PRESETS['free']['profile_visit']
        )

        schedule = {
            'active_hours': {'start': 8, 'end': 22},
            'active_days': [0, 1, 2, 3, 4, 5, 6],
            'timezone': 'Europe/Paris',
            'randomize_delay': True,
            'skip_probability': 0.05,
        }

        super().__init__(
            service="linkedin",
            identity=identity,
            action_type=action_type,
            limits=limits,
            schedule=schedule,
            **kwargs,
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rate Limiter CLI")
    parser.add_argument("--service", "-s", default="linkedin", help="Service name")
    parser.add_argument("--identity", "-i", default="default", help="Identity to check")
    parser.add_argument("--action", "-a", default="default", help="Action type")
    parser.add_argument("--reset", action="store_true", help="Reset counters")
    parser.add_argument("--test", action="store_true", help="Test recording a request")
    args = parser.parse_args()

    limiter = RateLimiter(
        service=args.service,
        identity=args.identity,
        action_type=args.action,
    )

    if args.reset:
        limiter.reset()
    elif args.test:
        print("🧪 Testing rate limit...")
        waited = limiter.wait_if_needed()
        if waited is not None:
            limiter.record_request()
            print(f"✅ Request recorded (waited {waited}s)")
        else:
            print("❌ Cannot make request now")
    else:
        print(f"📊 Rate Limiter Stats:")
        stats = limiter.get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")
