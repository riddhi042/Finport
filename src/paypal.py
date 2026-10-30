import os

from dotenv import load_dotenv
from paypalserversdk.api_helper import APIHelper
from paypalserversdk.configuration import Environment
from paypalserversdk.http.auth.o_auth_2 import ClientCredentialsAuthCredentials
from paypalserversdk.paypal_serversdk_client import PaypalServersdkClient

load_dotenv()

client = PaypalServersdkClient(
    environment=Environment.SANDBOX,
    client_credentials_auth_credentials=ClientCredentialsAuthCredentials(
        o_auth_client_id=os.environ["PAYPAL_CLIENT_ID"],
        o_auth_client_secret=os.environ["PAYPAL_CLIENT_SECRET"],
    ),
)


def get_order(order_id):
    response = client.orders.get_order({"id": order_id})
    return APIHelper.to_dictionary(response.body)
