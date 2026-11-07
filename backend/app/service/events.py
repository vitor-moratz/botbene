"""Canal de eventos do bot para o painel (WebSocket).

O bot roda numa thread comum; o servidor web roda em asyncio. `publish()` pode ser
chamado de qualquer thread e entrega o evento a todos os navegadores conectados.
"""

from __future__ import annotations

import asyncio


class EventHub:
    def __init__(self, max_queue: int = 500) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue] = set()
        self._max_queue = max_queue

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def clients(self) -> int:
        """Quantos painéis estão abertos agora."""
        return len(self._queues)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._queues.discard(q)

    def publish(self, event: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._fanout, event)

    def _fanout(self, event: dict) -> None:
        for q in list(self._queues):
            if q.qsize() < self._max_queue:  # navegador lento não trava o bot
                q.put_nowait(event)
