import json
from fastapi import FastAPI, Request
from src import db, paypal

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
    event = await request.json()
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
