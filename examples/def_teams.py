import requests
import msal
import json
from navconfig import config


# Constants
CLIENT_ID = config.get('MS_CLIENT_ID')
CLIENT_SECRET = config.get('MS_CLIENT_SECRET')
TENANT_ID = config.get('MS_TENANT_ID')
TEAM_ID = config.get('MSTEAMS_TEAM_ID')
CHANNEL_ID = config.get('MSTEAMS_DEFAULT_CHANNEL_ID')
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]  # This is just an example scope for Microsoft Graph
# SCOPES = ["https://graph.microsoft.com/ChannelMessage.Send"]

credentials = {
    "username": config.get('O365_USER'),
    "password": config.get('O365_PASSWORD')
}

# Create a PublicClientApplication instance
app = msal.PublicClientApplication(
    CLIENT_ID, authority=AUTHORITY
)

# # Create a confidential client application
# app = msal.ConfidentialClientApplication(
#     CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
# )

# Acquire token using ROPC
result = app.acquire_token_by_username_password(
    username=credentials["username"],
    password=credentials["password"],
    scopes=SCOPES
)

# Acquire a token
token = None
# result = app.acquire_token_for_client(scopes=SCOPES)

if "access_token" in result:
    token = result["access_token"]
    # Use the token to make requests
else:
    print(result.get("error"))
    print(result.get("error_description"))
    print(result.get("correlation_id"))

print('ACCESS TOKEN > ', token)
# Send Message to Teams Channel
message_url = f'https://graph.microsoft.com/v1.0/teams/{TEAM_ID}/channels/{CHANNEL_ID}/messages'

# message_url = f"https://graph.microsoft.com/beta/teams/{TEAM_ID}/channels/{CHANNEL_ID}/messages"
print('URL > ', message_url)
headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
}
message_data = {
    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
    "type": "AdaptiveCard",
    "version": "1.6",
    "contentType": "application/vnd.microsoft.card.adaptive",
    "speak": "<s>Your  meeting about \"Adaptive Card design session\"<break strength='weak'/> is starting at 12:30pm</s><s>Do you want to snooze <break strength='weak'/> or do you want to send a late notification to the attendees?</s>",
    "metadata": {
        "webUrl": "https://contoso.com/tab"
    },
    "body": [{
        "content": "Hello, World!",
        "contentType": "text"
    }]
}

message_data = {
    "subject": None,
    "body": {
        "contentType": "html",
        "content": "<attachment id=\"74d20c7f34aa4a7fb74e2b30004247c5\"></attachment>"
    },
    "attachments": [
        {
            "id": "74d20c7f34aa4a7fb74e2b30004247c5",
            "contentType": "application/vnd.microsoft.card.thumbnail",
            "contentUrl": None,
            "content": "{\r\n  \"title\": \"This is an example of posting a card\",\r\n  \"subtitle\": \"<h3>This is the subtitle</h3>\",\r\n  \"text\": \"Here is some body text. <br>\\r\\nAnd a <a href=\\\"http://microsoft.com/\\\">hyperlink</a>. <br>\\r\\nAnd below that is some buttons:\",\r\n  \"buttons\": [\r\n    {\r\n      \"type\": \"messageBack\",\r\n      \"title\": \"Login to FakeBot\",\r\n      \"text\": \"login\",\r\n      \"displayText\": \"login\",\r\n      \"value\": \"login\"\r\n    }\r\n  ]\r\n}",
            "name": None,
            "thumbnailUrl": None
        }
    ]
}

message_data = {
  "body": {
    "contentType": "html",
    "content": "<attachment id=\"4465B062-EE1C-4E0F-B944-3B7AF61EAF40\"></attachment>"
  },
  "attachments": [
    {
      "id": "4465B062-EE1C-4E0F-B944-3B7AF61EAF40",
      "contentType": "application/vnd.microsoft.card.adaptive",
      "content": json.dumps(
          {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.2",
            "type": "AdaptiveCard",
            "originator": "GUID",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "Enter your message:",
                    "wrap": True
                },
                {
                    "type": "Input.Text",
                    "id": "userMessage",
                    "placeholder": "Type your message here...",
                    "isMultiline": True
                }
            ],
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "Send",
                    "url": "http://localhost:5000/test",
                    "body": "{ \"message\": \"{{userMessage.value}}\" }",
                    "headers": [
                        {
                            "name": "Content-Type",
                            "value": "application/json"
                        }
                    ]
                }
            ]
        }
      )
    }
  ]
}

response = requests.post(message_url, headers=headers, json=message_data)
print(response.json())
