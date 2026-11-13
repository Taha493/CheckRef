"""The public web app (plan phase 10): upload → queue → progress → report → downloads.

Run with `checkref serve` (a single process: the queue lives in memory). Abuse protection
without accounts (spec §2): Cloudflare Turnstile, a per-IP rate limit, file size and page
limits, and a maximum queue length.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import tempfile
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from checkref import __version__
from checkref.pipeline import STAGES
from checkref.report.model import guide_url
from checkref.report.render import FONTS, FONTS_URL
from checkref.web.config import CREDITS, Settings
from checkref.web.jobs import Job, JobStore, QueueFull, State

log = logging.getLogger("checkref.web")

HERE = Path(__file__).parent
TURNSTILE_VERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
SIGNATURES = {".pdf": b"%PDF-", ".docx": b"PK\x03\x04"}
LOCAL_ADDRESSES = {"127.0.0.1", "::1"}
FORM_OVERHEAD = 64 * 1024  # multipart boundaries and the small form fields
STEPS = {"opening": "Opening the file", **STAGES, "report": "Writing the report"}
DOWNLOAD_FILES = {
    "pdf": ("report.pdf", "-report.pdf", "application/pdf"),
    "docx": (
        "corrected.docx",
        "-corrected-references.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
}


class RateLimiter:
    """Accepted uploads per client address in a sliding window. Addresses stay in memory only."""

    def __init__(self, limit: int, window_s: float):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque[float]] = {}

    def _recent(self, key: str, now: float) -> deque[float]:
        hits = self.hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        return hits

    def allowed(self, key: str, now: float | None = None) -> bool:
        return len(self._recent(key, time.time() if now is None else now)) < self.limit

    def record(self, key: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self._recent(key, now).append(now)
        if len(self.hits) > 10_000:
            for k in [k for k, v in self.hits.items() if not self._recent(k, now)]:
                del self.hits[k]


def script_hashes(html: str) -> str:
    """CSP sources allowing exactly the inline scripts of a page (the report's filter buttons)."""
    return " ".join(
        f"'sha256-{base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()}'"
        for s in re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    )


async def verify_turnstile(secret: str, token: str, ip: str) -> bool:
    data = {"secret": secret, "response": token, "remoteip": ip}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            reply = await client.post(TURNSTILE_VERIFY, data=data)
        return bool(reply.json().get("success"))
    except (httpx.HTTPError, ValueError):
        log.warning("Turnstile verification unavailable")
        return False


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = JobStore(settings)
    limiter = RateLimiter(settings.rate_limit, settings.rate_window_min * 60)
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals.update(
        version=__version__, settings=settings, credits=CREDITS, guide_url=guide_url()
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.turnstile_secret:
            log.warning("Turnstile is off (CHECKREF_TURNSTILE_SECRET not set): development only")
        store.start()
        yield
        store.stop()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.limiter = store, limiter
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    app.mount(FONTS_URL.rstrip("/"), StaticFiles(directory=FONTS), name="fonts")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        turnstile = "https://challenges.cloudflare.com"
        scripts = response.headers.get("x-script-hashes", "")
        if "x-script-hashes" in response.headers:
            del response.headers["x-script-hashes"]
        response.headers.setdefault(
            "Content-Security-Policy",
            f"default-src 'self'; script-src 'self' {turnstile} {scripts}; frame-src {turnstile}; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Job addresses are the only key to a report: never send them on as a referrer.
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith(("/jobs/", "/api/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    def page(request: Request, name: str, code: int = 200, **context) -> HTMLResponse:
        return templates.TemplateResponse(request, name, context, status_code=code)

    def message(request: Request, title: str, text: str, code: int) -> HTMLResponse:
        return page(request, "message.html", code, title=title, text=text, status_code=code)

    def client_ip(request: Request) -> str:
        peer = request.client.host if request.client else "unknown"
        if settings.trust_proxy and peer in LOCAL_ADDRESSES:
            # Caddy appends the address it saw last, so the final entry is the visitor's.
            forwarded = request.headers.get(settings.proxy_header, "").split(",")[-1].strip()
            if forwarded:
                return forwarded
        return peer

    def find(job_id: str) -> Job | None:
        return store.get(job_id)

    def gone(request: Request, job: Job | None) -> HTMLResponse:
        if job and job.state == State.DELETED:
            return message(
                request,
                "This report has been deleted",
                "Reports are deleted after both files are downloaded, after "
                f"{settings.expiry_min} minutes, or when you press Delete now. To see it "
                "again, upload the file again.",
                410,
            )
        return message(
            request,
            "Report not found",
            "This address does not match any check. Reports are deleted after "
            f"{settings.expiry_min} minutes at the latest.",
            404,
        )

    # ------------------------------------------------------------------ pages

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return page(request, "index.html", this_year=date.today().year)

    @app.post("/check")
    async def check(request: Request):
        ip = client_ip(request)
        size = request.headers.get("content-length", "")
        if not size.isdigit():
            return message(request, "Upload failed", "The upload had no length.", 411)
        if int(size) > settings.max_upload_bytes + FORM_OVERHEAD:
            return too_large(request)
        if not limiter.allowed(ip):
            return message(
                request,
                "Too many checks",
                f"This connection has used its {settings.rate_limit} checks for the last "
                f"{settings.rate_window_min} minutes. Please try again later.",
                429,
            )
        form = await request.form(max_files=1, max_fields=10)
        try:
            if not await turnstile_ok(form.get("cf-turnstile-response"), ip):
                return message(
                    request,
                    "Bot check failed",
                    "The check that you are not a bot did not pass. Please go back, wait for "
                    "the check box to finish, and upload again.",
                    400,
                )
            upload = form.get("file")
            if upload is None or isinstance(upload, str) or not upload.filename:
                return message(request, "No file", "Please choose a PDF or Word file.", 400)
            name = Path(upload.filename.replace("\\", "/")).name[:200]
            suffix = Path(name).suffix.lower()
            if suffix not in SIGNATURES:
                return message(
                    request,
                    "Unsupported file",
                    "Only PDF (.pdf) and Word (.docx) files can be checked. An older .doc "
                    "file can be saved as .docx from Word.",
                    415,
                )
            options = {}
            if form.get("recency"):
                try:
                    share = int(form.get("share") or 80)
                    year = int(form.get("year") or date.today().year)
                except ValueError:
                    share, year = -1, 0
                if not (1 <= share <= 100 and 1900 <= year <= date.today().year + 1):
                    return message(
                        request,
                        "Recency settings",
                        "The share must be 1–100% and the year a recent year.",
                        400,
                    )
                options["recency"] = {"share": share / 100, "year": year}
            saved = await run_in_threadpool(save_upload, upload.file, suffix)
        finally:
            await form.close()
        if saved is None:
            return too_large(request)
        if saved is False:
            return message(
                request,
                "Unsupported file",
                f"This file is not a real {suffix} file. Please upload the file as saved by "
                "Word or your PDF program.",
                415,
            )
        try:
            job = store.create(name, suffix, saved, options)
        except QueueFull:
            saved.unlink(missing_ok=True)
            return message(
                request,
                "Busy, please try again later",
                "Too many files are waiting to be checked right now. Please try again in a "
                "few minutes.",
                503,
            )
        limiter.record(ip)
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    def too_large(request: Request) -> HTMLResponse:
        return message(
            request,
            "File too large",
            f"The limit is {settings.max_upload_mb:g} MB. Large files are usually big because "
            "of images; a copy without images, or just the chapters with citations and the "
            "reference list, works the same.",
            413,
        )

    def save_upload(source, suffix: str) -> Path | None | bool:
        """Copy the upload into the jobs folder. None = too large; False = wrong content."""
        fd, tmp = tempfile.mkstemp(prefix=".upload-", dir=settings.jobs_dir)
        path = Path(tmp)
        total = 0
        with open(fd, "wb") as out:
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    break
                out.write(chunk)
        if total > settings.max_upload_bytes:
            path.unlink(missing_ok=True)
            return None
        with path.open("rb") as f:
            if not f.read(8).startswith(SIGNATURES[suffix]):
                path.unlink(missing_ok=True)
                return False
        return path

    async def turnstile_ok(token, ip: str) -> bool:
        if not settings.turnstile_secret:
            return True
        if not token or not isinstance(token, str):
            return False
        return await verify_turnstile(settings.turnstile_secret, token, ip)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    async def job_page(request: Request, job_id: str):
        job = find(job_id)
        if not job or job.state == State.DELETED:
            return gone(request, job)
        if job.state == State.DONE:
            return RedirectResponse(f"/jobs/{job.id}/report", status_code=303)
        if job.state == State.FAILED:
            return message(request, "The file could not be checked", job.message, 422)
        return page(request, "job.html", job=job, status=store.status(job), steps=STEPS)

    @app.get("/api/jobs/{job_id}")
    async def job_status(job_id: str):
        job = find(job_id)
        if not job:
            return JSONResponse({"state": "missing"}, status_code=404)
        out = store.status(job)
        if "stage" in out:
            out["stage_label"] = STEPS.get(out["stage"] or "", "Starting")
            out["step"] = list(STEPS).index(out["stage"]) + 1 if out["stage"] in STEPS else 0
            out["steps"] = len(STEPS)
        return out

    @app.get("/jobs/{job_id}/report", response_class=HTMLResponse)
    async def report(request: Request, job_id: str):
        job = find(job_id)
        if not job or job.state != State.DONE:
            if job and job.state in (State.QUEUED, State.RUNNING, State.FAILED):
                return RedirectResponse(f"/jobs/{job.id}", status_code=303)
            return gone(request, job)
        try:
            html = (job.folder / "report.html").read_text(encoding="utf-8")
        except OSError:
            return gone(request, job)
        return HTMLResponse(html, headers={"x-script-hashes": script_hashes(html)})

    @app.get("/jobs/{job_id}/{kind}")
    async def download(request: Request, job_id: str, kind: str):
        job = find(job_id)
        if kind not in DOWNLOAD_FILES:
            return message(request, "Not found", "There is no such download.", 404)
        if not job or job.state != State.DONE:
            return gone(request, job)
        stored, ending, media = DOWNLOAD_FILES[kind]
        path = job.folder / stored
        if not path.is_file():
            return gone(request, job)
        return FileResponse(
            path,
            media_type=media,
            filename=job.download_stem + ending,
            background=BackgroundTask(store.downloaded, job, kind),
        )

    @app.post("/jobs/{job_id}/delete", response_class=HTMLResponse)
    async def delete(request: Request, job_id: str):
        job = find(job_id)
        if job and job.state != State.DELETED:
            store.delete(job, "by user")
            return message(
                request,
                "Deleted",
                "The report and everything from your file have been deleted from the server.",
                200,
            )
        return gone(request, job)

    @app.get("/healthz")
    async def health():
        return Response("ok", media_type="text/plain")

    return app


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # One process (the queue is in memory); no access log (it would hold addresses and paths).
    uvicorn.run(create_app(), host=host, port=port, workers=1, access_log=False)
