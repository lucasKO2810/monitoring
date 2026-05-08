import asyncio
import json
import logging
import os
import random
import time
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests handled by the service.",
    ["service", "method", "route", "status_code"],
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["service", "method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0),
)
HTTP_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "Current in-flight HTTP requests.",
    ["service"],
)


class JsonLogFormatter(logging.Formatter):
    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "service": self.service_name,
            "message": record.getMessage(),
        }

        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            payload["trace_id"] = f"{span_context.trace_id:032x}"
            payload["span_id"] = f"{span_context.span_id:016x}"

        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_tracing(service_name: str) -> None:
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": os.getenv("OTEL_SERVICE_NAMESPACE", "sample-commerce"),
            "deployment.environment": os.getenv("DEPLOYMENT_ENVIRONMENT", "local"),
        }
    )
    provider = TracerProvider(resource=resource)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))

    trace.set_tracer_provider(provider)


def get_logger(service_name: str) -> logging.Logger:
    logger = logging.getLogger(service_name)
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter(service_name))
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    logger.log(level, message, extra={"extra_fields": fields})


def create_observed_app(service_name: str) -> tuple[FastAPI, logging.Logger]:
    configure_tracing(service_name)
    logger = get_logger(service_name)
    app = FastAPI(title=f"{service_name} service")
    tracer = trace.get_tracer(service_name)

    @app.middleware("http")
    async def observe_request(request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        route = request.url.path
        headers = dict(request.headers)
        context = propagate.extract(headers)
        start = time.perf_counter()
        status_code = 500
        HTTP_IN_FLIGHT.labels(service=service_name).inc()

        with tracer.start_as_current_span(
            f"{request.method} {route}",
            context=context,
            kind=SpanKind.SERVER,
        ) as span:
            span.set_attribute("http.request.method", request.method)
            span.set_attribute("url.path", route)
            try:
                response = await call_next(request)
                status_code = response.status_code
                span.set_attribute("http.response.status_code", status_code)
                if status_code >= 500:
                    span.set_status(Status(StatusCode.ERROR))
                return response
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                log_event(logger, logging.ERROR, "request_failed", path=route, error=str(exc))
                raise
            finally:
                elapsed = time.perf_counter() - start
                HTTP_IN_FLIGHT.labels(service=service_name).dec()
                HTTP_REQUESTS.labels(
                    service=service_name,
                    method=request.method,
                    route=route,
                    status_code=str(status_code),
                ).inc()
                HTTP_LATENCY.labels(
                    service=service_name,
                    method=request.method,
                    route=route,
                ).observe(elapsed)

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok", "service": service_name}

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app, logger


async def call_json(
    method: str,
    url: str,
    operation: str,
    json_body: dict[str, Any] | None = None,
    timeout: float = 3.0,
) -> httpx.Response:
    service_name = os.getenv("SERVICE_NAME", "sample-service")
    tracer = trace.get_tracer(service_name)
    method = method.upper()

    with tracer.start_as_current_span(operation, kind=SpanKind.CLIENT) as span:
        headers: dict[str, str] = {}
        propagate.inject(headers)
        span.set_attribute("http.request.method", method)
        span.set_attribute("url.full", url)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, json=json_body, headers=headers)
            span.set_attribute("http.response.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
            return response
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


async def jitter(min_ms: int, max_ms: int) -> None:
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default
