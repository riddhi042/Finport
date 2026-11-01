import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "risk_model_v2.joblib"
_bundle = joblib.load(MODEL_PATH)
MODEL = _bundle["model"]
FEATURES = _bundle["features"]
VERSION = _bundle["version"]
QUANTILES = np.asarray(_bundle["val_score_quantiles"])

MERCHANT_COUNTRY = os.getenv("MERCHANT_COUNTRY", "US")
MERCHANT_CURRENCY = os.getenv("MERCHANT_CURRENCY", "USD")
REVIEW_AT = float(os.getenv("REVIEW_AT", "90"))
HOLD_AT = float(os.getenv("HOLD_AT", "98"))
MODEL_MIN_AMOUNT = float(os.getenv("MODEL_MIN_AMOUNT", "0"))


def assess(amount, currency="USD", payer_country=None, hour=None):
    if hour is None:
        hour = datetime.now(timezone.utc).hour

    if amount >= MODEL_MIN_AMOUNT:
        row = pd.DataFrame([{
            "log_amount": float(np.log1p(amount)),
            "is_transfer": 1,
            "hour": hour,
        }])[FEATURES]
        raw = float(MODEL.predict_proba(row)[0, 1])
        model_rank = float(min(100.0, np.searchsorted(QUANTILES, raw, side="right") / len(QUANTILES) * 100))
        reasons = [f"Model rank {model_rank:.0f}/100 from amount and transaction pattern (learned from simulated data)"]
    else:
        raw = 0.0
        model_rank = 0.0
        reasons = [f"Amount {amount:,.2f} is below the range the model was trained on (min {MODEL_MIN_AMOUNT:,.0f}), so the model score was not used"]

    points = 0
    if payer_country and payer_country != MERCHANT_COUNTRY:
        points += 10
        reasons.append(f"Cross-border: payer in {payer_country}, merchant in {MERCHANT_COUNTRY} (+10, policy rule)")
    if currency != MERCHANT_CURRENCY:
        points += 10
        reasons.append(f"Foreign currency: {currency} vs {MERCHANT_CURRENCY} (+10, policy rule)")

    score = min(100.0, model_rank + points)
    decision = "hold" if score >= HOLD_AT else "review" if score >= REVIEW_AT else "approve"
    return {
        "risk_score": round(score, 1),
        "decision": decision,
        "model_rank": round(model_rank, 1),
        "model_raw_score": raw,
        "rule_points": points,
        "reasons": reasons,
        "model_version": VERSION,
    }