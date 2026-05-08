import logging
import os
import random
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from src.observability import create_observed_app, env_float, jitter, log_event


SERVICE_NAME = os.getenv("SERVICE_NAME", "payments")
FAILURE_RATE = env_float("PAYMENT_FAILURE_RATE", 0.08)

app, logger = create_observed_app(SERVICE_NAME)


@app.post("/charge")
async def charge(request: Request):
    payload = await request.json()
    await jitter(30, 180)

    if random.random() < FAILURE_RATE:
        log_event(
            logger,
            logging.ERROR,
            "payment_provider_failed",
            order_id=payload.get("order_id"),
            amount=payload.get("amount"),
        )
        return JSONResponse(
            status_code=503,
            content={
                "status": "failed",
                "reason": "payment_provider_unavailable",
                "order_id": payload.get("order_id"),
            },
        )

    payment_id = str(uuid.uuid4())
    log_event(
        logger,
        logging.INFO,
        "payment_captured",
        order_id=payload.get("order_id"),
        payment_id=payment_id,
        amount=payload.get("amount"),
    )
    return {
        "status": "captured",
        "payment_id": payment_id,
        "amount": payload.get("amount"),
        "currency": payload.get("currency", "USD"),
    }
