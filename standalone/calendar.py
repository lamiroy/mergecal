import inspect
import re
import zoneinfo
from datetime import timedelta, datetime
from enum import Enum

import requests
from requests import RequestException, Session
from requests.auth import HTTPBasicAuth

from icalendar import Calendar as ICal, TimezoneStandard, Timezone, Event

from mergecal.mergecal.calendars.caldav import is_caldav_url, fetch_and_create_caldav_calendar
from mergecal.mergecal.calendars.meetup import is_meetup_url, fetch_and_create_meetup_calendar
from mergecal.standalone import logger


class Calendar:

    def __str__(self):
        return self.name

    # https://stackoverflow.com/a/70251235
    TIMEZONE_CHOICES = tuple(
        (x, x)
        for x in sorted(zoneinfo.available_timezones(), key=str.lower)
        if x != "localtime"  # Exclude 'localtime' from the choices
    )

    def __init__(self, name: str = ''):
        self.name = name
        self.timezone = "Europe/Paris"
        self.include_source = False  # Include source name in event title
        self.sources = {}

    def addSource(self, src):
        assert isinstance(src, Source)
        self.sources.add(src)

    def deleteSource(self):
        pass

    def update(self):
        pass

    def getICS(self):
        merger = CalendarMerger(self)
        calendar_str = merger.merge()

        if not calendar_str:
            raise RuntimeError('empty calendar')

        return calendar_str


class Source:
    class CalendarTypes(Enum):
        ICAL = 'ICAL'
        CALDAV = 'CDAV'
        MEETUP = 'MTUP'
        UNKNOWN = 'UNKW'

    def __init__(self, url: str, *, name: str = 'default', username: str = None, password: str = None):
        self._name = name  # CharField
        self._url = url  # URLField
        self._username = username  # EncryptedCharField
        self._password = password  # EncryptedCharField
        self._caltype = Source.CalendarTypes.UNKNOWN
        self._include_title = True  # BooleanField
        self.include_description = False  # BooleanField - Include Event Description
        self.include_location = True  # BooleanField - Include Event Location,
        self.custom_prefix = None  # CharField optional prefix to add before each event title from this feed (e.g., '[Work]').
        self.exclude_keywords = ''  # TextField keywords separated by commas. Events from this feed containing these keywords in their title

    @property
    def name(self) -> str:
        return self._name

    @property
    def url(self) -> str:
        return self._url

    @property
    def username(self) -> str:
        return self._username

    @property
    def password(self) -> str:
        return self._password

    @property
    def include_title(self) -> bool:
        return self._include_title

    @property
    def caltype(self) -> CalendarTypes:
        return self._caltype

    def __str__(self):
        return self.name

    def clean(self):
        self._caltype = validate_auth_url(self.url, self.username, self.password)


def validate_auth_url(url, username=None, password=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,"
                  "application/signed-exchange;v=b3;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",  # Do Not Track Request Header
        "Upgrade-Insecure-Requests": "1",
    }

    # if url is meetup.com, skip validation
    if "meetup.com" in url:
        return Source.CalendarTypes.MEETUP

    timeout_value = 30
    try:
        r = requests.get(url, headers=headers, auth=HTTPBasicAuth(username, password), timeout=30)
        r.raise_for_status()
        cal = ICal.from_ical(r.text)  # noqa: F841
        return Source.CalendarTypes.ICAL
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        if status_code == 401:
            if re.search('oauth', str(r.text), re.IGNORECASE):
                raise RuntimeError(f'OAuth Authentication Requires')
            raise RuntimeError(f'Valid Username and Password Required\n{e}')
        raise RuntimeError(f'HTTPError {status_code}\n{e}')
    except ValueError as e:
        if re.search('webdav', str(e), re.IGNORECASE):
            return Source.CalendarTypes.CALDAV

        raise RuntimeError(f"{inspect.currentframe().f_code.co_name}: enter a valid icalendar feed.\n{e}")
    except requests.exceptions.ReadTimeout:
        raise RuntimeError(f"Connexion timed out after {timeout_value} seconds. Please try again later")


class CalendarMerger:
    def __init__(self, calendar: Calendar):
        self.calendar = calendar
        self.merged_calendar = None

    def merge(self) -> str:
        self.merged_calendar = self._create_new_calendar()
        self._add_sources()
        self._finalize_merged_calendar()
        calendar_str = self.merged_calendar.to_ical().decode("utf-8")

        return calendar_str

    def _create_new_calendar(self) -> ICal:
        new_cal = ICal()
        new_cal.add("prodid", f"-//{self.calendar.name}//mergecal.org//")
        new_cal.add("version", "2.0")
        new_cal.add("x-wr-calname", self.calendar.name)
        self._add_timezone(new_cal)
        return new_cal

    def _add_timezone(self, cal: ICal) -> None:
        tzinfo = zoneinfo.ZoneInfo(self.calendar.timezone)
        newtimezone = Timezone()
        newtimezone.add("tzid", tzinfo.key)

        now = datetime.now()
        std = TimezoneStandard()
        std.add(
            "dtstart",
            now - timedelta(days=1),
        )
        std.add("tzoffsetfrom", timedelta(seconds=-now.utcoffset().total_seconds()))
        std.add("tzoffsetto", timedelta(seconds=-now.utcoffset().total_seconds()))
        newtimezone.add_component(std)

        cal.add_component(newtimezone)

    def _add_sources(self) -> None:
        existing_uids = set()
        for source in self.calendar.sources:
            self._add_source_events(source, existing_uids)

    def _add_source_events(self, source: Source, existing_uids: set) -> None:
        source_calendar = None
        if source.caltype == Source.CalendarTypes.MEETUP or (source.caltype == Source.CalendarTypes.UNKNOWN and
                                                             is_meetup_url(source.url)):
            source_calendar = fetch_and_create_meetup_calendar(source.url)
        elif source.caltype == Source.CalendarTypes.CALDAV or (source.caltype == Source.CalendarTypes.UNKNOWN and
                                                               is_caldav_url(source.url)):
            auth = HTTPBasicAuth(username=source.username, password=source.password)
            source_calendar = fetch_and_create_caldav_calendar(source.url, auth)
        else:
            source_calendar = self._fetch_source_calendar(source)

        if source_calendar:
            for component in source_calendar.walk("VEVENT"):
                self._process_event(component, source, existing_uids)

    def _fetch_source_calendar(self, source: Source) -> None | ICal:
        url = source.url
        auth = HTTPBasicAuth(username=source.username, password=source.password)
        headers = {
            "User-Agent": "MergeCal/1.0 (https://mergecal.org)",
            "Accept": "text/calendar, application/calendar+xml, application/calendar+json",  # noqa: E501
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        }

        def validate_calendar(cal: ICal) -> None:
            if not cal.walk():
                msg = f"Calendar from {url} contains no components"
                raise ValueError(msg)

        try:
            response = Session().get(url, headers=headers, timeout=30, auth=auth)
            response.encoding = "utf-8"
            response.raise_for_status()

            # Log the response content for debugging
            logger.debug(f"Response content for {url}: {response.text[:500]}...")

            calendar = ICal.from_ical(response.text)
            validate_calendar(calendar)
        except RequestException as e:
            self._add_source_error(source, f"HTTP error: {e!s}")
            return None
        except ValueError as e:
            self._add_source_error(source, f"Parsing error: {e!s}")
            return None

        return calendar

    def _process_event(self, event: Event, source: Source, existing_uids: set) -> None:
        uid = event.get("uid")
        if uid is None or uid not in existing_uids:
            self._apply_event_rules(event, source)
            if self._should_include_event(event, source):
                self.merged_calendar.add_component(event)
                if uid is not None:
                    existing_uids.add(uid)

    def _apply_event_rules(self, event: Event, source: Source) -> None:
        if not source.include_title:
            event["summary"] = source.custom_prefix or source.name
        elif source.custom_prefix:
            event["summary"] = f"{source.custom_prefix}: {event.get('summary')}"

        if not source.include_description:
            event.pop("description", None)

        if not source.include_location:
            event.pop("location", None)

    def _should_include_event(self, event: Event, source: Source) -> bool:
        if not source.exclude_keywords:
            return True

        exclude_keywords = [
            kw.strip().lower() for kw in source.exclude_keywords.split(",")
        ]
        event_title = event.get("summary", "").lower()
        return not any(kw in event_title for kw in exclude_keywords)

    def _add_source_error(self, source: Source, error_message: str) -> None:
        if not hasattr(self, "source_errors"):
            self.source_errors = []
        self.source_errors.append(
            {
                "source_name": source.name,
                "source_url": source.url,
                "error": error_message,
            },
        )

    def _finalize_merged_calendar(self) -> None:
        if hasattr(self, "source_errors") and self.source_errors:
            error_event = Event()
            error_event.add("summary", "MergeCal: Source Errors")
            error_description = "The following sources had errors:\n\n"
            for error in self.source_errors:
                error_description += f"- {error['source_name']} ({error['source_url']}): {error['error']}\n"  # noqa: E501
            error_event.add("description", error_description)
            error_event.add("dtstart", datetime.now())
            error_event.add("dtend", datetime.now() + timedelta(hours=1))
            self.merged_calendar.add_component(error_event)
