import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from src import actions, assess, db, paypal

load_dotenv()

VERIFY_WEBHOOKS = os.getenv("VERIFY_WEBHOOKS", "").strip().lower() == "true"
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "").strip()
ACTIONS_ENABLED = os.getenv("ACTIONS_ENABLED", "false").strip().lower() == "true"

if VERIFY_WEBHOOKS and not PAYPAL_WEBHOOK_ID:
    raise RuntimeError("PAYPAL_WEBHOOK_ID is required when VERIFY_WEBHOOKS=true")

app = FastAPI()
app.include_router(assess.router)
db.init()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/events")
def events():
    return db.all_events()


@app.get("/queue")
def queue():
    return assess.pending_review()


def _queue_action(assessment_id, action):
    assessment, claimed = assess.claim_pending_review(assessment_id, action)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if not claimed:
        raise HTTPException(
            status_code=409,
            detail="Assessment has already been acted on or has no authorization",
        )
    if not ACTIONS_ENABLED:
        assessment = assess.set_action_status(assessment_id, "simulated")
        return {
            "assessment": assessment,
            "action": action,
            "action_status": "simulated",
        }

    try:
        result = (
            actions.capture_authorization(assessment["authorization_id"])
            if action == "capture"
            else actions.void_authorization(assessment["authorization_id"])
        )
    except paypal.PayPalApiError as exc:
        assess.set_action_status(assessment_id, "error")
        status = f" (HTTP {exc.status_code})" if exc.status_code else ""
        raise HTTPException(
            status_code=502,
            detail=f"PayPal {action} action failed{status}",
        ) from exc

    final_status = "captured" if action == "capture" else "voided"
    assessment = assess.set_action_status(assessment_id, final_status)
    return {"assessment": assessment, "result": result}


@app.post("/queue/{assessment_id}/approve")
def approve_queued_assessment(assessment_id: int):
    return _queue_action(assessment_id, "capture")


@app.post("/queue/{assessment_id}/void")
def void_queued_assessment(assessment_id: int):
    return _queue_action(assessment_id, "void")


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
    if not isinstance(res, dict):
        res = {}
    event_type = event.get("event_type")
    related_ids = (res.get("supplementary_data") or {}).get("related_ids") or {}
    order_id = related_ids.get("order_id")
    authorization_id = res.get("id") if event_type == "PAYMENT.AUTHORIZATION.CREATED" else None
    if event_type == "PAYMENT.AUTHORIZATION.CREATED" and not (authorization_id and order_id):
        raise HTTPException(
            status_code=400,
            detail="Authorization event is missing its authorization or order ID",
        )

    email = country = None
    if order_id:
        order = await run_in_threadpool(paypal.get_order, order_id)
        payer = order.get("payer") or {}
        email = payer.get("email_address")
        country = (payer.get("address") or {}).get("country_code")
    amount = res.get("amount") or {}
    db.save({
        "id": event.get("id"), "event_type": event_type,
        "capture_id": res.get("id") if event_type == "PAYMENT.CAPTURE.COMPLETED" else None,
        "order_id": order_id,
        "amount": float(amount.get("value", 0)),
        "currency": amount.get("currency_code"),
        "status": res.get("status"), "payer_email": email,
        "payer_country": country, "created_at": event.get("create_time"),
        "raw": json.dumps(event),
    })
    print(event_type, res.get("id"), country)

    if event_type == "PAYMENT.AUTHORIZATION.CREATED":
        assessment, created = assess.assess_and_store(
            amount=float(amount.get("value", 0)),
            currency=amount.get("currency_code", "USD"),
            payer_country=country,
            order_id=order_id,
            authorization_id=authorization_id,
            actions_enabled=ACTIONS_ENABLED,
            deduplicate_order=True,
            return_assessment=True,
        )
        if created or assessment["action_status"] == "error":
            action = assessment.get("action")
            if action and ACTIONS_ENABLED:
                try:
                    if action == "capture":
                        await run_in_threadpool(
                            actions.capture_authorization, assessment["authorization_id"]
                        )
                        status = "captured"
                    else:
                        await run_in_threadpool(
                            actions.void_authorization, assessment["authorization_id"]
                        )
                        status = "voided"
                except paypal.PayPalApiError as exc:
                    assess.set_action_status(assessment["id"], "error")
                    status = f" (HTTP {exc.status_code})" if exc.status_code else ""
                    raise HTTPException(
                        status_code=502,
                        detail=f"PayPal {action} action failed{status}",
                    ) from exc
                assess.set_action_status(assessment["id"], status)
            elif action:
                assess.set_action_status(assessment["id"], "simulated")
        return {"received": True}

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        assess.assess_and_store(
            amount=float(amount.get("value", 0)),
            currency=amount.get("currency_code", "USD"),
            payer_country=country,
            capture_id=res.get("id"),
            order_id=order_id,
            deduplicate_order=True,
        )
    return {"received": True}
