import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry._logs import set_logger_provider
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST


DB_PATH = Path(os.getenv("ORDER_DB_PATH", "data/orders.db"))
STATUSES = {"received", "preparing", "shipped", "delivered"}

resource = Resource.create({"service.name": "order-tracker"})

# Configure exporters based on environment
otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
if otel_endpoint:
    # Use OTLP gRPC exporter for collector + console for debugging
    trace_exporter = OTLPSpanExporter(endpoint=otel_endpoint, insecure=True)
    metric_exporter = OTLPMetricExporter(endpoint=otel_endpoint, insecure=True)
    log_exporter = OTLPLogExporter(endpoint=otel_endpoint, insecure=True)
    # Add console exporter for debugging
    console_metric_exporter = ConsoleMetricExporter()
else:
    # Local development - export to console
    trace_exporter = ConsoleSpanExporter()
    metric_exporter = ConsoleMetricExporter()
    log_exporter = ConsoleLogExporter()
    console_metric_exporter = ConsoleMetricExporter()

trace_provider = TracerProvider(resource=resource)
trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
trace.set_tracer_provider(trace_provider)

metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=30000)
console_metric_reader = PeriodicExportingMetricReader(console_metric_exporter, export_interval_millis=10000)
meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader, console_metric_reader])
metrics.set_meter_provider(meter_provider)
metrics.set_meter_provider(meter_provider)

logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
set_logger_provider(logger_provider)
logging_handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
logging.getLogger().addHandler(logging_handler)
logging.getLogger().setLevel(logging.INFO)

meter = metrics.get_meter("order-tracker")
order_lookup_requests = meter.create_counter(
    "order_tracker_order_lookup_requests_total",
    description="Total number of order lookup requests",
    unit="1",
)
order_lookup_duration = meter.create_histogram(
    "order_tracker_order_lookup_duration_seconds",
    description="Duration of order lookup requests",
    unit="s",
)

# Prometheus metrics for /metrics endpoint
prom_order_lookup_requests = Counter(
    "order_tracker_order_lookup_requests_total",
    "Total number of order lookup requests",
    ["route", "status_code"],
)
prom_order_lookup_duration = Histogram(
    "order_tracker_order_lookup_duration_seconds",
    "Duration of order lookup requests",
    ["route", "status_code"],
)

SQLite3Instrumentor().instrument()


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                customer TEXT NOT NULL,
                item TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        if db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0:
            now = datetime.now(timezone.utc)
            previous_month_end = now.replace(day=1) - timedelta(days=1)
            for order in (
                ("standard-1001", "Avery", "Notebook", "standard", "received", now),
                ("express-1002", "Sam", "Headphones", "express", "preparing", previous_month_end),
                ("standard-1003", "Riley", "Water bottle", "standard", "shipped", now),
            ):
                db.execute(
                    "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
                    (*order[:5], order[5].isoformat()),
                )


def as_dict(row):
    return dict(row) if row else None


def order_detail(row):
    order = as_dict(row)
    if order["priority"] == "express":
        placed_at = datetime.fromisoformat(order["created_at"])
        estimated_at = placed_at + timedelta(days=2)
        order["estimated_delivery"] = estimated_at.date().isoformat()
    return order


class NewOrder(BaseModel):
    customer: str = Field(min_length=1, max_length=80)
    item: str = Field(min_length=1, max_length=120)
    priority: str = "standard"


class StatusUpdate(BaseModel):
    status: str


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Order Tracker", lifespan=lifespan)

FastAPIInstrumentor.instrument_app(app)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.middleware("http")
async def record_request_metrics(request: Request, call_next):
    start_time = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", None) or request.url.path
        if path != "/metrics":
            duration = time.perf_counter() - start_time
            attributes = {"route": path, "status_code": str(status_code)}
            order_lookup_requests.add(1, attributes)
            order_lookup_duration.record(duration, attributes)
            prom_order_lookup_requests.labels(**attributes).inc()
            prom_order_lookup_duration.labels(**attributes).observe(duration)


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent.parent / "static" / "index.html")


@app.get("/healthz")
def health():
    with connect() as db:
        db.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/api/orders")
def list_orders():
    with connect() as db:
        rows = db.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    return [as_dict(row) for row in rows]


@app.get("/api/orders/{order_id}")
def get_order(order_id: str, test_error: str = None):
    logger = logging.getLogger(__name__)
    if test_error == "500":
        raise Exception("Test 500 error for alert testing")
    logger.info("Looking up order", extra={"order_id": order_id})
    with connect() as db:
        row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        logger.warning("Order not found", extra={"order_id": order_id})
        raise HTTPException(404, "Order not found")
    logger.info("Order found", extra={"order_id": order_id, "customer": row["customer"]})
    return order_detail(row)


@app.post("/api/orders", status_code=201)
def create_order(order: NewOrder):
    if order.priority not in {"standard", "express"}:
        raise HTTPException(422, "Priority must be standard or express")
    order_id = str(uuid4())
    with connect() as db:
        db.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, order.customer, order.item, order.priority, "received",
             datetime.now(timezone.utc).isoformat()),
        )
    return get_order(order_id)


@app.patch("/api/orders/{order_id}")
def update_status(order_id: str, update: StatusUpdate):
    if update.status not in STATUSES:
        raise HTTPException(422, "Invalid status")
    with connect() as db:
        cursor = db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (update.status, order_id),
        )
    if cursor.rowcount == 0:
        raise HTTPException(404, "Order not found")
    return get_order(order_id)


@app.get("/test/500")
def test_500():
    raise Exception("Test 500 error for alert testing")
