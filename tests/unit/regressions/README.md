# Regression tests

Fast, mock/fixture-only unit tests pinning bugs found and fixed over the past
two weeks so they can't silently come back. No real DB, no real C++
simulator subprocess, no real OSRM, no real growth_v1 bundle load, no
internet.

Run with: `pytest tests/unit/regressions -v`

| File | Regresses commit(s) | Summary |
|---|---|---|
| `test_apparatus_column_alignment.py` | `4efcfff` | The 5 places that name apparatus columns (writer, stations route, `ApparatusSpec` schema, both CSV headers) must agree exactly. |
| `test_roster_endpoint_reads_chiefs.py` | `4efcfff` | `GET /api/stations/roster` must surface `Suppression_Chief` / `EMS_Chief` counts. |
| `test_synthetic_csv_datetime_format.py` | `a795946` | Synthetic incident datetimes must be written as `YYYY-MM-DD HH:MM:SS`, no fractional/nanosecond seconds. |
| `test_synthetic_csv_no_commas_in_type.py` | `0352dda` | `sanitize_incident_types` strips commas using the historical `' -  '` convention; historical types pass through unchanged. |
| `test_synthetic_csv_category_remap.py` | `36cc7c1` | `remap_categories` replaces placeholder `'Major'`/`'Unknown'` with the real NFDResponse Enum via a mocked lookup. |
| `test_path_resolution_via_env.py` | `071924d`, `2ec4e5e` | `BASE_DIR`/`DATA_DIR`/`LOGS_DIR` honor env overrides; `incidents_variants.BUNDLE_DIR` follows `DATA_DIR`. |
| `test_osrm_host_fallback.py` | `1c090fa` | Unresolvable `OSRM_HOST` falls back to `localhost` with a printed diagnostic; a resolvable host is kept silently. |
| `test_apparatus_writer.py` | `c76b35c` | `create_stations_csv_from_payload` writes chief counts correctly, renames `Engine`->`Engine_ID`, and silently drops unknown apparatus types (pinned as current behavior). |
| `test_naive_csv_parsing_safety.py` | `0352dda`/`a795946`/`36cc7c1` (root cause) | Every synthetic-incidents CSV row splits to exactly 7 fields under a naive `line.split(',')`, matching the C++ loader's actual parsing. |
| `test_error_response_shapes.py` | endpoint audit (mostly unfixed) | Pins known-good 4xx+JSON error shapes; `xfail`s the still-broken bare-500 cases with NOTEs. |
| `test_run_simulation_command_construction.py` | (this session) | `FIREBEATS_MATRIX_PATH` uses the shared `<BASE_DIR>/logs/beats.bin`, not the per-run `logs_dir`; `--DISPATCH_POLICY` reflects config. |
| `test_dispatch_policy_field_precedence.py` | (dead-field cleanup) | `models.dispatch` has zero effect; only top-level `dispatch_policy` is read. |
