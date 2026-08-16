"""Dispatch the crawl-worker GitHub Actions workflow from the API process.

The API must never execute the crawler. After inserting a queued crawl_run it
asks GitHub to run ``crawl-worker.yml``, which claims the row and executes
``execute_crawl_run`` on the runner.
"""

from __future__ import annotations

from typing import Any

import httpx

from backend.core.config import settings
from backend.core.logging import log_event


class CrawlDispatchError(RuntimeError):
    """GitHub workflow_dispatch failed or is not configured."""


def dispatch_crawl_workflow(
    *,
    run_id: int,
    source_id: int | None = None,
    page_id: int | None = None,
) -> dict[str, Any]:
    """Trigger ``workflow_dispatch`` for the crawl worker.

    Scope (source_id / page_id) is passed as workflow inputs because
    ``crawl_runs`` has no scope columns. Never logs the token.
    """

    token = (
        settings.github_actions_token.get_secret_value()
        if settings.github_actions_token is not None
        else None
    )
    repository = (settings.github_repository or "").strip()
    workflow_id = (settings.github_crawl_workflow_id or "").strip()
    ref = (settings.github_workflow_ref or "main").strip()
    api_url = (settings.github_api_url or "https://api.github.com").rstrip("/")

    if not token:
        raise CrawlDispatchError(
            "GITHUB_ACTIONS_TOKEN is not configured; cannot dispatch crawl worker"
        )
    if not repository or "/" not in repository:
        raise CrawlDispatchError(
            "GITHUB_REPOSITORY must be set to 'owner/repo' for crawl dispatch"
        )
    if not workflow_id:
        raise CrawlDispatchError("GITHUB_CRAWL_WORKFLOW_ID is not configured")

    inputs: dict[str, str] = {"run_id": str(int(run_id))}
    if source_id is not None:
        inputs["source_id"] = str(int(source_id))
    if page_id is not None:
        inputs["page_id"] = str(int(page_id))

    url = f"{api_url}/repos/{repository}/actions/workflows/{workflow_id}/dispatches"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = {"ref": ref, "inputs": inputs}

    log_event(
        "crawl_workflow_dispatch_started",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        repository=repository,
        workflow_id=workflow_id,
        ref=ref,
    )
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise CrawlDispatchError(
            f"GitHub workflow_dispatch transport error: {type(exc).__name__}"
        ) from exc

    if response.status_code not in {204, 201, 200}:
        # Do not include response body if it might echo auth; keep short.
        raise CrawlDispatchError(
            f"GitHub workflow_dispatch failed with HTTP {response.status_code}"
        )

    log_event(
        "crawl_workflow_dispatch_succeeded",
        run_id=run_id,
        source_id=source_id,
        page_id=page_id,
        repository=repository,
        workflow_id=workflow_id,
        http_status=response.status_code,
    )
    return {
        "dispatched": True,
        "repository": repository,
        "workflow_id": workflow_id,
        "ref": ref,
        "run_id": run_id,
        "source_id": source_id,
        "page_id": page_id,
    }
