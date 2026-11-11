"""Local HTTP server: JSON API plus the bundled single-page frontend."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from importlib import resources
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, api


class _FreshStatic(StaticFiles):
    """The bundled page, scripts and styles are revalidated on every load (a cheap 304 when unchanged), so an update or an edit during development never shows stale code; the large vendored libraries may be cached for a day."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=86400" if path.startswith("vendor/") else "no-cache"
        return response


class SolveRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict, description='{"F": "250 kN"} or {"F": {"value": 250, "unit": "kN"}}')
    solve_for: list[str] | None = None
    output_units: dict[str, str] = Field(default_factory=dict)
    sig_figs: int = 5
    search: dict[str, list[Any]] | None = Field(default=None, description='range [lo, hi] in which to look for a variable that must be found numerically, e.g. {"k": ["0.001 1/s", "1 1/s"]}')
    ode_times: list[Any] | None = Field(default=None, description='for differential equations: extra times to tabulate, e.g. ["10 s", "20 s"]')


class RpcRequest(BaseModel):
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ApiGuard:
    """Protection for a server that other programs on this computer are meant to call at a known address.

    * ``Host`` must be a loopback name, which defeats DNS rebinding (a web page cannot make the browser talk to this server under its own name).
    * A request carrying an ``Origin`` header (that is, one sent by a web page) is refused unless the origin is this server's own or listed in ``origins``,
      which stops other sites from making the browser send requests here. Programs that are not browsers send no ``Origin``.
    * With a ``token``, every request except the public API description needs ``Authorization: Bearer <token>``.
    * Origins that are listed also get the CORS headers a browser needs to read the answers.
    """

    token: str | None = None
    origins: tuple[str, ...] = ()
    any_host: bool = False          # a server deliberately bound to a network address (``serve --host 0.0.0.0``) is reached under other names: skip the Host check, keep the rest


_LOOPBACK = {"127.0.0.1", "localhost", "[::1]", "::1"}


def bound_to_loopback(host: str) -> bool:
    """True when a server started with ``--host host`` is reachable from this computer only."""
    return host.strip().lower() in _LOOPBACK
_PUBLIC_PATHS = {"/api/docs", "/api/openapi.json"}


def _host_name(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):
        return host.split("]")[0] + "]"
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def create_app(serve_frontend: bool = True, guard: ApiGuard | None = None) -> FastAPI:
    app = FastAPI(title="SlideRule", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")

    if guard is not None:
        @app.middleware("http")
        async def guarded(request: Request, call_next):
            host = request.headers.get("host", "")
            if not guard.any_host and _host_name(host) not in _LOOPBACK:
                return JSONResponse({"detail": {"code": "BAD_HOST", "message": "this server only answers to localhost, 127.0.0.1 or [::1]"}}, status_code=403)
            origin = request.headers.get("origin")
            if origin is not None and origin not in guard.origins and origin != f"http://{host}":
                return JSONResponse({"detail": {"code": "BAD_ORIGIN", "message": "requests from web pages are only accepted from origins allowed with --api-origin"}}, status_code=403)
            if guard.token and request.url.path not in _PUBLIC_PATHS:
                given = request.headers.get("authorization", "")
                if not hmac.compare_digest(given.encode(), f"Bearer {guard.token}".encode()):
                    return JSONResponse({"detail": {"code": "UNAUTHORIZED", "message": "send the header  Authorization: Bearer <token>"}}, status_code=401,
                                        headers={"WWW-Authenticate": "Bearer"})
            return await call_next(request)

        if guard.origins:                       # added last, so it is outermost and answers browser preflights and decorates the 401/403 replies
            app.add_middleware(CORSMiddleware, allow_origins=list(guard.origins), allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except api.ApiError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": exc.message, "details": getattr(exc, "details", None)}) from None

    @app.get("/api/meta")
    def meta():
        return api.meta()

    @app.get("/api/calculations")
    def calculations(q: str = "", discipline: list[str] = Query(default=[]), variable: list[str] = Query(default=[]),
                     solves_for: list[str] = Query(default=[]), subdiscipline: list[str] = Query(default=[]), level: str = "", ids: list[str] | None = Query(default=None), basic: list[str] | None = Query(default=None)):
        return call(api.list_calculations, q, discipline, variable, solves_for, subdiscipline, "", level, ids, basic)

    @app.get("/api/calculations/{calc_id}")
    def calculation(calc_id: str):
        return call(api.get_calculation, calc_id)

    @app.get("/api/lists")
    def lists_get():
        return call(api.lists_get)

    @app.put("/api/lists")
    def lists_put(body: dict):
        return call(api.lists_set, body)

    @app.post("/api/calculations/{calc_id}/sweep")
    def sweep(calc_id: str, body: dict):
        return call(api.sweep, calc_id, body.get("inputs", {}), body.get("vary", ""), body.get("values", []), body.get("solve_for"), body.get("output_units"), int(body.get("sig_figs", 5)))

    @app.post("/api/calculations/{calc_id}/solve")
    def solve(calc_id: str, body: SolveRequest):
        return call(api.solve, calc_id, body.inputs, body.solve_for, body.output_units, body.sig_figs, body.ode_times, body.search)

    @app.get("/api/convert")
    def convert(value: float, from_unit: str = Query(alias="from"), to_unit: str = Query(alias="to"), sig_figs: int = 6):
        res = api.convert(value, from_unit, to_unit, sig_figs)
        if not res["ok"]:
            raise HTTPException(422, res)
        return res

    @app.get("/api/unit")
    def unit(expr: str, as_delta: bool = False):
        return api.parse_unit_expr(expr, as_delta)

    @app.get("/api/kinds")
    def kinds():
        return api.kinds_catalog()

    @app.get("/api/vocabulary")
    def vocabulary():
        return api.variable_vocabulary()

    @app.post("/api/design/check")
    def design_check(body: dict):
        return call(api.design_check_block, body.get("calc_id", ""), body.get("roles"))

    @app.post("/api/design/solve")
    def design_solve(body: dict):
        return call(api.design_solve, body.get("graph", body), int(body.get("sig_figs", 5)))

    @app.post("/api/design/validate")
    def design_validate(body: dict):
        return call(api.design_validate, body.get("graph", body))

    @app.post("/api/design/export")
    def design_export(body: dict):
        """Body: {graph, format: latex|markdown|html|python|matlab|excel, mode: both|symbolic|numeric, sig_figs, standalone}. Excel returns {binary: true, content_base64}."""
        return call(api.design_export_document, body.get("graph", {}), body.get("format", "latex"), body.get("mode", "both"),
                    int(body.get("sig_figs", 5)), bool(body.get("standalone", True)))

    @app.get("/api/design/examples")
    def design_examples():
        return api.design_examples()

    @app.get("/api/data")
    def data_packs():
        return api.data_packs()

    @app.get("/api/data/search")
    def data_search(q: str = "", pack: str = "", category: str = ""):
        return api.data_search(q, pack, category)

    @app.get("/api/data/{pack}/{record_id}/{prop}")
    def data_value(pack: str, record_id: str, prop: str, x: float | None = None, x_unit: str = "K", unit: str | None = None):
        return call(api.data_value, pack, record_id, prop, x, x_unit, unit)

    @app.get("/api/data/{pack}/{record_id}")
    def data_record(pack: str, record_id: str):
        return call(api.data_record, pack, record_id)

    @app.get("/api/custom")
    def custom_list():
        return api.custom_list()

    @app.post("/api/custom/validate")
    def custom_validate(body: dict):
        return call(api.custom_validate, body.get("calculation", body))

    @app.post("/api/custom")
    def custom_save(body: dict):
        """Body: {calculation, replace?}. 409 if the id exists and replace is not set."""
        return call(api.custom_save, body.get("calculation", body), bool(body.get("replace", False)))

    @app.delete("/api/custom/{calc_id}")
    def custom_delete(calc_id: str):
        return call(api.custom_delete, calc_id)

    @app.post("/api/custom/import")
    def custom_import(body: dict):
        """Body: {document, on_conflict: rename|replace|skip|ask, dry_run?}."""
        return call(api.custom_import, body.get("document"), body.get("on_conflict", "rename"), bool(body.get("dry_run", False)))

    @app.get("/api/custom/export")
    def custom_export(id: list[str] = Query(default=[])):
        return api.custom_export(id or None)

    @app.get("/api/settings")
    def settings_get():
        return api.settings_get()

    @app.put("/api/settings")
    def settings_set(body: dict):
        """Body: {timeout_enabled?, timeout_seconds?, acknowledge_risk?}. Switching the limit off needs acknowledge_risk (409 otherwise)."""
        return call(api.settings_set, body.get("timeout_enabled"), body.get("timeout_seconds"), bool(body.get("acknowledge_risk", False)))

    @app.post("/api/rpc")
    def rpc(body: RpcRequest):
        """Same envelope the in-browser (Pyodide) engine uses, so the frontend has one code path."""
        return JSONResponse(api.handle(body.method, body.params))

    if serve_frontend:
        web = resources.files("sliderule") / "web"
        app.mount("/", _FreshStatic(directory=str(web), html=True), name="web")
    return app
