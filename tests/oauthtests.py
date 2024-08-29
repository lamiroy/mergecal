import os

import requests
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("URL")
userN = os.getenv("USER")
passW = os.getenv("PASSWD")

if __name__ == '__main__':

    try:
        auth = requests.auth.HTTPBasicAuth(username=userN, password=passW)
        response = requests.get(
            url,
            auth=auth, timeout=10)
        response.raise_for_status()
        answer = response.text
        print(answer)


    except requests.exceptions.HTTPError as e:
        print(f'Error {e}')
        answer = response.text
        print(answer)
