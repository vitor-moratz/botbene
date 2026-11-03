from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.broker.base import Broker
from app.config import BACKEND_DIR, Settings, get_settings
from app.db.database import Database
from app.service.bot import BotService
from app.service.broker_factory import iq_broker_factory
from app.research.dataset import research_db
from app.service.archiver import ResearchArchiver
from app.service.config_store import ConfigStore
from app.service.events import EventHub
from app.service.resolver import PendingResolver

FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
log = logging.getLogger(__name__)


def _ui_version(frontend_dir: Path) -> str:
    """Muda sempre que algum arquivo do painel muda (o painel compara e recarrega sozinho)."""
    if not frontend_dir.exists():
        return "0"
    return str(int(max((p.stat().st_mtime for p in frontend_dir.iterdir() if p.is_file()), default=0)))


def create_app(
    settings: Settings | None = None,
    broker_factory: Callable[[], Broker] | None = None,
    db: Database | None = None,
    frontend_dir: Path = FRONTEND_DIR,
    allow_shutdown: bool = True,
    start_resolver: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    db = db or Database(settings.db_url())
    hub = EventHub()
    config = ConfigStore(settings.resolved_data_dir() / "config.json", settings.iq_email, settings.iq_password)
    bot = BotService(settings, db, hub, broker_factory or iq_broker_factory(settings, config), config=config)
    resolver = PendingResolver(db, bot.shared_broker, hub)
    archiver = ResearchArchiver(research_db(settings), bot.shared_broker, config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        hub.bind_loop(asyncio.get_running_loop())
        if start_resolver:
            resolver.start()
            archiver.start()
        yield
        resolver.stop()
        archiver.stop()
        bot.stop(wait=5)

    app = FastAPI(title="BotBene", version="0.3.0", lifespan=lifespan)
    app.state.bot, app.state.db, app.state.hub, app.state.config = bot, db, hub, config
    app.state.allow_shutdown = allow_shutdown
    app.state.resolver = resolver
    app.state.ui_version = lambda: _ui_version(frontend_dir)  # lido a cada status: vale mesmo sem reiniciar
    app.include_router(router)

    @app.middleware("http")
    async def no_cache_for_panel(request, call_next):
        # A janela do programa não pode ficar com uma versão velha do painel guardada.
        response = await call_next(request)
        if not request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.websocket("/ws/live")
    async def live(ws: WebSocket) -> None:
        await ws.accept()
        queue = hub.subscribe()
        try:
            await ws.send_json({"type": "status", **bot.snapshot()})
            while True:
                await ws.send_json(await queue.get())
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001 - navegador fechou no meio do envio
            log.debug("WebSocket encerrado", exc_info=True)
        finally:
            hub.unsubscribe(queue)

    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="painel")
    return app
