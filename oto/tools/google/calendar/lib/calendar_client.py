"""Google Calendar API client using OAuth2 user credentials."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']


class CalendarClientError(Exception):
    """Calendar API error."""


class CalendarClient:
    """Google Calendar API client.

    Args:
        credentials: OAuth2 user credentials. If None, uses get_user_credentials().
        account: Named account to use (None = auto-detect if single account).
    """

    def __init__(self, credentials: Optional[Credentials] = None, account: Optional[str] = None):
        if credentials is None:
            from oto.tools.google.credentials import get_user_credentials
            credentials = get_user_credentials(SCOPES, account=account)
        self.service = build('calendar', 'v3', credentials=credentials)

    def list_calendars(self) -> list[dict]:
        """List all calendars accessible by the user."""
        resp = self.service.calendarList().list().execute()
        return [
            {
                'id': cal['id'],
                'summary': cal.get('summary', ''),
                'primary': cal.get('primary', False),
                'accessRole': cal.get('accessRole', ''),
            }
            for cal in resp.get('items', [])
        ]

    def list_events(
        self,
        calendar_id: str = 'primary',
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 20,
        query: Optional[str] = None,
    ) -> list[dict]:
        """List events from a calendar.

        Args:
            calendar_id: Calendar ID (default: 'primary').
            time_min: Start of time range (ISO 8601). Default: none (no lower bound).
            time_max: End of time range (ISO 8601). Default: none (no upper bound).
            max_results: Maximum number of events.
            query: Free text search query.
        """

        kwargs = {
            'calendarId': calendar_id,
            'maxResults': max_results,
            'singleEvents': True,
            'orderBy': 'startTime',
        }
        if time_min:
            kwargs['timeMin'] = time_min
        if time_max:
            kwargs['timeMax'] = time_max
        if query:
            kwargs['q'] = query

        resp = self.service.events().list(**kwargs).execute()
        return [self._format_event(e) for e in resp.get('items', [])]

    def get_event(self, event_id: str, calendar_id: str = 'primary') -> dict:
        """Get a single event by ID."""
        event = self.service.events().get(
            calendarId=calendar_id, eventId=event_id,
        ).execute()
        return self._format_event(event, detailed=True)

    def today(self, calendar_id: str = 'primary', max_results: int = 50) -> list[dict]:
        """List today's events."""
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self.list_events(
            calendar_id=calendar_id,
            time_min=start.isoformat(),
            time_max=end.isoformat(),
            max_results=max_results,
        )

    def upcoming(
        self,
        days: int = 7,
        calendar_id: str = 'primary',
        max_results: int = 50,
    ) -> list[dict]:
        """List events for the next N days."""
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days)
        return self.list_events(
            calendar_id=calendar_id,
            time_min=now.isoformat(),
            time_max=end.isoformat(),
            max_results=max_results,
        )

    @staticmethod
    def _format_event(event: dict, detailed: bool = False) -> dict:
        """Format an event into a clean dict."""
        start = event.get('start', {})
        end = event.get('end', {})
        result = {
            'id': event['id'],
            'summary': event.get('summary', '(no title)'),
            'start': start.get('dateTime', start.get('date', '')),
            'end': end.get('dateTime', end.get('date', '')),
            'status': event.get('status', ''),
            'htmlLink': event.get('htmlLink', ''),
        }
        location = event.get('location')
        if location:
            result['location'] = location

        hangout = event.get('hangoutLink')
        if hangout:
            result['hangoutLink'] = hangout

        organizer = event.get('organizer', {})
        if organizer:
            result['organizer'] = organizer.get('email', '')

        if detailed:
            result['description'] = event.get('description', '')
            attendees = event.get('attendees', [])
            if attendees:
                result['attendees'] = [
                    {
                        'email': a.get('email', ''),
                        'responseStatus': a.get('responseStatus', ''),
                        'displayName': a.get('displayName', ''),
                    }
                    for a in attendees
                ]
            result['recurrence'] = event.get('recurrence', [])
            reminders = event.get('reminders', {})
            if reminders:
                result['reminders'] = reminders

        return result
