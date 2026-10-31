import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from src import db, paypal

load_dotenv()

VERIFY_WEBHOOKS = os.getenv("VERIFY_WEBHOOKS", "").strip().lower() == "true"
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "").strip()

if VERIFY_WEBHOOKS and not PAYPAL_WEBHOOK_ID:
    raise RuntimeError("PAYPAL_WEBHOOK_ID is required when VERIFY_WEBHOOKS=true")

app = FastAPI()
db.init()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/events")
def events():
    return db.all_events()


@app.post("/webhook")
async def webhook(request: Request):
    try:
        event = json.loads(await request.body())
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid webhook JSON") from None

    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Webhook event must be a JSON object")

    if VERIFY_WEBHOOKS:
        try:
            valid_signature = await run_in_threadpool(
                paypal.verify_webhook_signature,
                event,
                request.headers,
                PAYPAL_WEBHOOK_ID,
            )
        except paypal.PayPalApiError:
            raise HTTPException(
                status_code=502,
                detail="Webhook signature verification is unavailable",
            ) from None
        if not valid_signature:
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    res = event.get("resource", {})
    order_id = (res.get("supplementary_data", {})
                   .get("related_ids", {}).get("order_id"))
    email = country = None
    if order_id:
        order = paypal.get_order(order_id)
        payer = order.get("payer", {})
        email = payer.get("email_address")
        country = payer.get("address", {}).get("country_code")
    db.save({
        "id": event.get("id"), "event_type": event.get("event_type"),
        "capture_id": res.get("id"), "order_id": order_id,
        "amount": float(res.get("amount", {}).get("value", 0)),
        "currency": res.get("amount", {}).get("currency_code"),
        "status": res.get("status"), "payer_email": email,
        "payer_country": country, "created_at": event.get("create_time"),
        "raw": json.dumps(event),
    })
    print(event.get("event_type"), res.get("id"), country)
    return {"received": True}
