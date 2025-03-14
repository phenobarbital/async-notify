import asyncio
import json
from notify.models import Actor, TeamsWebhook, TeamsCard, TeamsChannel, TeamsChat
from notify.providers.teams import Teams
from notify.conf import (
    MS_TEAMS_DEFAULT_TEAMS_ID,
    MS_TEAMS_DEFAULT_CHANNEL_ID,
    MS_TEAMS_DEFAULT_WEBHOOK
)

adaptive_card  = {
  "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
  "type": "AdaptiveCard",
  "version": "1.5",
  "body": [
    {
      "type": "TextBlock",
      "size": "medium",
      "weight": "bolder",
      "text": "My Own Form",
      "horizontalAlignment": "center",
      "wrap": True,
      "style": "heading"
    },
    {
      "type": "Input.Text",
      "label": "Name",
      "style": "text",
      "id": "SimpleVal",
      "isRequired": True,
      "errorMessage": "Name is required",
      "placeholder": "Enter your name"
    },
    {
      "type": "Input.Text",
      "label": "Homepage",
      "style": "url",
      "id": "UrlVal",
      "placeholder": "Enter your homepage url"
    },
    {
      "type": "Input.Text",
      "label": "Email",
      "style": "email",
      "id": "EmailVal",
      "placeholder": "Enter your email"
    },
    {
      "type": "Input.Text",
      "label": "Phone",
      "style": "tel",
      "id": "TelVal",
      "placeholder": "Enter your phone number"
    },
    {
      "type": "Input.Text",
      "label": "Comments",
      "style": "text",
      "isMultiline": True,
      "id": "MultiLineVal",
      "placeholder": "Enter any comments"
    },
    {
      "type": "Input.Number",
      "label": "Quantity (Minimum -5, Maximum 5)",
      "min": -5,
      "max": 5,
      "value": 1,
      "id": "NumVal",
      "errorMessage": "The quantity must be between -5 and 5"
    },
    {
      "type": "Input.Date",
      "label": "Due Date",
      "id": "DateVal",
      "value": "2025-02-20"
    },
    {
      "type": "Input.Time",
      "label": "Start time",
      "id": "TimeVal",
      "value": "16:59"
    },
    {
      "type": "TextBlock",
      "size": "medium",
      "weight": "bolder",
      "text": "Input ChoiceSet",
      "horizontalAlignment": "center",
      "wrap": True,
      "style": "heading"
    },
    {
      "type": "Input.ChoiceSet",
      "id": "CompactSelectVal",
      "label": "What color do you want? (compact)",
      "style": "compact",
      "value": "1",
      "choices": [
        {
          "title": "Red",
          "value": "1"
        },
        {
          "title": "Green",
          "value": "2"
        },
        {
          "title": "Blue",
          "value": "3"
        }
      ]
    },
    {
      "type": "Input.ChoiceSet",
      "id": "SingleSelectVal",
      "label": "What color do you want? (expanded)",
      "style": "expanded",
      "value": "1",
      "choices": [
        {
          "title": "Red",
          "value": "1"
        },
        {
          "title": "Green",
          "value": "2"
        },
        {
          "title": "Blue",
          "value": "3"
        }
      ]
    },
    {
      "type": "Input.ChoiceSet",
      "id": "MultiSelectVal",
      "label": "What color do you want? (multiselect)",
      "isMultiSelect": True,
      "value": "1,3",
      "choices": [
        {
          "title": "Red",
          "value": "1"
        },
        {
          "title": "Green",
          "value": "2"
        },
        {
          "title": "Blue",
          "value": "3"
        }
      ]
    },
    {
      "type": "TextBlock",
      "size": "medium",
      "weight": "bolder",
      "text": "Input.Toggle",
      "horizontalAlignment": "center",
      "wrap": True,
      "style": "heading"
    },
    {
      "type": "Input.Toggle",
      "label": "Please accept the terms and conditions:",
      "title": "I accept the terms and conditions (True/False)",
      "valueOn": "true",
      "valueOff": "false",
      "id": "AcceptsTerms",
      "isRequired": True,
      "errorMessage": "Accepting the terms and conditions is required"
    },
    {
      "type": "Input.Toggle",
      "label": "How do you feel about red cars?",
      "title": "Red cars are better than other cars",
      "valueOn": "RedCars",
      "valueOff": "NotRedCars",
      "id": "ColorPreference"
    }
  ],
  "actions": [
    {
      "type": "Action.Submit",
      "title": "Submit",
      "data": {
        "id": "1234567890"
      }
    },
    {
      "type": "Action.ShowCard",
      "title": "Show Card",
      "card": {
        "type": "AdaptiveCard",
        "body": [
          {
            "type": "Input.Text",
            "label": "Enter comment",
            "style": "text",
            "id": "CommentVal"
          }
        ],
        "actions": [
          {
            "type": "Action.Submit",
            "title": "OK"
          }
        ]
      }
    }
  ]
}

# sample with media:
adcard = """
{"$schema":"http://adaptivecards.io/schemas/adaptive-card.json","type":"AdaptiveCard","version":"1.5","contentType":"application/vnd.microsoft.card.adaptive","metadata":{"webUrl":"https://contoso.com/tab"},"body":[{"type":"TextBlock","size":"Medium","weight":"Bolder","text":"User Registration","horizontalAlignment":"Center","wrap":true,"style":"heading"},{"type":"TextBlock","size":"large","weight":"bolder","text":"Please fill out the form to register."},{"type":"Input.Text","id":"first_name","label":"First Name"},{"type":"Input.Text","id":"last_name","label":"Last Name"},{"type":"Input.Text","id":"username","label":"Username","isRequired":true,"errorMessage":"Username is required"},{"type":"Input.Text","id":"age","label":"Age"}],"actions":[{"type":"Action.Submit","title":"Submit"}]}
"""

# Convert the adaptive card to JSON and assign it as your message payload:
msg = json.dumps(adaptive_card)

async def send_direct_message():
    user = {
        "name": "Javier Leon",
        "account": {
            "address": "jlara@trocglobal.com"
        }
    }
    try:
        recipient = Actor(**user)
    except Exception as e:
        print(f"Error creating recipient: {e.payload}")
        return
    tm = Teams(as_user=True)
    async with tm as conn:
        result = await conn.send(
            recipient=recipient,
            message=adcard
        )
    print('RESULT > ', result)

if __name__ == "__main__":
    asyncio.run(send_direct_message())
