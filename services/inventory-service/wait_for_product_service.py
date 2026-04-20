"""
Wait until product-service accepts HTTP (migrations + gunicorn ready).
depends_on only waits for container start, not for the app to listen.
"""

import os
import time

import requests


def main() -> None:
    base = os.environ.get("PRODUCT_SERVICE_URL", "http://product-service:8000").rstrip("/")
    url = f"{base}/api/products/"
    deadline = time.time() + 180
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return
            last_err = RuntimeError(f"unexpected status {resp.status_code}")
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(2)
    raise SystemExit(f"product-service not ready at {url}: {last_err}")


if __name__ == "__main__":
    main()
