import asyncio
from typing import Callable, Dict, List, Any

class EventBus:
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None

    def set_loop(self, loop):
        self.loop = loop

    def subscribe(self, event_type: str, callback: Callable):
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)

    def publish(self, event_type: str, payload: Any):
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                if asyncio.iscoroutinefunction(callback):
                    if self.loop and self.loop.is_running():
                        asyncio.run_coroutine_threadsafe(callback(payload), self.loop)
                else:
                    callback(payload)
