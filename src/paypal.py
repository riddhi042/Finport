import os
import threading
import time

import requests
from dotenv import load_dotenv
from paypalserversdk.api_helper import APIHelper
from paypalserversdk.configuration import Environment
from paypalserversdk.exceptions.api_exception import ApiException
from paypalserversdk.http.auth.o_auth_2 import ClientCredentialsAuthCredentials
from paypalserversdk.paypal_serversdk_client import PaypalServersdkClient

load_dotenv()

WEBHOOKS_PAGE_SIZE = 20
_access_token = None
_access_token_expires_at = 0
_access_token_lock = threading.Lock()

client = PaypalServersdkClient(
    environment=Environment.SANDBOX,
    client_credentials_auth_credentials=ClientCredentialsAuthCredentials(
        o_auth_client_id=os.environ["PAYPAL_CLIENT_ID"],
        o_auth_client_secret=os.environ["PAYPAL_CLIENT_SECRET"],
    ),
)


class PayPalApiError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def get_access_token():
    global _access_token, _access_token_expires_at

    with _access_token_lock:
        if _access_token and _access_token_expires_at > time.time() + 30:
            return _access_token

        try:
            response = client.o_auth_authorization.request_token(
                {"authorization": client.oauth_2.build_basic_auth_header()}
            )
        except ApiException as exc:
            raise PayPalApiError("PayPal OAuth request failed") from exc
        except requests.RequestException as exc:
            raise PayPalApiError("PayPal OAuth request failed") from exc

        token = response.body.access_token
        if not token:
            raise PayPalApiError("PayPal OAuth response did not contain an access token")

        _access_token = token
        expires_in = getattr(response.body, "expires_in", 0)
        _access_token_expires_at = time.time() + expires_in if expires_in else 0
        return _access_token


def _paypal_request(method, path, **kwargs):
    headers = kwargs.pop("headers", {})
    headers.update(
        {
            "Authorization": f"Bearer {get_access_token()}",
            "Accept": "application/json",
        }
    )
    try:
        response = requests.request(
            method,
            f"{client.config.get_base_uri()}{path}",
            headers=headers,
            timeout=15,
            **kwargs,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        raise PayPalApiError("PayPal API request failed", status_code) from exc
    except requests.RequestException as exc:
        raise PayPalApiError("PayPal API request failed") from exc

    return response


def verify_webhook_signature(event, headers, webhook_id):
    required_headers = {
        "auth_algo": "paypal-auth-algo",
        "cert_url": "paypal-cert-url",
        "transmission_id": "paypal-transmission-id",
        "transmission_sig": "paypal-transmission-sig",
        "transmission_time": "paypal-transmission-time",
    }
    verification_request = {
        field: headers.get(header)
        for field, header in required_headers.items()
    }
    if any(not value for value in verification_request.values()):
        return False

    verification_request["webhook_id"] = webhook_id
    verification_request["webhook_event"] = event
    try:
        result = _paypal_request(
            "POST",
            "/v1/notifications/verify-webhook-signature",
            json=verification_request,
        ).json()
    except requests.exceptions.JSONDecodeError as exc:
        raise PayPalApiError("PayPal returned an invalid verification response") from exc

    if not isinstance(result, dict):
        raise PayPalApiError("PayPal returned an invalid verification response")
    if result.get("verification_status") == "SUCCESS":
        return True
    if result.get("verification_status") == "FAILURE":
        return False
    raise PayPalApiError("PayPal returned an invalid verification response")


def list_webhooks():
    webhooks = []
    page = 1
    while True:
        try:
            result = _paypal_request(
                "GET",
                "/v1/notifications/webhooks",
                params={"page_size": WEBHOOKS_PAGE_SIZE, "page": page},
            ).json()
        except requests.exceptions.JSONDecodeError as exc:
            raise PayPalApiError("PayPal returned an invalid webhook list") from exc

        if not isinstance(result, dict) or not isinstance(result.get("webhooks"), list):
            raise PayPalApiError("PayPal returned an invalid webhook list")

        page_webhooks = result["webhooks"]
        if not all(isinstance(webhook, dict) for webhook in page_webhooks):
            raise PayPalApiError("PayPal returned an invalid webhook list")
        webhooks.extend(page_webhooks)
        total_pages = result.get("total_pages")
        if (
            (isinstance(total_pages, int) and page >= total_pages)
            or len(page_webhooks) < WEBHOOKS_PAGE_SIZE
        ):
            return webhooks
        page += 1


def get_order(order_id):
    response = client.orders.get_order({"id": order_id})
    return APIHelper.to_dictionary(response.body)
