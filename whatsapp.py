
import os
import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v25.0")


def check_whatsapp_config():
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        raise RuntimeError(
            "Missing WhatsApp settings. Check your .env file."
        )

    url = (
        f"https://graph.facebook.com/{API_VERSION}/"
        f"{PHONE_NUMBER_ID}"
    )
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def send_test_message(recipient: str):
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        raise RuntimeError("Check WhatsApp settings in .env")

    url = (
        f"https://graph.facebook.com/{API_VERSION}/"
        f"{PHONE_NUMBER_ID}/messages"
    )
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": "jaspers_market_order_confirmation_v1",
            "language": {"code": "en_US"},
            "components": [{
                "type": "body",
                "parameters": [
    {"type": "text", "text": "Gym Test"},
    {"type": "text", "text": "TEST-001"},
    {"type": "text", "text": "Oct 18, 2026"},
],
            }],
        },
    }

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()

def send_gym_reminder(
    recipient: str,
    member_name: str,
    expiry_date: str,
    fee: str,
):
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        raise RuntimeError("Check WhatsApp settings in .env")

    url = (
        f"https://graph.facebook.com/{API_VERSION}/"
        f"{PHONE_NUMBER_ID}/messages"
    )

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": "gym_membership_reminder",
            "language": {"code": "en"},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": member_name},
                    {"type": "text", "text": expiry_date},
                    {"type": "text", "text": fee},
                ],
            }],
        },
    }

    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    check_whatsapp_config()
    recipient = input("Enter your own verified WhatsApp number (with country code): ")
    result = send_test_message(recipient)
    print("WhatsApp API accepted the message.")
    print(result)
