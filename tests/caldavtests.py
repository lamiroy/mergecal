import os

from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

from mergecal.calendars.caldav import fetch_and_create_caldav_calendar, get_ics

from datetime import datetime
import json
import caldav
from icalendar import Calendar, Event

# CalDAV info

if __name__ == '__main__':

    load_dotenv()
    url = os.getenv("CALURL")
    userN = os.getenv("USER")
    passW = os.getenv("PASSWD")

    auth = HTTPBasicAuth(username=userN, password=passW)

    cal = get_ics(url, auth)
    print(cal)

