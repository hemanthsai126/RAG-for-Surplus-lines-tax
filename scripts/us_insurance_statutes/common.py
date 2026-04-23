from __future__ import annotations

import time
from pathlib import Path

import httpx

try:
    import certifi

    def ssl_verify() -> str | bool:
        return certifi.where()

except ImportError:

    def ssl_verify() -> str | bool:
        return True


def client_headers(user_agent: str) -> dict[str, str]:
    return {"User-Agent": user_agent, "Accept": "text/html,*/*;q=0.8"}


def make_client(
    *,
    user_agent: str,
    timeout: float,
    verify: str | bool,
) -> httpx.Client:
    return httpx.Client(
        headers=client_headers(user_agent),
        timeout=timeout,
        verify=verify,
        http2=False,
    )


def get_text(client: httpx.Client, url: str, delay_sec: float) -> str:
    r = client.get(url, follow_redirects=True)
    r.raise_for_status()
    time.sleep(delay_sec)
    return r.text


def write_md(path: Path, title: str, source_url: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    md = f"# {title}\n\n**Official source:** {source_url}\n\n---\n\n{body}\n"
    path.write_text(md, encoding="utf-8")
