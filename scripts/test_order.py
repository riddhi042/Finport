import os
import requests
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api-m.sandbox.paypal.com"

# 1. Get an access token
CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")

token = requests.post(
    f"{BASE}/v1/oauth2/token",
    auth=(CLIENT_ID, CLIENT_SECRET),
    data={"grant_type": "client_credentials"},
).json()["access_token"]

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# 2. Create an order
order = requests.post(
    f"{BASE}/v2/checkout/orders",
    headers=headers,
    json={
        "intent": "CAPTURE",
        "purchase_units": [{"amount": {"currency_code": "USD", "value": "50.00"}}],
    },
).json()

print("Order ID:", order["id"], "| Status:", order["status"])

# 3. Print the link the buyer must open
for link in order["links"]:
    if link["rel"] in ("approve", "payer-action"):
        print("\nOpen this in your browser and log in as a sandbox BUYER:")
        print(link["href"])

input("\nPress Enter after you have approved the payment in the browser...")

# 4. Capture the payment
capture = requests.post(
    f"{BASE}/v2/checkout/orders/{order['id']}/capture",
    headers=headers,
)
result = capture.json()
print("Capture status:", result.get("status"))