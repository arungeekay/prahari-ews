"""Shared FastAPI plumbing: a factory that adds /api/health, permissive CORS (evaluators click
straight in), and mounts the built React frontend as static files served by FastAPI (§8.3)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def create_app(title: str, product: str, frontend_dir: str | None = None) -> FastAPI:
    app = FastAPI(title=title)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.product = product

    @app.get("/api/health")
    def health():
        # llm = "active" when a real LLM (Anthropic key) is wired; "template" = deterministic fallback
        try:
            from ..llm import using_llm
            llm = "active" if using_llm() else "template"
        except Exception:
            llm = "template"
        return {"status": "ok", "product": product, "llm": llm}

    return app


def register_warmup(app: FastAPI, product: str) -> None:
    """On startup, build the bundle and warm its heavy serving tables in a background thread so
    /api/health responds immediately (keep-alive) while the first real click loads instantly."""
    import threading

    @app.on_event("startup")
    def _warm():
        from .bundle import get_bundle
        bundle = get_bundle()                       # load data + models (fast)
        threading.Thread(target=lambda: bundle.warm(product), daemon=True).start()


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
