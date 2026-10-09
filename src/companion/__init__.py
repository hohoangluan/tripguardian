"""Public companion API: Đang đi (trip rows, check-in, suggestions) and the confirmed Google Calendar export
(docs/COMPANION.md)."""

from .calendar import Calendar, CalendarError, GoogleCalendarApi, NotConnected
from .service import Companion, load_settings
from .trips import plan_hash, stops_of

__all__ = ["Calendar", "CalendarError", "Companion", "GoogleCalendarApi", "NotConnected", "load_settings", "plan_hash", "stops_of"]
