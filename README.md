# CrossBorder AI

Risk triage for international PayPal payments. Each payment is scored when it arrives, then PayPal is told what to do: capture it, void it, or hold it for a human to review.

Built for the PayPal AI Hackathon. **All payments are PayPal sandbox payments, and the model learned from simulated data. This is a prototype, not real fraud detection.**

## What it does

1. A buyer pays through PayPal Checkout (sandbox). The order is created with intent AUTHORIZE, so the money is held and not yet taken.
2. PayPal sends a signed webhook. The server verifies the signature and stores the event.
3. The payment is scored: a gradient-boosting model plus transparent policy rules (cross-border, foreign currency, much larger than this merchant's usual order).
4. The decision drives a PayPal API call through the PayPal Server SDK: low risk is captured, high risk is voided, and the middle band waits in a review queue.
5. A Streamlit dashboard shows live payments, plain-English explanations, the review queue and charts.

## Architecture

```
Buyer -> PayPal Checkout (sandbox)
              |  signed webhook
              v
        FastAPI  /webhook  -> verify signature -> SQLite (events)
              |
              v
        risk scoring (model + policy rules) -> SQLite (assessments)
              |
              v
        PayPal Server SDK: capture / void / queue for review
              |
              v
        Streamlit dashboard (reads the API)
```

## Tools

- PayPal sandbox, Orders and Payments APIs, webhooks, official `paypal-server-sdk` (Python)
- **APIMatic Context Plugin for PayPal**, used with VS Code Copilot to build the SDK integration, signature verification and the authorize, capture and void actions. See [docs/apimatic-log.md](docs/apimatic-log.md) for what the plugin did, what I changed and what the SDK did not cover.
- FastAPI, SQLite, scikit-learn, pandas, Streamlit, Plotly

## Setup

Needs Python 3.13.

```bash
git clone https://github.com/riddhi042/Finport.git
cd Finport
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash; on macOS/Linux use .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # then fill in your sandbox credentials
```

Create a PayPal sandbox app at developer.paypal.com and put its Client ID and Secret in `.env`. See `.env.example` for every setting.

Run the API and the dashboard:

```bash
uvicorn src.main:app --reload --port 8000
streamlit run dashboard/app.py
```

PayPal needs a public URL to send webhooks. For local runs use ngrok (`ngrok http 8000`) and register `https://<your-domain>/webhook` on your sandbox app. Set `PAYPAL_WEBHOOK_ID` from `python scripts/list_webhooks.py`, and keep `VERIFY_WEBHOOKS=true`.

Make a test payment:

```bash
python scripts/test_order.py --amount 50
```

Open the printed link, approve as a sandbox buyer, then press Enter. Actions are simulated unless `ACTIONS_ENABLED=true`.

[Hosted demo: add the Render link here once deployed.]

## Model and evaluation

- Data: PaySim, a synthetic mobile-money dataset (not PayPal data). Fraud only appears in TRANSFER and CASH_OUT rows, so the model trains on those.
- Split: by time (train on earlier steps, validate on the next, test on the last), not random.
- Metrics: PR-AUC, precision and recall. Accuracy is meaningless here, since 0.13% of rows are fraud.

| Model | Features | Validation PR-AUC | Test PR-AUC | Test recall at 50% precision |
|---|---|---|---|---|
| v1 | amount, type, hour of day | 0.213 | 0.300 | 0.289 |
| v2 | amount, type | 0.0056 | 0.0332 | 0.013 |

The random baseline PR-AUC on the test set is 0.0077. Validation and test fraud rates differ (0.14% vs 0.77%), so compare each score with its own baseline, not with each other.

- Time of day carries most of the signal in PaySim. In this simulator fraud appears to be spread across the day while normal activity follows a daily cycle, so night-time looks riskier. This is likely a simulation artifact and may not hold for real payments.
- **Deployed model: v1.** Models are only applied to payments of 17,000 or more (the range they were trained on); smaller payments are decided by policy rules alone.
- A benchmark model that also uses PaySim's balance columns scores near-perfectly, because the simulator leaves bookkeeping errors in those columns. PayPal events carry no balances, and this is not a real-world result.
- Policy rules (not learned): cross-border payer, foreign currency, and amounts far above this merchant's median payment.

## Limitations

- PaySim is simulated, and the fraud labels reflect the simulator.
- PaySim has no country or currency fields, so the cross-border signals are rules I wrote, not learned patterns.
- PaySim amounts are large. Payments below the model's trained range (17,000) get no model score, and only the rules apply. Sandbox demo payments are small, so the merchant-history rule drives the demo decisions.
- Sandbox payments carry no real fraud labels, so there is no live accuracy measurement.
- The review queue and PayPal actions are a prototype. A production system would need more safeguards, audit logging and monitoring.

## License

See the [LICENSE](LICENSE) file.
