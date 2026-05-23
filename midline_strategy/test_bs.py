from backfill_history import _fetch_chunk

print("Test 1: 2018-01-01 ~ 2025-12-31")
df = _fetch_chunk(["000001"], "2018-01-01", "2025-12-31")
print("  rows:", len(df) if df is not None else "FAILED")

print("Test 2: 2025-01-01 ~ 2025-12-31")
df = _fetch_chunk(["000001"], "2025-01-01", "2025-12-31")
print("  rows:", len(df) if df is not None else "FAILED")
