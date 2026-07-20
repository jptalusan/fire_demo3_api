# tests/preflight

Fast configuration / data-integrity checks that run **before** the API is
started -- either as a container-entrypoint step (`scripts/preflight.sh`)
or as the first stage of a CI job. Every failure message names the exact
file / column / env var / payload field that is wrong, plus the fix, so
operators don't have to guess.

## Run it

```
bash scripts/preflight.sh          # both phases, with a banner
pytest tests/preflight -v          # every check including optional
pytest tests/preflight -m "not optional"   # skip predictive/synthetic checks
```

Total wall-clock target: **under 5 seconds**. Phase 1 (required files
only) alone must be **under 1 second** because it's the fail-fast gate.

## Files

| File | Bug class prevented | Motivating incident |
|------|---------------------|---------------------|
| `test_required_files_present.py` | Missing CSVs / models / binary / beats.bin | (2), (3), (9) |
| `test_csv_column_schema.py` | Column drift between stations + NFDResponse, unquoted commas in `incident_type`, category with no dispatch row | (1), (7), (8) |
| `test_env_config_resolution.py` | BASE_DIR / DATA_DIR / LOGS_DIR / OSRM_HOST / HOST_ONNXRUNTIME_DIR wrong | (4), (6) |
| `test_payload_validation.py` | Malformed SimConfig / legacy Chief apparatus / bad enums | (5) |
| `test_simulator_command_paths.py` | `--*_PATH` flags escaping DATA_DIR/LOGS_DIR, per-run collisions | (2), (9) |
| `test_docker_compose_config.py` | Missing bind mounts, missing env vars, hard-coded OSRM_HOST, no restart policy | (2), (4), (6) |

(Incident numbers refer to the list in the preflight task brief.)

## Optional checks

Tests marked `@pytest.mark.optional` cover the growth_poisson_v1 bundle
and incident-prediction-system trees. They are only relevant when a
predictive / synthetic-incident flow is exercised, and are skipped by
`preflight.sh` by default. Run them explicitly with:

```
pytest tests/preflight -v -m optional
```

## Known XFAILs (follow-up work)

Two payload-validation cases are `xfail(strict=True)` because the
current schema is too permissive. When the underlying issue is fixed
the xfails flip to unexpected-pass and force us to remove the marker.

1. **Legacy `{"type":"Chief"}` apparatus is silently accepted at job
   submit.** `JobSubmitRequest.payload` is `dict[str, Any]`; SimConfig
   validation never runs. Follow-up: replace with a discriminated union
   keyed on `kind`.
2. **Reversed `date_range` (`start_date > end_date`) is accepted.**
   `DateRange` has no cross-field validator; the reversed range flows
   through the engine and errors with a misleading "no incidents found".
   Follow-up: add a `@model_validator` on `DateRange`.

## Fixtures

Preflight tests inspect the *real* checkout under test. There is
intentionally very little mocking -- the point is to answer "will a
docker deploy of THIS commit start cleanly?". The only exception is
`test_simulator_command_paths.py`, which patches
`asyncio.create_subprocess_exec` to capture the argv the simulator
would have been launched with, without ever running the C++ binary.
