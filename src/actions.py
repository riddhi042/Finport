import uuid

import requests
from paypalserversdk.api_helper import APIHelper
from paypalserversdk.exceptions.api_exception import ApiException

from src import paypal


def _request_id(action, resource_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"finport:{action}:{resource_id}"))


def _perform(action, resource_id, operation, parameters):
    request = {
        **parameters,
        "paypal_request_id": _request_id(action, resource_id),
        "prefer": "return=representation",
    }
    try:
        response = operation(request)
    except ApiException as exc:
        status = f" (HTTP {exc.response_code})" if exc.response_code else ""
        raise paypal.PayPalApiError(f"PayPal {action} failed{status}", exc.response_code) from exc
    except requests.RequestException as exc:
        raise paypal.PayPalApiError(f"PayPal {action} request failed") from exc

    result = APIHelper.to_dictionary(response.body)
    if not isinstance(result, dict):
        raise paypal.PayPalApiError(f"PayPal {action} returned an invalid response")
    return result


def authorize_order(order_id):
    return _perform(
        "authorize order",
        order_id,
        paypal.client.orders.authorize_order,
        {"id": order_id},
    )


def capture_authorization(authorization_id):
    return _perform(
        "capture authorization",
        authorization_id,
        paypal.client.payments.capture_authorized_payment,
        {"authorization_id": authorization_id},
    )


def void_authorization(authorization_id):
    return _perform(
        "void authorization",
        authorization_id,
        paypal.client.payments.void_payment,
        {"authorization_id": authorization_id},
    )


def refund_capture(capture_id):
    return _perform(
        "refund capture",
        capture_id,
        paypal.client.payments.refund_captured_payment,
        {"capture_id": capture_id, "body": {}},
    )
