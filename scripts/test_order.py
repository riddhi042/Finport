import argparse
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import requests
from dotenv import load_dotenv
from paypalserversdk.api_helper import APIHelper
from paypalserversdk.exceptions.api_exception import ApiException
from paypalserversdk.models.amount_with_breakdown import AmountWithBreakdown
from paypalserversdk.models.checkout_payment_intent import CheckoutPaymentIntent
from paypalserversdk.models.order_request import OrderRequest
from paypalserversdk.models.purchase_unit_request import PurchaseUnitRequest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import actions, paypal

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Create and authorize a PayPal Sandbox order.")
    parser.add_argument("--amount", type=Decimal, default=Decimal("50.00"))
    parser.add_argument("--currency", default="USD")
    args = parser.parse_args()

    if not args.amount.is_finite() or args.amount <= 0:
        parser.error("--amount must be a finite value greater than zero")

    currency = args.currency.upper()
    request = OrderRequest(
        intent=CheckoutPaymentIntent.AUTHORIZE,
        purchase_units=[
            PurchaseUnitRequest(
                amount=AmountWithBreakdown(
                    currency_code=currency,
                    value=format(args.amount, "f"),
                )
            )
        ],
    )

    try:
        response = paypal.client.orders.create_order({
            "body": request,
            "paypal_request_id": str(uuid.uuid4()),
            "prefer": "return=representation",
        })
    except ApiException as exc:
        status = f" (HTTP {exc.response_code})" if exc.response_code else ""
        print(f"Unable to create PayPal order{status}.", file=sys.stderr)
        return 1
    except requests.RequestException:
        print("Unable to reach PayPal while creating the order.", file=sys.stderr)
        return 1

    order = APIHelper.to_dictionary(response.body)
    if not isinstance(order, dict) or not order.get("id"):
        print("PayPal did not return an order ID.", file=sys.stderr)
        return 1

    approval_url = next(
        (
            link["href"]
            for link in order.get("links", [])
            if link.get("rel") in ("approve", "payer-action")
        ),
        None,
    )
    if not approval_url:
        print("PayPal did not return an approval link.", file=sys.stderr)
        return 1

    print("Order ID:", order["id"], "| Status:", order.get("status"))
    print("\nOpen this URL and approve the order using a sandbox buyer:")
    print(approval_url)
    input("\nPress Enter after approving the order...")

    try:
        result = actions.authorize_order(order["id"])
    except paypal.PayPalApiError as exc:
        status = f" (HTTP {exc.status_code})" if exc.status_code else ""
        print(f"Unable to authorize PayPal order{status}.", file=sys.stderr)
        return 1

    purchase_units = result.get("purchase_units") or []
    authorizations = (
        (purchase_units[0].get("payments") or {}).get("authorizations") or []
        if purchase_units
        else []
    )
    if not authorizations or not authorizations[0].get("id"):
        print("PayPal did not return an authorization ID.", file=sys.stderr)
        return 1

    authorization = authorizations[0]
    print("Authorization ID:", authorization["id"], "| Status:", authorization.get("status"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
