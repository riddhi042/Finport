from pathlib import Path
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import paypal


def safe_webhook_url(url):
    if not isinstance(url, str):
        return ""

    parsed = urlsplit(url)
    safe_query = urlencode(
        [(key, "[REDACTED]") for key, _ in parse_qsl(parsed.query, keep_blank_values=True)]
    )
    safe_netloc = parsed.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parsed.scheme, safe_netloc, parsed.path, safe_query, ""))


def main():
    try:
        webhooks = paypal.list_webhooks()
    except paypal.PayPalApiError as exc:
        status = f" (HTTP {exc.status_code})" if exc.status_code else ""
        print(f"Unable to list PayPal webhooks{status}.", file=sys.stderr)
        return 1

    if not webhooks:
        print("No PayPal webhooks found.")
        return 0

    print("Webhook ID\tURL")
    for webhook in webhooks:
        print(f"{webhook.get('id', '')}\t{safe_webhook_url(webhook.get('url', ''))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
