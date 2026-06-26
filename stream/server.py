"""FastAPI WebSocket server for YouTube Live streaming."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

_broadcaster = None
_price_feed = None
_broadcast_task = None
_health = None
_start_time: datetime | None = None
_paper_trading: bool = True


async def broadcast_loop():
    while True:
        try:
            if _broadcaster:
                await _broadcaster.broadcast()
        except Exception as e:
            logger.error(f"Broadcast error: {e}")
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _broadcast_task
    logger.info("Stream server starting...")
    _broadcast_task = asyncio.create_task(broadcast_loop())
    yield
    logger.info("Stream server shutting down...")
    if _broadcast_task:
        _broadcast_task.cancel()


app = FastAPI(
    title="Trading Agents Live Stream",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        content = await asyncio.to_thread(html_path.read_text, encoding="utf-8")
        return HTMLResponse(content=content)
    return HTMLResponse(content="<h1>Trading Agents Live Stream</h1><p>Dashboard loading...</p>")


@app.get("/api/snapshot")
async def api_snapshot():
    if _broadcaster:
        return JSONResponse(content=_broadcaster.build_snapshot())
    return JSONResponse(content={"error": "Broadcaster not initialized"}, status_code=503)


@app.get("/health")
async def health():
    """Health check endpoint for monitoring (Kubernetes, UptimeRobot, etc.)."""
    if _health is None:
        return JSONResponse({"status": "unknown", "services": {}}, status_code=503)

    health_data = _health.to_dict() if hasattr(_health, "to_dict") else {}
    all_ok = all(health_data.get(k, False) for k in ("llm_available", "broker_available", "db_available") if k in health_data)

    uptime = ""
    if _start_time:
        delta = datetime.now(timezone.utc) - _start_time
        uptime = str(delta).split(".")[0]

    return JSONResponse({
        "status": "ok" if all_ok else "degraded",
        "uptime": uptime,
        "trading_mode": "paper" if _paper_trading else "live",
        "services": {
            "llm": health_data.get("llm_available", False),
            "broker": health_data.get("broker_available", False),
            "db": health_data.get("db_available", False),
        },
        "consecutive_failures": health_data.get("consecutive_failures", {}),
    })


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    data = await asyncio.to_thread(generate_latest)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    if _broadcaster:
        _broadcaster.add_client(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        if _broadcaster:
            _broadcaster.remove_client(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if _broadcaster:
            _broadcaster.remove_client(websocket)


def init_server(broadcaster, price_feed=None, health=None, paper_trading=True, start_time=None):
    global _broadcaster, _price_feed, _health, _start_time, _paper_trading
    _broadcaster = broadcaster
    _price_feed = price_feed
    _health = health
    _paper_trading = paper_trading
    _start_time = start_time or datetime.now(timezone.utc)


def run_server(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    logger.info(f"Starting stream server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()
