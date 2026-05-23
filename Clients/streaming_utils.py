"""Shared streaming helpers for Verna AI clients."""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Callable, Dict, Optional

from ServerManager.server_manager import ServerManager


async def iter_stream_events(
    server_manager: ServerManager,
    query: str,
    channel_id: Optional[str] = None,
    thread_ts: Optional[str] = None,
) -> AsyncIterator[dict]:
    """Yield token/status/done/error events from ServerManager."""
    async for event in server_manager.process_request_stream(
        query, channel_id=channel_id, thread_ts=thread_ts
    ):
        yield event


async def collect_stream_response(
    server_manager: ServerManager,
    query: str,
    channel_id: Optional[str] = None,
    thread_ts: Optional[str] = None,
    on_token: Optional[Callable[[str], None]] = None,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> str:
    """Run streaming agent and return the full response text."""
    parts: list[str] = []

    def _dispatch(event: Dict[str, Any]) -> None:
        if on_event:
            on_event(event)
        if event.get("type") == "token" and on_token:
            on_token(event.get("content", ""))

    async for event in iter_stream_events(
        server_manager, query, channel_id=channel_id, thread_ts=thread_ts
    ):
        event_type = event.get("type")
        if event_type == "token":
            chunk = event.get("content", "")
            if chunk:
                parts.append(chunk)
            _dispatch(event)
        elif event_type == "status":
            _dispatch(event)
        elif event_type == "error":
            _dispatch(event)
            return event.get("content", "Error processing request.")
        elif event_type == "done":
            _dispatch(event)
            return event.get("content") or "".join(parts)
    return "".join(parts)


def run_collect_stream(
    server_manager: ServerManager,
    query: str,
    channel_id: Optional[str] = None,
    thread_ts: Optional[str] = None,
    on_token: Optional[Callable[[str], None]] = None,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> str:
    """Sync wrapper for Streamlit and other sync callers."""
    return asyncio.run(
        collect_stream_response(
            server_manager,
            query,
            channel_id,
            thread_ts,
            on_token=on_token,
            on_event=on_event,
        )
    )
