import asyncio
import logging
import os
import random

from src.observability import call_json, configure_tracing, get_logger, log_event


SERVICE_NAME = os.getenv("SERVICE_NAME", "load-generator")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend:8080")
INTERVAL_SECONDS = float(os.getenv("REQUEST_INTERVAL_SECONDS", "0.75"))
PRODUCTS = ["keyboard", "monitor", "desk-lamp", "notebook", "webcam"]


async def run() -> None:
    configure_tracing(SERVICE_NAME)
    logger = get_logger(SERVICE_NAME)
    counter = 0

    while True:
        counter += 1
        product_id = random.choice(PRODUCTS)
        quantity = random.randint(1, 3)
        user_id = f"synthetic-{random.randint(1, 250)}"
        url = (
            f"{FRONTEND_URL}/checkout"
            f"?user_id={user_id}&product_id={product_id}&quantity={quantity}"
        )

        try:
            response = await call_json("GET", url, "synthetic.checkout", timeout=5.0)
            log_event(
                logger,
                logging.INFO if response.status_code < 500 else logging.WARNING,
                "synthetic_checkout",
                sequence=counter,
                status_code=response.status_code,
                product_id=product_id,
            )
        except Exception as exc:
            log_event(logger, logging.ERROR, "synthetic_checkout_failed", error=str(exc))

        await asyncio.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run())
