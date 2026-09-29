import os
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings

import httpx


class Settings(BaseSettings):
    grafana_url: str = "http://grafana:3000"
    loki_url: str = "http://loki:3100"
    tempo_url: str = "http://tempo:3200"
    prometheus_url: str = "http://prometheus:9090"
    alerts_storage_path: str = "/data/alerts"
    coding_assistant_cmd: str = "python coding_assistant.py"
    coding_assistant_args: str = ""

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

app = FastAPI(title="Incident Response Service", version="0.1.0")

ALERTS_DIR = Path(settings.alerts_storage_path)
ALERTS_DIR.mkdir(parents=True, exist_ok=True)


class AlertmanagerAlert(BaseModel):
    status: str = "firing"
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None
    generatorURL: Optional[str] = None
    fingerprint: Optional[str] = None
    id: Optional[str] = None
    uid: Optional[str] = None
    orgID: Optional[int] = None
    folderUID: Optional[str] = None
    ruleGroup: Optional[str] = None
    title: Optional[str] = None
    condition: Optional[str] = None
    data: Optional[list[dict[str, Any]]] = None
    updated: Optional[str] = None
    noDataState: Optional[str] = None
    execErrState: Optional[str] = None
    for_: Optional[str] = Field(default=None, alias="for")
    provenance: Optional[str] = None
    isPaused: Optional[bool] = None


class AlertPayload(BaseModel):
    receiver: Optional[str] = "unknown"
    status: Optional[str] = "firing"
    alerts: list[AlertmanagerAlert]
    groupLabels: Optional[dict[str, str]] = None
    commonLabels: Optional[dict[str, str]] = None
    commonAnnotations: Optional[dict[str, str]] = None
    externalURL: Optional[str] = None
    version: Optional[str] = None
    groupKey: Optional[str] = None
    truncatedAlerts: int = 0

    def model_post_init(self, __context):
        if self.groupLabels is None:
            self.groupLabels = {}
        if self.commonLabels is None:
            self.commonLabels = {}
        if self.commonAnnotations is None:
            self.commonAnnotations = {}


async def fetch_logs_from_loki(endpoint: str, start_time: str, end_time: str) -> list[dict]:
    query = f'{{job="order-tracker", http_target="{endpoint}"}}'
    params = {
        "query": query,
        "start": start_time,
        "end": end_time,
        "limit": 100,
        "direction": "backward"
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{settings.loki_url}/loki/api/v1/query_range", params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("data", {}).get("result", [])
        except Exception:
            pass
    return []


async def fetch_traces_from_tempo(endpoint: str, start_time: str, end_time: str) -> list[dict]:
    query = f'http.target="{endpoint}"'
    params = {
        "q": query,
        "start": start_time,
        "end": end_time,
        "limit": 50
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{settings.tempo_url}/api/search", params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("traces", [])
        except Exception:
            pass
    return []


async def fetch_metrics_from_prometheus(endpoint: str, start_time: str, end_time: str) -> dict:
    queries = {
        "error_rate": f'sum(rate(order_tracker_http_server_duration_milliseconds_count{{job="otel-collector",http_target="{endpoint}",http_status_code=~"5.."}}[5m])) / sum(rate(order_tracker_http_server_duration_milliseconds_count{{job="otel-collector",http_target="{endpoint}"}}[5m]))',
        "latency_p95": f'histogram_quantile(0.95, sum(rate(order_tracker_http_server_duration_milliseconds_bucket{{job="otel-collector",http_target="{endpoint}"}}[5m])) by (le, http_target))',
        "request_rate": f'sum(rate(order_tracker_http_server_duration_milliseconds_count{{job="otel-collector",http_target="{endpoint}"}}[5m])) by (http_status_code)'
    }
    results = {}
    async with httpx.AsyncClient() as client:
        for name, query in queries.items():
            try:
                resp = await client.get(
                    f"{settings.prometheus_url}/api/v1/query",
                    params={"query": query, "time": end_time},
                    timeout=10
                )
                if resp.status_code == 200:
                    results[name] = resp.json().get("data", {}).get("result", [])
            except Exception:
                results[name] = []
    return results


def save_alert_data(alert: AlertmanagerAlert, logs: list, traces: list, metrics: dict) -> Path:
    alert_uid = alert.fingerprint or str(uuid4())
    alert_dir = ALERTS_DIR / alert_uid
    alert_dir.mkdir(parents=True, exist_ok=True)

    alert_info = {
        "alert": alert.model_dump(),
        "logs": logs,
        "traces": traces,
        "metrics": metrics,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }

    alert_file = alert_dir / "alert.json"
    alert_file.write_text(json.dumps(alert_info, indent=2))

    return alert_dir

    return alert_dir


def generate_incident_report(alert_dir: Path, alert: AlertmanagerAlert, logs: list, traces: list, metrics: dict) -> str:
    endpoint = alert.annotations.get("description", "").split("Endpoint**: ")[1].split("\n")[0] if "Endpoint**" in alert.annotations.get("description", "") else "unknown"
    
    report = f"""# Incident Report: {alert.annotations.get("summary", "Unknown Alert")}

**Alert UID**: {alert.fingerprint}
**Status**: {alert.status}
**Received**: {datetime.now(timezone.utc).isoformat()}
**Affected Endpoint**: {endpoint}

## Alert Details
- **Alertname**: {alert.labels.get("alertname", "unknown")}
- **Annotations**: {json.dumps(alert.annotations, indent=2)}
- **Labels**: {json.dumps(alert.labels, indent=2)}

## Metrics at Alert Time
"""
    for name, data in metrics.items():
        report += f"\n### {name}\n```json\n{json.dumps(data, indent=2)}\n```\n"

    report += f"\n## Recent Logs ({len(logs)} entries)\n"
    for log_stream in logs[:5]:
        for value in log_stream.get("values", [])[:3]:
            report += f"- {value[0]}: {value[1]}\n"

    report += f"\n## Related Traces ({len(traces)} traces)\n"
    for trace in traces[:5]:
        report += f"- Trace ID: {trace.get('traceID')}, Duration: {trace.get('durationMs', 'N/A')}ms\n"

    report += f"""
## Recommended Actions
1. Check the dashboard: http://127.0.0.1:3000/d/order-tracker-requests/order-tracker-request-metrics
2. Review traces in Tempo for the affected endpoint
3. Check recent deployments or configuration changes
4. Correlate with logs in Loki

## Files
- Alert data: {alert_dir / "alert.json"}
- This report: {alert_dir / "INCIDENT_REPORT.md"}
"""

    report_file = alert_dir / "INCIDENT_REPORT.md"
    report_file.write_text(report)
    return str(report_file)


async def run_coding_assistant(alert_dir: Path, report_path: str) -> dict:
    prompt = f"""
You are an incident response engineer. An alert has been triggered.

## Incident Report
{Path(report_path).read_text()}

## Alert Data
{Path(alert_dir / "alert.json").read_text()}

Please analyze this incident and provide:
1. Root cause analysis
2. Immediate mitigation steps
3. Long-term fix recommendations
4. Any code changes needed

Output your analysis to {alert_dir / "ANALYSIS.md"}.
"""

    prompt_file = alert_dir / "prompt.txt"
    prompt_file.write_text(prompt)

    # Use absolute path to coding assistant script
    coding_assistant_script = Path("/app/coding_assistant.py")
    cmd = f"{settings.coding_assistant_cmd.split()[0]} {coding_assistant_script} < {prompt_file}"
    
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=str(alert_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        output = f"STDOUT:\n{stdout.decode()}\n\nSTDERR:\n{stderr.decode()}\n"
        (alert_dir / "coding_assistant_output.log").write_text(output)
        
        analysis_file = alert_dir / "ANALYSIS.md"
        analysis = analysis_file.read_text() if analysis_file.exists() else output
        
        return {
            "success": True,
            "output": output,
            "analysis": analysis,
            "returncode": proc.returncode
        }
    except Exception as e:
        error_msg = str(e)
        (alert_dir / "coding_assistant_error.log").write_text(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "output": "",
            "analysis": "",
            "returncode": -1
        }


@app.post("/alerts")
async def receive_alert(payload: AlertPayload):
    results = []
    
    for alert in payload.alerts:
        if alert.status != "firing":
            continue
            
        alert_uid = alert.fingerprint or str(uuid4())
        endpoint = "unknown"
        for key, value in alert.annotations.items():
            if "endpoint" in key.lower() or "endpoint" in value.lower():
                endpoint = value.split("**")[-1].split("\n")[0].strip() if "**" in value else value
                break
        
        end_time = datetime.now(timezone.utc).isoformat()
        start_time = (datetime.now(timezone.utc).replace(second=0, microsecond=0)).isoformat()
        
        logs, traces, metrics = await asyncio.gather(
            fetch_logs_from_loki(endpoint, start_time, end_time),
            fetch_traces_from_tempo(endpoint, start_time, end_time),
            fetch_metrics_from_prometheus(endpoint, start_time, end_time)
        )
        
        alert_dir = save_alert_data(alert, logs, traces, metrics)
        report_path = generate_incident_report(alert_dir, alert, logs, traces, metrics)
        
        # Wait for coding assistant to complete
        coding_result = await run_coding_assistant(alert_dir, report_path)
        
        results.append({
            "alert_uid": alert_uid,
            "endpoint": endpoint,
            "alert_dir": str(alert_dir),
            "report": report_path,
            "coding_assistant": coding_result
        })
    
    return {"status": "received", "processed": len(results), "details": results}


@app.get("/healthz")
async def health():
    return {"status": "ok"}


@app.get("/alerts")
async def list_alerts():
    alerts = []
    for alert_dir in ALERTS_DIR.iterdir():
        if alert_dir.is_dir():
            alert_file = alert_dir / "alert.json"
            if alert_file.exists():
                alerts.append(json.loads(alert_file.read_text()))
    return {"alerts": alerts}


@app.get("/alerts/{alert_uid}")
async def get_alert(alert_uid: str):
    alert_file = ALERTS_DIR / alert_uid / "alert.json"
    if not alert_file.exists():
        raise HTTPException(404, "Alert not found")
    return json.loads(alert_file.read_text())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)