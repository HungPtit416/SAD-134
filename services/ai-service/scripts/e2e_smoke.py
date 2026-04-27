import os

import requests


def main() -> None:
    base = os.environ.get("BASE_GATEWAY", "http://gateway").rstrip("/")
    email = os.environ.get("E2E_EMAIL", "user1@gmail.com")
    password = os.environ.get("E2E_PASSWORD", "123456")

    login = requests.post(
        f"{base}/user/api/auth/login/",
        json={"username": email, "password": password},
        timeout=30,
    )
    login.raise_for_status()
    access = login.json()["access"]
    auth = {"Authorization": f"Bearer {access}"}
    auth_json = {"Authorization": f"Bearer {access}", "Content-Type": "application/json"}

    prods = requests.get(f"{base}/product/api/products/", timeout=30).json()
    if not prods:
        raise RuntimeError("No products returned from product-service.")
    pid = prods[0]["id"]

    requests.post(
        f"{base}/cart/api/cart/items/?user_id={email}",
        json={"product_id": pid, "quantity": 1},
        headers=auth_json,
        timeout=30,
    ).raise_for_status()

    cart = requests.get(f"{base}/cart/api/cart/?user_id={email}", headers=auth, timeout=30)
    cart.raise_for_status()
    cartj = cart.json()
    items = cartj.get("items") or []
    if items:
        item_id = items[0]["id"]
        requests.patch(
            f"{base}/cart/api/cart/items/{item_id}/?user_id={email}",
            json={"quantity": 2},
            headers=auth_json,
            timeout=30,
        ).raise_for_status()

    co = requests.post(
        f"{base}/order/api/checkout/?user_id={email}",
        json={},
        headers=auth_json,
        timeout=60,
    )
    co.raise_for_status()
    order = co.json()

    out = {
        "product_id": pid,
        "cart_id": cartj.get("id"),
        "order_id": order.get("id"),
        "payment_status": order.get("payment_status"),
        "shipping_status": order.get("shipping_status"),
        "tracking_code": order.get("tracking_code"),
    }
    print(out)


if __name__ == "__main__":
    main()

