from __future__ import print_function

import os
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import google_auth_httplib2
import httplib2
import json

OAUTH_TOKEN = os.getenv("OAUTH_TOKEN")


def main():
    """Runs the Apps Script architecture diagram parser to extract images from google docs.
    
    Shamelessly borrowed from:
    https://github.com/googleworkspace/python-samples/blob/main/apps_script/quickstart/quickstart.py
    """
    # pylint: disable=maybe-no-member
    script_id = 'AKfycbzDwuUjFDJTeCHukXsweJw7nT0T6_m2E-91ozsIrQqmyDWubReiIhIInc4wtIedPvJhRw'
    SCOPES = [
      "https://www.googleapis.com/auth/script.projects",
      "https://www.googleapis.com/auth/script.storage",
      "https://www.googleapis.com/auth/cloud-platform",
      "https://www.googleapis.com/auth/drive",
      "https://www.googleapis.com/auth/script.external_request"
    ]

    http = httplib2.Http(timeout=1800)
    
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if OAUTH_TOKEN:
        creds = Credentials.from_authorized_user_info(json.loads(OAUTH_TOKEN), SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        # with open('token.json', 'w') as token:
        #     token.write(creds.to_json())

    service = build('script', 'v1', http=google_auth_httplib2.AuthorizedHttp(creds, http=http))

    # Create an execution request object.
    request = {"function": "doWork"}

    while 1:
        try:
            # Make the API request.
            response = service.scripts().run(scriptId=script_id,
                                             body=request).execute()
            if 'error' in response:
                # The API executed, but the script returned an error.
                # Extract the first (and only) set of error details. The values of
                # this object are the script's 'errorMessage' and 'errorType', and
                # a list of stack trace elements.
                error = response['error']['details'][0]
                print(f"Script error message: {0}.{format(error['errorMessage'])}")
            elif response.get('response').get('result') == "No file IDs to parse.":
                print("Finished parsing all file IDs!")
                exit(0)
            else:
                print(response.get('response').get('result'))
                

        except HttpError as error:
            # The API encountered a problem before the script started executing.
            print(f"An error occurred: {error}")
            print(error.content)


if __name__ == '__main__':
    main()
