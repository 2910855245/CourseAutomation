import os
import sys
import threading
from datetime import datetime


class _Tee:
    def __init__(self, original, fp):
        self.original = original
        self.fp = fp

    def write(self, data):
        self.original.write(data)
        self.original.flush()
        try:
            self.fp.write(data)
            self.fp.flush()
        except Exception as e:
            pass

    def flush(self):
        self.original.flush()
        try:
            self.fp.flush()
        except Exception as e:
            pass

    def isatty(self):
        return self.original.isatty()

    def fileno(self):
        return self.original.fileno()


class SessionLogger:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_init'):
            return
        self._init = True
        self._original_stdout = None
        self._fp = None
        self._running = False

    @staticmethod
    def _path():
        from config import LOGS_DIR
        d = os.path.join(LOGS_DIR, "sessions")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "latest.ses")

    def start(self):
        if self._running:
            return
        self._running = True
        self._original_stdout = sys.stdout
        self._fp = open(self._path(), 'w', encoding='utf-8')
        self._fp.write(f"# {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self._fp.flush()
        sys.stdout = _Tee(self._original_stdout, self._fp)
        try:
            from infrastructure.rich_ui import console as rc
            rc.file = sys.stdout
        except Exception as e:
            pass
        try:
            from presentation.utils import console as pc
            pc.file = sys.stdout
        except Exception as e:
            pass

    def stop(self):
        if not self._running:
            return
        self._running = False
        sys.stdout = self._original_stdout or sys.__stdout__
        try:
            self._fp.close()
        except Exception as e:
            pass
        self._fp = None

    def dump(self):
        """强制刷盘"""
        try:
            if self._fp:
                self._fp.flush()
        except Exception as e:
            pass


def get_session_logger():
    return SessionLogger()
