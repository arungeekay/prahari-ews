"""Shared FastAPI plumbing: a factory that adds /api/health, permissive CORS (evaluators click
straight in), and mounts the built React frontend as static files served by FastAPI (§8.3).

Startup never blocks the listener: the bundle (data + models) loads in a background thread and
/api/health answers immediately with status "warming" until it is resident. Health reports the
narrative provider that is ACTUALLY usable (SDK importable and key present), the data source and
its provenance, so a silent degradation is visible."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_STATE = {"bundle_ready": False, "error": None}


def _llm_status() -> dict:
    """Configured provider vs whether its SDK actually imports (the docker image once lacked it)."""
    try:
        from ..llm import active_provider
        configured = active_provider()
    except Exception:
        configured = "template"
    usable = configured
    if configured == "anthropic":
        try:
            import anthropic  # noqa: F401
        except Exception:
            usable = "template"
    elif configured == "openai":
        try:
            import openai  # noqa: F401
        except Exception:
            usable = "template"
    return dict(configured=configured, usable=usable, degraded=(usable != configured))


def create_app(title: str, product: str, frontend_dir: str | None = None) -> FastAPI:
    app = FastAPI(title=title)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.product = product

    @app.get("/api/health")
    def health():
        llm = _llm_status()
        out = {"status": "ok" if _STATE["bundle_ready"] else ("error" if _STATE["error"] else "warming"),
               "product": product, "llm": llm["usable"], "llm_detail": llm}
        if _STATE["bundle_ready"]:
            try:
                from .bundle import get_bundle
                out["data_source"] = get_bundle().provenance
            except Exception:
                pass
        if _STATE["error"]:
            out["error"] = _STATE["error"]
        return out

    return app


def register_warmup(app: FastAPI, product: str) -> None:
    """On startup, load the bundle and warm its heavy serving tables in a background thread so the
    listener accepts connections immediately; /api/health says 'warming' until ready."""

    def _load():
        try:
            from .bundle import get_bundle
            bundle = get_bundle()
            bundle.warm(product)                 # heavy tables built once, under the bundle lock
            _STATE["bundle_ready"] = True        # health says "warming" until the first click is instant
        except Exception as e:  # pragma: no cover - surfaced through /api/health
            _STATE["error"] = f"{type(e).__name__}: {e}"

    @app.on_event("startup")
    def _warm():
        if os.environ.get("PRAHARI_SYNC_BOOT") == "1":
            _load()
        else:
            threading.Thread(target=_load, daemon=True).start()


def mount_frontend(app: FastAPI, frontend_dir: str) -> None:
    """Serve the Vite build (index.html + assets) with SPA fallback. No-op if not built yet."""
    dist = Path(frontend_dir)
    if not (dist / "index.html").exists():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/")
    def _index():
        return FileResponse(dist / "index.html")

    @app.get("/{full_path:path}")
    def _spa(full_path: str):
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
