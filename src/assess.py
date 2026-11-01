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
            reasons TEXT, model_version TEXT, created_at TEXT,
            authorization_id TEXT, action TEXT, action_status TEXT, acted_at TEXT)""")
        columns = {
            row["name"] for row in c.execute("PRAGMA table_info(assessments)")
        }
        for name, column_type in (
            ("authorization_id", "TEXT"),
            ("action", "TEXT"),
            ("action_status", "TEXT"),
            ("acted_at", "TEXT"),
        ):
            if name not in columns:
                c.execute(f"ALTER TABLE assessments ADD COLUMN {name} {column_type}")


init()


def prior_amounts(exclude_capture_id=None, limit=50):
    with db.conn() as c:
        rows = c.execute(
            "SELECT amount FROM assessments WHERE capture_id IS NULL OR capture_id != ? "
            "ORDER BY id DESC LIMIT ?",
            (exclude_capture_id or "", limit),
        ).fetchall()
    return [r["amount"] for r in rows]


class AssessRequest(BaseModel):
    amount: float = Field(gt=0)
    currency: str = "USD"
    payer_country: str | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    capture_id: str | None = None
    order_id: str | None = None
    dry_run: bool = False


def assess_and_store(amount, currency="USD", payer_country=None, hour=None,
                     capture_id=None, order_id=None, authorization_id=None,
                     actions_enabled=False, deduplicate_order=False,
                     return_assessment=False):
    with db.conn() as c:
        if deduplicate_order:
            c.execute("BEGIN IMMEDIATE")
            if order_id:
                existing = c.execute(
                    "SELECT * FROM assessments WHERE order_id = ? ORDER BY id DESC LIMIT 1",
                    (order_id,),
                ).fetchone()
            elif capture_id:
                existing = c.execute(
                    "SELECT * FROM assessments WHERE capture_id = ? ORDER BY id DESC LIMIT 1",
                    (capture_id,),
                ).fetchone()
            else:
                existing = None

            if existing:
                if capture_id and not existing["capture_id"]:
                    c.execute(
                        "UPDATE assessments SET capture_id = ? WHERE id = ?",
                        (capture_id, existing["id"]),
                    )
                    existing = c.execute(
                        "SELECT * FROM assessments WHERE id = ?", (existing["id"],)
                    ).fetchone()
                if return_assessment:
                    return dict(existing), False
                return {
                    "risk_score": existing["risk_score"],
                    "decision": existing["decision"],
                    "model_rank": existing["model_rank"],
                    "model_raw_score": existing["model_raw_score"],
                    "rule_points": existing["rule_points"],
                    "reasons": json.loads(existing["reasons"]),
                    "model_version": existing["model_version"],
                }

        r = risk.assess(amount, currency, payer_country, hour, prior_amounts(capture_id))
        action = None
        action_status = None
        if authorization_id:
            action = {"approve": "capture", "hold": "void"}.get(r["decision"])
            if r["decision"] == "review":
                action_status = "pending_review"
            elif actions_enabled:
                action_status = "error"
            else:
                action_status = "simulated"

        now = datetime.now(timezone.utc).isoformat()
        acted_at = now if action_status in ("error", "simulated") else None
        cursor = c.execute(
            """INSERT INTO assessments (capture_id, order_id, amount, currency,
               payer_country, risk_score, decision, model_rank, model_raw_score,
               rule_points, reasons, model_version, created_at, authorization_id,
               action, action_status, acted_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (capture_id, order_id, amount, currency, payer_country, r["risk_score"],
             r["decision"], r["model_rank"], r["model_raw_score"], r["rule_points"],
             json.dumps(r["reasons"]), r["model_version"],
             now, authorization_id, action, action_status, acted_at),
        )
        if return_assessment:
            row = c.execute(
                "SELECT * FROM assessments WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return dict(row), True
    return r


def pending_review():
    with db.conn() as c:
        return [dict(row) for row in c.execute(
            "SELECT * FROM assessments WHERE action_status = 'pending_review' ORDER BY id"
        )]


def claim_pending_review(assessment_id, action):
    with db.conn() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            "SELECT * FROM assessments WHERE id = ?", (assessment_id,)
        ).fetchone()
        if row is None:
            return None, False
        if row["action_status"] != "pending_review" or not row["authorization_id"]:
            return dict(row), False

        acted_at = datetime.now(timezone.utc).isoformat()
        c.execute(
            """UPDATE assessments SET action = ?, action_status = 'error', acted_at = ?
               WHERE id = ? AND action_status = 'pending_review'""",
            (action, acted_at, assessment_id),
        )
        updated = c.execute(
            "SELECT * FROM assessments WHERE id = ?", (assessment_id,)
        ).fetchone()
        return dict(updated), True


def set_action_status(assessment_id, action_status):
    with db.conn() as c:
        c.execute(
            "UPDATE assessments SET action_status = ?, acted_at = ? WHERE id = ?",
            (action_status, datetime.now(timezone.utc).isoformat(), assessment_id),
        )
        row = c.execute(
            "SELECT * FROM assessments WHERE id = ?", (assessment_id,)
        ).fetchone()
        return dict(row) if row else None


@router.post("/assess")
def assess_endpoint(req: AssessRequest):
    if req.dry_run:
        return risk.assess(req.amount, req.currency, req.payer_country, req.hour,
                           prior_amounts(req.capture_id))
    return assess_and_store(req.amount, req.currency, req.payer_country, req.hour,
                            req.capture_id, req.order_id)


@router.get("/assessments")
def list_assessments():
    with db.conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM assessments ORDER BY id DESC LIMIT 100")]