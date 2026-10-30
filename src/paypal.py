import atexit
import os

from dotenv import load_dotenv
from paypal import PaypalClient
from paypal.core import ClientCredentials

load_dotenv()

client = PaypalClient(
    base_url="https://api-m.sandbox.paypal.com",
    oauth2=ClientCredentials(
        client_id=os.environ["PAYPAL_CLIENT_ID"],
        client_secret=os.environ["PAYPAL_CLIENT_SECRET"],
    ),
)
atexit.register(client.close)


def get_order(order_id):
    order = client.orders.get_order(order_id)
    return order.to_dict(exclude_unset=True)
