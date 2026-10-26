"""Limiter-level simulation (no HTTP). A fake clock is passed to allow(), so
the whole run is instant and repeatable. It measures the LIMITER DECISIONS only."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rate_limiter import SlidingWindowLimiter

CHUNKS = 20          # a 10 MB file in 512 KB chunks
RESENT = 3           # chunks re-sent after the interruption


def honest_student(limit_fn):
    """start + 20 chunks + status + 3 resent chunks + finalize, one request per second."""
    requests = ["start"] + ["chunk"] * 10 + ["status"] + ["chunk"] * (CHUNKS - 10 + RESENT) + ["finalize"]
    blocked = 0
    for second, kind in enumerate(requests):
        allowed, _ = limit_fn(kind, float(second))
        if not allowed:
            blocked += 1
    return len(requests), blocked


def abuser(limit_fn):
    """Tries to create 100 sessions in 10 seconds. Counts how many were allowed."""
    allowed_count = 0
    for i in range(100):
        allowed, _ = limit_fn("start", i * 0.1)
        allowed_count += allowed
    return allowed_count


def make_naive(limit):
    lim = SlidingWindowLimiter(limit, 60)
    return lambda kind, t: lim.allow("u", now=t)


def make_session_aware():
    lim = SlidingWindowLimiter(3, 60)
    def fn(kind, t):
        if kind == "start":
            return lim.allow("u", now=t)
        return True, 0
    return fn


def run_comparison():
    rows=[]
    for name,maker in [('Naive: 5 requests/minute',lambda:make_naive(5)),
                       ('Naive: 30 requests/minute',lambda:make_naive(30)),
                       ('Session-aware: 3 new/minute',make_session_aware)]:
        total,blocked=honest_student(maker())
        rows.append({'policy':name,'requests':total,'blocked':blocked,
                     'finished':blocked==0,'flood_admissions':abuser(maker())})
    return {'kind':'limiter_simulation','rows':rows,
            'notes':'Deterministic policy simulation with a supplied clock; no HTTP, file uploads, latency or server-capacity measurements. Twenty chunks, three repeated chunks, one request per simulated second. Separate fresh limiters test 100 session attempts in ten simulated seconds.'}

if __name__=='__main__':
    import json
    print(json.dumps(run_comparison(),indent=2))
