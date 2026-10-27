"""Run isolated checks with all actual socket connections denied before imports."""
import os, socket, sys, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3] / 'trilingua-code' / 'Model'
sys.path.insert(0, str(ROOT))
_local = threading.local()
_connect, _pair = socket.socket.connect, socket.socketpair
def denied(sock, *args, **kwargs):
    if getattr(_local, 'socketpair', False):
        return _connect(sock, *args, **kwargs)
    raise OSError('Outbound network disabled by offline test runner')
def socketpair(*args, **kwargs):
    _local.socketpair = True
    try: return _pair(*args, **kwargs)
    finally: _local.socketpair = False
socket.socket.connect = denied
socket.socketpair = socketpair
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main(sys.argv[1:]))
