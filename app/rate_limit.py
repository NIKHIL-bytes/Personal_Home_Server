"""Small in-memory login rate limiter for the single-worker web service."""
from collections import defaultdict, deque
from threading import Lock
import time

WINDOW_SECONDS = 15 * 60
MAX_FAILURES_PER_IP = 10
MAX_FAILURES_PER_ACCOUNT = 5

_lock = Lock()
_attempts = defaultdict(deque)


def _prune(key, now):
    q = _attempts[key]
    cutoff = now - WINDOW_SECONDS
    while q and q[0] <= cutoff:
        q.popleft()
    return q


def _key(kind, value):
    return f"{kind}:{value}"


def check_login_allowed(ip_address: str, username: str):
    now = time.monotonic()

    with _lock:
        ip_q = _prune(_key("ip", ip_address), now)
        account_q = _prune(_key("account", username), now)

        if len(ip_q) >= MAX_FAILURES_PER_IP:
            retry = max(1, int(WINDOW_SECONDS - (now - ip_q[0])))
            return False, retry

        if len(account_q) >= MAX_FAILURES_PER_ACCOUNT:
            retry = max(1, int(WINDOW_SECONDS - (now - account_q[0])))
            return False, retry

    return True, 0


def record_login_failure(ip_address: str, username: str):
    now = time.monotonic()

    with _lock:
        _prune(_key("ip", ip_address), now).append(now)
        _prune(_key("account", username), now).append(now)


def record_login_success(ip_address: str, username: str):
    with _lock:
        _attempts.pop(_key("account", username), None)
        _attempts.pop(_key("ip", ip_address), None)
