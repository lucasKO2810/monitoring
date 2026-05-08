import logging
import os
import random
import uuid

from fastapi.responses import JSONResponse
from opentelemetry import trace

from src.observability import call_json, create_observed_app, jitter, log_event


SERVICE_NAME = os.getenv("SERVICE_NAME", "frontend")
ORDERS_URL = os.getenv("ORDERS_URL", "http://orders:8080")
PRODUCTS = ["keyboard", "monitor", "desk-lamp", "notebook", "webcam"]

app, logger = create_observed_app(SERVICE_NAME)


@app.get("/")
async def index():
    return {
        "service": SERVICE_NAME,
        "routes": ["/checkout", "/health", "/metrics"],
        "orders_url": ORDERS_URL,
    }


@app.get("/checkout")
async def checkout(user_id: str | None = None, product_id: str | None = None, quantity: int = 1):
    await jitter(10, 60)
    user_id = user_id or f"user-{random.randint(1000, 9999)}"
    product_id = product_id or random.choice(PRODUCTS)
    order_id = str(uuid.uuid4())

    span = trace.get_current_span()
    span.set_attribute("app.order_id", order_id)
    span.set_attribute("app.product_id", product_id)

    payload = {
        "order_id": order_id,
        "user_id": user_id,
        "product_id": product_id,
        "quantity": quantity,
    }
    response = await call_json("POST", f"{ORDERS_URL}/orders", "orders.create", payload)
    body = response.json()

    log_event(
        logger,
        logging.INFO if response.status_code < 500 else logging.WARNING,
        "checkout_completed",
        order_id=order_id,
        user_id=user_id,
        product_id=product_id,
        status_code=response.status_code,
    )
    return JSONResponse(status_code=response.status_code, content=body)
