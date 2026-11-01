import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import assess, db

with db.conn() as c:
    rows = c.execute(
        "SELECT capture_id, order_id, amount, currency, payer_country "
        "FROM events WHERE event_type = 'PAYMENT.CAPTURE.COMPLETED'"
    ).fetchall()
    done = {r["capture_id"] for r in c.execute("SELECT capture_id FROM assessments")}

n = 0
for r in rows:
    if r["capture_id"] in done or not r["amount"]:
        continue
    assess.assess_and_store(
        amount=r["amount"], currency=r["currency"] or "USD",
        payer_country=r["payer_country"], capture_id=r["capture_id"], order_id=r["order_id"],
    )
    n += 1
print(f"scored {n} payments")