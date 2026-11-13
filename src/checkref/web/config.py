"""Web app settings (spec §2, §5 ⑫). Every limit can be set through an environment variable
CHECKREF_<NAME>; the defaults are the version-1 starting values (spec §13: tuned after
deployment)."""

from __future__ import annotations

import dataclasses
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Shown in the footer of the web pages (home page and report view), never in the PDF.
CREDITS = (
    ("Owned by", "Dr. Muhammad Akmal", "muhammad.akmal@uvas.edu.pk"),
    ("Developed by", "Taha Mahmood", "taha.tsf901@gmail.com"),
)


@dataclass(frozen=True)
class Settings:
    jobs_dir: Path = Path(tempfile.gettempdir()) / "checkref-jobs"
    max_upload_mb: float = 20
    max_pages: int = 100
    max_queue: int = 10  # waiting jobs, not counting the one running
    rate_limit: int = 5  # accepted uploads per IP address...
    rate_window_min: int = 60  # ...in this many minutes
    expiry_min: int = 60  # results are deleted this long after the check at the latest
    job_timeout_min: int = 20
    worker_memory_mb: int = 4096  # 0 = no limit
    # Cloudflare Turnstile; both empty = no bot check (local development only).
    turnstile_site_key: str = ""
    turnstile_secret: str = ""
    # Behind a proxy on the same server (Caddy) the visitor's address comes from a header:
    # "x-forwarded-for" (Caddy alone) or "cf-connecting-ip" (Cloudflare in front of Caddy).
    # Only read when the request itself comes from this machine.
    trust_proxy: bool = False
    proxy_header: str = "x-forwarded-for"

    @classmethod
    def from_env(cls) -> Settings:
        values = {}
        for f in dataclasses.fields(cls):
            raw = os.environ.get(f"CHECKREF_{f.name.upper()}")
            if raw is None:
                continue
            kind = type(f.default)
            values[f.name] = raw == "1" if kind is bool else kind(raw)
        return cls(**values)

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)
