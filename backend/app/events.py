from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, AsyncGenerator


class EventBus:
    def __init__(self) -> None:
        self.listeners: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def publish(self, analysis_id: str, event: str, data: Any) -> None:
        for queue in self.listeners.get(analysis_id, []):
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
