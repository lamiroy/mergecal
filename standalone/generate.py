from cryptography.fernet import Fernet

from standalone import calendar
from io import StringIO
import pandas as pd

from standalone.calendar import Source, CalendarMerger

calendar_config_file = 'calendars.csv'
key = None

if __name__ == '__main__':

    cal = calendar.Calendar("Bart")

    if key:
        f = Fernet(key)
        # opening the original file to decrypt
        with open(calendar_config_file, 'rb') as file:
            DATA = file.read()
        DATA = f.decrypt(DATA)
        print('Data have been Decrypted')
    else:
        # opening the original file to decrypt
        with open(calendar_config_file, 'r') as file:
            DATA = file.read()

    DATA = StringIO(DATA)

    # Makes a panda dataframe with the data
    df = pd.read_csv(DATA)

    for _, source_params in df.iterrows():
        p = source_params.to_dict()
        s = Source(**p)
        cal.addSource(s)

    c = CalendarMerger(cal).merge()
    print(c)
