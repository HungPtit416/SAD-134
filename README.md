# SAD E-commerce (Microservices + Docker + Frontend)

This repository contains a minimal E-commerce MVP following the architecture requirements:

- One **Product Service** for the whole catalog (do not split by category).
- Separate services for **Cart**, **Order**, **User**, **Inventory**.
- A simple **frontend** to demonstrate the workflow.

## DDD folder structure (per service)

Each Django app is organized to match the report structure:

- `domain/`: pure domain entities / interfaces
- `application/`: use-cases / orchestration (calls repositories, gateways)
- `infrastructure/`: ORM models, repository implementations, external integrations
- `presentation/`: REST API (serializers, views, urls)

To keep Django conventions working, entrypoints like `models.py`, `views.py`, `serializers.py`, `urls.py` remain, but they delegate to the corresponding `infrastructure/` or `presentation/` modules.

## Run with Docker

From the repository root:

```bash
docker compose up --build
```

After startup:

- Frontend: `http://localhost:3000`
- Product Service API: `http://localhost:8001/api/`
- Cart Service API: `http://localhost:8002/api/`
- Order Service API: `http://localhost:8003/api/`
- User Service API: `http://localhost:8004/api/`
- Inventory Service API: `http://localhost:8005/api/`

## Demo workflow (matches the report)

- User requests products from Product Service
- Add items to Cart (Cart stores `product_id`)
- Checkout creates an Order from the Cart

## Quick API checks

- List products: `GET http://localhost:8001/api/products/`
- Get cart: `GET http://localhost:8002/api/cart/?user_id=demo-user`
- Add to cart: `POST http://localhost:8002/api/cart/items/?user_id=demo-user` body `{"product_id":1,"quantity":1}`
- Checkout: `POST http://localhost:8003/api/checkout/?user_id=demo-user`

