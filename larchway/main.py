"""Application factory and ASGI entry point (``uvicorn larchway.main:app``)."""
from __future__ import annotations

import importlib
import pkgutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from . import domain, routers
from .adapters.fs import prepare_data_dir
from .db import connect, init_schema
from .pages import templates
from .seed import seed
from .settings import Settings


def load_package(package) -> list:
    """Import every module in ``package``, in name order."""
    names = sorted(info.name for info in pkgutil.iter_modules(package.__path__))
    return [importlib.import_module(f"{package.__name__}.{name}") for name in names]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    prepare_data_dir(settings)
    conn = connect(settings.database_path)
    try:
        init_schema(conn)
        seed(conn)
        from .domain.addons import load_active_addons

        load_active_addons(conn, settings)
    finally:
        conn.close()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Larchway", debug=settings.debug, lifespan=lifespan)
    app.state.settings = settings

    load_package(domain)
    for module in load_package(routers):
        if hasattr(module, "router"):
            app.include_router(module.router)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        return templates.TemplateResponse(request, "home.html")

    return app


app = create_app()
