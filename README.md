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
- high service 5xx rate
- high p95 latency

`config/alertmanager/alertmanager.yml` intentionally uses a local receiver with no outbound notifications. Add Slack, email, Teams, or webhook receiver config there when you are ready to send real alerts.

## Stop

```bash
docker compose down
```

Remove persisted Grafana, Prometheus, Loki, Tempo, and Alertmanager data:

```bash
docker compose down -v
```
