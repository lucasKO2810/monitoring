# Distributed Observability Stack

A local observability lab for distributed systems, inspired by Raghuraj Singh Solanki's Medium article on a complete OpenTelemetry, Prometheus, Grafana, Loki, Promtail, Node Exporter, and Alertmanager stack:

https://medium.com/@raghurajs212/building-a-complete-observability-monitoring-stack-opentelemetry-prometheus-grafana-loki-d988827ec1cc

This project adds a runnable sample distributed system and keeps it on a separate Docker network while still allowing telemetry to flow into the monitoring stack.

## What Runs

Monitoring stack on `observability-net`:

- OpenTelemetry Collector receives OTLP traces and metrics.
- Tempo stores traces for Grafana.
- Prometheus scrapes service, collector, Loki, Tempo, and node metrics.
- Loki stores Docker container logs collected by Promtail.
- Grafana is pre-provisioned with Prometheus, Loki, Tempo, and a starter dashboard.
- Alertmanager receives Prometheus alerts.
- Node Exporter exposes local system metrics from inside the Docker environment.

Sample distributed system on `distributed-sample-net`:

- `frontend` exposes `GET /checkout` on `http://localhost:8080`.
- `orders` coordinates inventory reservation and payment capture.
- `inventory` randomly rejects some reservations to create realistic non-5xx failures.
- `payments` randomly emits provider failures so traces, logs, metrics, and alerts have useful data.
- `load-generator` continuously calls the frontend.

Each sample service joins both networks: it talks to peer services over `distributed-sample-net`, and it reaches `otel-collector` plus Prometheus scraping over `observability-net`.

## Start

```bash
cp .env.example .env
docker compose up --build -d
```

Open:

- Grafana: http://localhost:3000, login `admin` / `admin` unless changed in `.env`
- Frontend: http://localhost:8080/checkout
- Prometheus: http://localhost:9090
- Alertmanager: http://localhost:9093
- Loki: http://localhost:3100
- Tempo: http://localhost:3200

Generate one manual request:

```bash
curl "http://localhost:8080/checkout?user_id=lucas&product_id=keyboard&quantity=1"
```

## Useful Queries

Prometheus:

```promql
sum by (service) (rate(http_requests_total{job="sample-services"}[1m]))
histogram_quantile(0.95, sum by (le, service) (rate(http_request_duration_seconds_bucket{job="sample-services"}[5m])))
sum by (service) (rate(http_requests_total{job="sample-services", status_code=~"5.."}[2m]))
```

Loki:

```logql
{compose_project="distributed-observability", service=~"frontend|orders|inventory|payments|load-generator"}
```

Grafana:

- Dashboard: `Distributed Observability / Distributed Services Overview`
- Explore Prometheus for metrics.
- Explore Loki for logs.
- Explore Tempo for traces and service-to-service spans.

## Scale The Sample System

The sample services avoid fixed container names, and Prometheus uses Docker DNS discovery, so replicas can be added:

```bash
docker compose up -d --scale orders=3 --scale payments=2
```

## Connect Another Compose Project

Create the observability stack first so Docker creates `observability-net`. Then attach any other app compose file to that external network:

```yaml
services:
  my-api:
    image: my-api:local
    networks:
      - app-private
      - observability
    environment:
      OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: http://otel-collector:4318/v1/traces

networks:
  app-private:
  observability:
    external: true
    name: observability-net
```

For Prometheus scraping, expose a `/metrics` endpoint from your service and add it to `config/prometheus/prometheus.yml`. For logs, Promtail discovers Docker containers through the Docker socket and labels logs with the Compose service name.

## Alerting

Starter alerts live in `config/prometheus/alert-rules.yml`:

- service scrape target down
- high service 5xx rate (warning >10%, critical >25%)
- high p95 / p99 latency
- SLO burn rate alerts (1h and 6h windows for /checkout)
- infrastructure alerts (CPU, memory, observability stack down)

`config/alertmanager/alertmanager.yml` routes critical and warning alerts to separate receivers with inhibit rules. Add Slack, PagerDuty, email, or webhook receiver config there when you are ready to send real alerts.

## Dashboards

Seven production-style Grafana dashboards are provisioned automatically:

| # | Dashboard | Purpose |
|---|-----------|---------|
| 1 | Global Overview | System health, active alerts, traffic, error rate, P95 latency, service health |
| 2 | Service Detail | Per-service RED metrics, route breakdown, status codes, logs (service selector) |
| 3 | SLO / Error Budget | Checkout 99.9% SLO, error budget remaining, 1h/6h burn rates, per-service availability |
| 4 | Distributed Tracing | Trace search, dependency chain latency, failed request volume, error logs with trace links |
| 5 | Logs Explorer | Log volume, error/warning trends, service+level filters, trace ID search |
| 6 | Infrastructure | Host CPU/memory/disk/network, observability stack health, Prometheus scrape stats |
| 7 | Alerting Overview | Firing/pending alerts, alert timeline, breakdown by severity and service |

All dashboards cross-link via the top navigation bar.

## Resource Requirements

The monitoring stack has the following resource limits configured:

| Component | CPU Limit | Memory Limit | Memory Reserved | Disk |
|---|---|---|---|---|
| Prometheus | 1.0 | 1 GB | 512 MB | 5 GB (15-day retention) |
| Loki | 1.0 | 1 GB | 256 MB | ~2–5 GB (14-day retention) |
| Tempo | 1.0 | 1 GB | 256 MB | ~1–3 GB (72h retention) |
| Grafana | 1.0 | 512 MB | 128 MB | ~100 MB |
| OTel Collector | 1.0 | 512 MB | 128 MB | — (stateless) |
| Promtail | 0.5 | 256 MB | 64 MB | ~1 MB |
| Alertmanager | 0.25 | 128 MB | 64 MB | ~50 MB |
| Node Exporter | 0.25 | 128 MB | 32 MB | — (stateless) |
| **Totals** | **6.0** | **4.5 GB** | **1.4 GB** | **~8–13 GB** |

Minimum host: **4 CPU cores, 8 GB RAM** (including sample services), **20 GB disk**.

Under light load (~1–2 req/s), the stack typically idles at ~0.5 CPU and ~1–1.5 GB RAM. The limits provide headroom for query spikes, compaction, and burst ingestion.

## Stop

```bash
docker compose down
```

Remove persisted Grafana, Prometheus, Loki, Tempo, and Alertmanager data:

```bash
docker compose down -v
```
