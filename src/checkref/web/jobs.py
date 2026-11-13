"""The job queue (plan phase 10): one worker process at a time, progress for the waiting page,
and deletion (spec §5 ⑫).

Jobs live in memory and in one folder each under `Settings.jobs_dir`. A job's folder is removed:
- when both downloads (PDF and DOCX) have been served;
- when the user presses "Delete now";
- `expiry_min` minutes after the check finished;
- on start-up (folders left by a previous run).
After deletion only a small record (state and counts, no file name) is kept until it, too,
expires, so the page can say "deleted" rather than "not found".

The log holds only job IDs, timings and counts.
"""

from __future__ import annotations

import json
import logging
import secrets
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from checkref.web.config import Settings

log = logging.getLogger("checkref.web")

DOWNLOADS = ("pdf",)  # offered on the report page; the report is deleted once all are out


class State(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    DELETED = "deleted"


@dataclass
class Job:
    id: str
    folder: Path
    file_name: str
    created: float = field(default_factory=time.time)
    state: State = State.QUEUED
    started: float | None = None
    finished: float | None = None
    message: str = ""  # for a failed job: what to tell the user
    counts: dict = field(default_factory=dict)
    downloaded: set[str] = field(default_factory=set)

    @property
    def download_stem(self) -> str:
        return Path(self.file_name).stem or "thesis"


class QueueFull(Exception):
    pass


class JobStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jobs: dict[str, Job] = {}
        self.queue: deque[str] = deque()
        self.lock = threading.Lock()
        self.wake = threading.Condition(self.lock)
        self.running: subprocess.Popen | None = None
        self.stopping = False
        self.threads: list[threading.Thread] = []

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        root = self.settings.jobs_dir
        root.mkdir(parents=True, exist_ok=True)
        root.chmod(0o700)
        for leftover in root.iterdir():  # from a previous run; their records are gone
            shutil.rmtree(leftover, ignore_errors=True)
        for target in (self._dispatch, self._sweep):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self.threads.append(t)

    def stop(self) -> None:
        with self.lock:
            self.stopping = True
            if self.running:
                self.running.kill()
            self.wake.notify_all()
        for t in self.threads:
            t.join(timeout=5)
        for job in list(self.jobs.values()):
            self._remove(job)

    # ------------------------------------------------------------------ submitting

    def create(self, file_name: str, suffix: str, data_path: Path, options: dict) -> Job:
        """Queue a check of the uploaded file at `data_path` (moved into the job folder)."""
        with self.lock:
            if len(self.queue) >= self.settings.max_queue:
                raise QueueFull
            job_id = secrets.token_urlsafe(16)
            folder = self.settings.jobs_dir / job_id
            folder.mkdir(mode=0o700)
            shutil.move(data_path, folder / f"input{suffix}")
            options = {
                **options,
                "file_name": file_name,
                "max_pages": self.settings.max_pages,
                "expiry_min": self.settings.expiry_min,
            }
            (folder / "job.json").write_text(json.dumps(options), encoding="utf-8")
            job = Job(id=job_id, folder=folder, file_name=file_name)
            self.jobs[job_id] = job
            self.queue.append(job_id)
            self.wake.notify_all()
        log.info("job %s queued (position %d)", job_id, len(self.queue))
        return job

    # ------------------------------------------------------------------ reading

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def position(self, job: Job) -> int:
        """1 = next to run."""
        with self.lock:
            try:
                return self.queue.index(job.id) + 1
            except ValueError:
                return 0

    def stage(self, job: Job) -> str | None:
        try:
            return json.loads((job.folder / "progress.json").read_text(encoding="utf-8"))["stage"]
        except (OSError, ValueError, KeyError):
            return None

    def status(self, job: Job) -> dict:
        out: dict = {"state": job.state.value}
        if job.state == State.QUEUED:
            out["position"] = self.position(job)
        elif job.state == State.RUNNING:
            out["stage"] = self.stage(job)
            out["seconds"] = round(time.time() - (job.started or time.time()))
        elif job.state == State.FAILED:
            out["message"] = job.message
        return out

    # ------------------------------------------------------------------ downloads, deletion

    def downloaded(self, job: Job, kind: str) -> None:
        """Called after a download has been sent; deletes the job once every offered file is out."""
        with self.lock:
            job.downloaded.add(kind)
            done = set(DOWNLOADS) <= job.downloaded
        if done:
            self.delete(job, "downloaded")

    def delete(self, job: Job, reason: str) -> None:
        with self.lock:
            if job.state == State.DELETED:
                return
            if job.id in self.queue:
                self.queue.remove(job.id)
            if job.state == State.RUNNING and self.running:
                self.running.kill()
            job.state = State.DELETED
            job.finished = job.finished or time.time()
            job.file_name = ""
        self._remove(job)
        log.info("job %s deleted (%s)", job.id, reason)

    def _remove(self, job: Job) -> None:
        shutil.rmtree(job.folder, ignore_errors=True)

    # ------------------------------------------------------------------ threads

    def _dispatch(self) -> None:
        while True:
            with self.lock:
                while not self.queue and not self.stopping:
                    self.wake.wait()
                if self.stopping:
                    return
                job = self.jobs[self.queue.popleft()]
                job.state = State.RUNNING
                job.started = time.time()
            self._run(job)

    def _run(self, job: Job) -> None:
        log.info("job %s started (waited %.0f s)", job.id, job.started - job.created)
        cmd = [sys.executable, "-m", "checkref.web.worker", str(job.folder)]
        cmd.append(str(self.settings.worker_memory_mb))
        with self.lock:
            # stderr goes to the service log; the worker writes no thesis text there.
            self.running = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
        timed_out = False
        try:
            self.running.wait(timeout=self.settings.job_timeout_min * 60)
        except subprocess.TimeoutExpired:
            self.running.kill()
            self.running.wait()
            timed_out = True
        with self.lock:
            code = self.running.returncode
            self.running = None
            if job.state == State.DELETED:  # "Delete now" while it ran
                self._remove(job)
                return
            job.finished = time.time()
            try:
                outcome = json.loads((job.folder / "result.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                outcome = {"ok": False}
            if outcome.get("ok"):
                job.state = State.DONE
                job.counts = {k: v for k, v in outcome.items() if k != "ok"}
            else:
                job.state = State.FAILED
                job.message = outcome.get("message") or (
                    f"The check took longer than {self.settings.job_timeout_min} minutes and "
                    "was stopped."
                    if timed_out
                    else "Something went wrong while checking this file."
                )
        for p in job.folder.glob("input.*"):  # the worker removes it; this is a safety net
            p.unlink(missing_ok=True)
        if job.state == State.FAILED:
            self._remove(job)  # nothing to download
        took = job.finished - (job.started or job.finished)
        log.info(
            "job %s %s in %.1f s (exit %s%s) %s",
            job.id,
            job.state.value,
            took,
            code,
            ", timed out" if timed_out else "",
            json.dumps(job.counts) if job.counts else "",
        )

    def _sweep(self) -> None:
        while not self.stopping:
            self.sweep()
            with self.lock:
                self.wake.wait(timeout=30)

    def sweep(self, now: float | None = None) -> None:
        """Delete results older than the expiry, and forget deleted jobs after the same time."""
        now = time.time() if now is None else now
        expiry = self.settings.expiry_min * 60
        for job in list(self.jobs.values()):
            if job.finished is None or now - job.finished < expiry:
                continue
            if job.state == State.DELETED:
                if now - job.finished >= 2 * expiry:
                    with self.lock:
                        self.jobs.pop(job.id, None)
            else:
                self.delete(job, "expired")
