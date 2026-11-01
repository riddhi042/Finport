import json
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src import db, risk

router = APIRouter()


def init():
    with db.conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capture_id TEXT, order_id TEXT, amount REAL, currency TEXT,
            payer_country TEXT, risk_score REAL, decision TEXT,
            model_rank REAL, model_raw_score REAL, rule_points INTEGER,
            reasons TEXT, model_version TEXT, created_at TEXT)""")


init()


class AssessRequest(BaseModel):
    amount: float = Field(gt=0)
    currency: str = "USD"
    payer_country: str | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    capture_id: str | None = None
    order_id: str | None = None
    dry_run: bool = False


def assess_and_store(amount, currency="USD", payer_country=None, hour=None,
                     capture_id=None, order_id=None):
    r = risk.assess(amount, currency, payer_country, hour)
    with db.conn() as c:
        c.execute(
            """INSERT INTO assessments (capture_id, order_id, amount, currency,
               payer_country, risk_score, decision, model_rank, model_raw_score,
               rule_points, reasons, model_version, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (capture_id, order_id, amount, currency, payer_country, r["risk_score"],
             r["decision"], r["model_rank"], r["model_raw_score"], r["rule_points"],
             json.dumps(r["reasons"]), r["model_version"],
             datetime.now(timezone.utc).isoformat()),
        )
    return r


@router.post("/assess")
def assess_endpoint(req: AssessRequest):
    if req.dry_run:
        return risk.assess(req.amount, req.currency, req.payer_country, req.hour)
    return assess_and_store(req.amount, req.currency, req.payer_country, req.hour,
                            req.capture_id, req.order_id)


@router.get("/assessments")
def list_assessments():
    with db.conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM assessments ORDER BY id DESC LIMIT 100")]