import os
import requests
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api-m.sandbox.paypal.com"


def get_token():
    r = requests.post(
        f"{BASE}/v1/oauth2/token",
        auth=(os.getenv("PAYPAL_CLIENT_ID"), os.getenv("PAYPAL_CLIENT_SECRET")),
        data={"grant_type": "client_credentials"},
    )
    return r.json()["access_token"]


def get_order(order_id):
    r = requests.get(
        f"{BASE}/v2/checkout/orders/{order_id}",
        headers={"Authorization": f"Bearer {get_token()}"},
    )
    return r.json()
