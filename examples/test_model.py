from notify.models import Actor

DEFAULT_RECIPIENT = {
    "name": "Jesus Lara",
    "account": {
        "address": "jesuslarag@gmail.com",
        "phone": "+34692817379"
    }
}

recipient = Actor(**DEFAULT_RECIPIENT)
print(recipient)
