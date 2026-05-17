# Backend (FastAPI)

Phase 1 walking skeleton. The API contract lives in `app/schemas.py` and
[docs/CONTRACT.md](../docs/CONTRACT.md).

## Local dev

```bash
python -m venv .venv && source .venv/bin/activate    # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API runs at http://localhost:8000. Try:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/regions
curl -X POST http://localhost:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"state":"WA","region_type":"county","region_name":"Whatcom County"}'
```

Interactive docs at http://localhost:8000/docs.

## Tests

```bash
pytest
```

The contract test asserts the response shape. Future phases should keep
this test passing without modification.

## Module map

| Module | Purpose | Replaced by |
|--------|---------|-------------|
| `main.py` | FastAPI routes, CORS | (stable) |
| `schemas.py` | Pydantic models = API contract | (stable; change deliberately) |
| `regions.py` | State/county/city → bbox + centroid lookup | TIGER shapefile in a later phase |
| `pipeline.py` | Orchestrator | Each call site replaced one at a time |
| `fakes.py` | Hardcoded Phase-1 data, segregated by future phase | Phase 2/3/4/6/7 |

## Replacing a fake

When Phase 2 lands:
1. Create `app/consumption.py` with `real_consumption(region: RegionRecord) -> Consumption`.
2. In `pipeline.py`, change `fake_consumption(record)` to `real_consumption(record)`.
3. Delete `fake_consumption` from `fakes.py`.
4. Add a real source string to the `Consumption.source` field (e.g. `"eGRID 2023"`).
5. Update `docs/CAVEATS.md` if the real data has limitations the fake didn't.
6. The contract test should still pass.
