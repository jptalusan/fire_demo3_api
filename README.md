# Fire Demo3 API

A FastAPI application that serves data files.

## Installation

Install dependencies:

```bash
pip install -e .
```

## Running

Run the application:

```bash
python src/app.py
```

Or with uvicorn:

```bash
uvicorn src.app:app --reload

# With debug
uv run uvicorn src.app:app --reload --log-level debug --host 0.0.0.0 --port 8000
```

## API

- GET /files: Returns a JSON list of files in the data directory.