import logging
import os
import random
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from src.observability import create_observed_app, env_float, jitter, log_event


SERVICE_NAME = os.getenv("SERVICE_NAME", "inventory")
LOW_STOCK_RATE = env_float("INVENTORY_LOW_STOCK_RATE", 0.10)

app, logger = create_observed_app(SERVICE_NAME)


@app.post("/reserve")
async def reserve(request: Request):
    payload = await request.json()
    await jitter(15, 120)

    if random.random() < LOW_STOCK_RATE:
        log_event(
            logger,
            logging.WARNING,
            "inventory_low_stock",
            order_id=payload.get("order_id"),
            product_id=payload.get("product_id"),
        )
        return JSONResponse(
            status_code=409,
            content={
                "status": "rejected",
                "reason": "low_stock",
                "product_id": payload.get("product_id"),
            },
        )

    reservation_id = str(uuid.uuid4())
    log_event(
        logger,
        logging.INFO,
        "inventory_reserved",
        order_id=payload.get("order_id"),
        reservation_id=reservation_id,
        product_id=payload.get("product_id"),
    )
    return {
        "status": "reserved",
        "reservation_id": reservation_id,
        "product_id": payload.get("product_id"),
        "quantity": payload.get("quantity", 1),
    }
