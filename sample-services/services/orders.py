import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from opentelemetry import trace

from src.observability import call_json, create_observed_app, jitter, log_event


SERVICE_NAME = os.getenv("SERVICE_NAME", "orders")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://inventory:8080")
PAYMENTS_URL = os.getenv("PAYMENTS_URL", "http://payments:8080")

app, logger = create_observed_app(SERVICE_NAME)


@app.post("/orders")
async def create_order(request: Request):
    payload = await request.json()
    order_id = payload["order_id"]
    product_id = payload["product_id"]
    quantity = int(payload.get("quantity", 1))
    await jitter(20, 90)

    trace.get_current_span().set_attribute("app.order_id", order_id)

    inventory_response = await call_json(
        "POST",
        f"{INVENTORY_URL}/reserve",
        "inventory.reserve",
        {"order_id": order_id, "product_id": product_id, "quantity": quantity},
    )
    if inventory_response.status_code >= 400:
        log_event(
            logger,
            logging.WARNING,
            "order_rejected_inventory",
            order_id=order_id,
            product_id=product_id,
            status_code=inventory_response.status_code,
        )
        return JSONResponse(
            status_code=409,
            content={
                "order_id": order_id,
                "status": "rejected",
                "reason": "inventory_unavailable",
                "inventory": inventory_response.json(),
            },
        )

    payment_response = await call_json(
        "POST",
        f"{PAYMENTS_URL}/charge",
        "payments.charge",
        {"order_id": order_id, "amount": round(19.99 * quantity, 2), "currency": "USD"},
    )
    if payment_response.status_code >= 400:
        log_event(
            logger,
            logging.ERROR,
            "order_failed_payment",
            order_id=order_id,
            status_code=payment_response.status_code,
        )
        return JSONResponse(
            status_code=502,
            content={
                "order_id": order_id,
                "status": "failed",
                "reason": "payment_failed",
                "payment": payment_response.json(),
            },
        )

    log_event(logger, logging.INFO, "order_accepted", order_id=order_id, product_id=product_id)
    return {
        "order_id": order_id,
        "status": "accepted",
        "inventory": inventory_response.json(),
        "payment": payment_response.json(),
    }
