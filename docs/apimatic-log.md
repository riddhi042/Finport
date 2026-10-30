# APIMatic Context Plugin log

## 2026-10-30: Replaced hand-written HTTP calls with the PayPal Python SDK

- **Tool:** VS Code Copilot (Agent mode) + APIMatic PayPal Context Plugin
- **Plugin skills used:** python-client-initialization, python-authentication, python-calling-endpoints
- **Task:** Rewrite `src/paypal.py` to use the official `paypal-server-sdk` (sandbox) instead of raw `requests`, keeping `get_order()` returning the same dict shape.
- **Decision:** The agent first proposed installing an unpinned SDK from a git URL (`@main`). I declined and had it use the official PyPI package, pinned to 2.2.0.
- **Result:** The SDK fetched a real sandbox order, and the webhook still stores `payer_email` and `payer_country` correctly. PayPal's delivery status shows Success.