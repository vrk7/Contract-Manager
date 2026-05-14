from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, AsyncGenerator

import structlog

logger = structlog.get_logger(__name__)


class EventBus:
    def __init__(self) -> None:
        self.listeners: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def publish(self, analysis_id: str, event: str, data: Any) -> None:
        listeners = self.listeners.get(analysis_id, [])
        logger.debug("event_published", analysis_id=analysis_id, event=event, listener_count=len(listeners))
        for queue in listeners:
            queue.put_nowait({"event": event, "data": data})

    async def subscribe(self, analysis_id: str) -> AsyncGenerator[dict, None]:
        queue: asyncio.Queue = asyncio.Queue()
        self.listeners.setdefault(analysis_id, []).append(queue)
        try:
            while True:
                item = await queue.get()
                yield item
        finally:
            self.listeners[analysis_id].remove(queue)
            if not self.listeners[analysis_id]:
                self.listeners.pop(analysis_id, None)


event_bus = EventBus()
