import logging
from urllib.parse import urlparse

import caldav
import requests
from icalendar import Calendar as Ical
from icalendar import Event

logger = logging.getLogger(__name__)


def is_caldav_url(url: str, auth=None) -> bool:
    # Parse the URL
    # parsed_url = urlparse(url, 'https')

    try:
        with caldav.DAVClient(url=url, auth=auth) as client:
            _ = client.principal()
        return True
    except requests.RequestException as e:
        print(f"An error occurred: {e}")
        return False


def fetch_and_create_caldav_calendar(caldav_url: str, auth) -> Ical | None:
    logger.info(f"Using CalDAV calendar {caldav_url}")
    if is_caldav_url(caldav_url, auth):
        try:
            return get_ics(caldav_url, auth)
        except requests.RequestException as e:
            print(f"An error occurred while fetching iCalendar data: {e}")
    else:
        print(f"The URL {caldav_url} is not a CalDAV resource.")
    return None


def get_ics(url, auth) -> Ical:
    client = caldav.DAVClient(url=url, auth=auth)

    calendar = client.calendar(url=url)

    logger.info(f"Using CalDAV calendar {calendar}")
    results = calendar.events()
    outputCal = Ical()

    for event in results:
        icalEvent = Ical.from_ical(event._data)

        for component in icalEvent.subcomponents:
            if component.name == "VEVENT":
                outputCal.add_component(component)

    return outputCal


