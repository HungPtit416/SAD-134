import os
import time

import psycopg


def main() -> None:
    host = os.environ.get("DATABASE_HOST")
    if not host:
        return
    port = int(os.environ.get("DATABASE_PORT", "5432"))
    name = os.environ.get("DATABASE_NAME", "payment_db")
    user = os.environ.get("DATABASE_USER", "postgres")
    password = os.environ.get("DATABASE_PASSWORD", "postgres")

    deadline = time.time() + 60
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            conn = psycopg.connect(host=host, port=port, dbname=name, user=user, password=password)
            conn.close()
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1)
    raise SystemExit(f"Database not ready: {last_err}")


if __name__ == "__main__":
    main()

