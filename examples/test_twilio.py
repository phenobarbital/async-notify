from twilio.rest import Client

account_sid = "ACacf847ea8682ad1681e385628f85d79e"
auth_token = "c2e08a52eb3c3cc9881d7e56c7d5dc9a"

api_key = "SK77906d961ebb46c3b6d434e18a46eae7"
api_secret = "OtmQYPylCIm6wTlRTnjav1BjEl0BMinz"

from_number = "+13056778755"
message = "Proof of Concept: SMS"

client = Client(api_key, api_secret, account_sid)

accounts = client.api.accounts.list()
for record in accounts:
    print(record.sid)

key = client.keys(api_key).fetch()
print(key.friendly_name)

msg = client.messages.create(to='+17863292222', from_=from_number, body=message)
print(msg)
print(msg.sid)
