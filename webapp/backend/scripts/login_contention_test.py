"""Isolate exactly how login latency degrades with concurrent scrypt hashing."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/perf_test.db")
os.environ.setdefault("JWT_SECRET", "perf-secret")
from fastapi import FastAPI
from app.core.routes_v2 import register_v2
from fastapi.testclient import TestClient
import concurrent.futures as cf

app = FastAPI()
register_v2(app)
client = TestClient(app)

def one_login():
    t0 = time.perf_counter()
    r = client.post("/api/v2/auth/login", json={"email": "estimator@demo.io", "password": "changeme-estimator"})
    assert r.status_code == 200
    return (time.perf_counter() - t0) * 1000

for concurrency in [1, 5, 10, 20, 25]:
    with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
        t0 = time.perf_counter()
        times = list(ex.map(lambda _: one_login(), range(concurrency)))
        wall = time.perf_counter() - t0
    times.sort()
    print(f"concurrency={concurrency:3d}: per-request p50={times[len(times)//2]:7.1f}ms  "
         f"max={max(times):7.1f}ms  total wall time for batch={wall*1000:7.1f}ms")
