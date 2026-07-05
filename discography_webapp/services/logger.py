import logging
import sys
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections and websocket in self.active_connections[user_id]:
            self.active_connections[user_id].remove(websocket)

    async def broadcast(self, message: str, user_id: int = None):
        if user_id and user_id in self.active_connections:
            for connection in list(self.active_connections[user_id]):
                try:
                    await connection.send_text(message)
                except Exception:
                    self.disconnect(connection, user_id)

manager = ConnectionManager()


class SafeFormatter(logging.Formatter):
    """Formatter that safely handles Unicode on Windows consoles."""

    def format(self, record):
        try:
            msg = super().format(record)
            # Map common psytrance symbols to safe ASCII versions if they might fail
            # although uvicorn/ch handles most if reconfigured
            return msg
        except (UnicodeEncodeError, UnicodeDecodeError):
            if isinstance(record.msg, str):
                # Replace unencodable characters
                safe_msg = record.msg.encode('ascii', errors='replace').decode('ascii')
                record.msg = safe_msg
            return super().format(record)


class WebSocketHandler(logging.Handler):
    def __init__(self, event_bus, user_id):
        super().__init__()
        self.event_bus = event_bus
        self.user_id = user_id

    def emit(self, record):
        try:
            log_entry = self.format(record)
        except UnicodeEncodeError:
            record.msg = str(record.msg).encode('ascii', errors='replace').decode('ascii')
            log_entry = self.format(record)
        except Exception:
            return
        try:
            self.event_bus.publish('log', {
                'user_id': self.user_id,
                'message': log_entry
            })
        except Exception:
            # Silently drop if event bus fails — don't crash logging
            pass


import os

loggers = {}

def get_logger(event_bus, user_id: int):
    if user_id in loggers:
        return loggers[user_id]

    logger = logging.getLogger(f"discography_downloader_{user_id}")
    logger.setLevel(logging.INFO)
    # Prevent duplicate handlers on re-creation
    logger.handlers.clear()

    formatter = SafeFormatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S')

    # Console handler — force UTF-8 on Windows
    ch = logging.StreamHandler(stream=sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    try:
        ch.stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    logger.addHandler(ch)

    # File handler
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_file = os.path.join(base_dir, "data", f"app_{user_id}.log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    fh = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # WebSocket handler
    ws_handler = WebSocketHandler(event_bus, user_id)
    ws_handler.setFormatter(formatter)
    logger.addHandler(ws_handler)

    loggers[user_id] = logger
    return logger
