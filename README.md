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

## TRY THIS FROM GPT
Got it — you’re on **RHEL 8** and want to install everything needed to run this FastAPI app.

Here’s a clean, step-by-step setup guide:

---

### 🧰 1. Install system dependencies

RHEL 8 ships with an older Python by default, so you’ll need to ensure Python ≥3.9 is available.

```bash
sudo dnf install -y python3 python3-pip python3-virtualenv git
```

If you want to use `uv` (the fast Python package manager mentioned in your README), install it separately:

```bash
pip install uv
```

If that fails due to permission issues, use:

```bash
python3 -m pip install --user uv
```

---

### 🧱 2. Clone and enter the project directory

```bash
git clone https://github.com/your-org/fire-demo3-api.git
cd fire-demo3-api
```

---

### 🐍 3. (Optional but recommended) Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

### 📦 4. Install Python dependencies

If your project has a `pyproject.toml` or `setup.py` file, the `-e .` installs it in *editable mode*:

```bash
pip install -e .
```

If you’re using `uv`, run:

```bash
uv pip install -e .
```

---

### 🚀 5. Run the FastAPI app

You can run it directly with Python:

```bash
python src/app.py
```

Or, preferably, with **Uvicorn** (ASGI server):

```bash
uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```

If you used `uv`, you can do:

```bash
uv run uvicorn src.app:app --reload --log-level debug --host 0.0.0.0 --port 8000
```

---

### ✅ 6. Test the API

Visit in your browser:

```
http://localhost:8000/files
```

Or the interactive docs:

```
http://localhost:8000/docs
```

---

### 🧩 Optional dependencies for development

If you want to include developer tools (e.g. testing, linting):

```bash
pip install -e .[dev]
```

(Assuming your `pyproject.toml` or `setup.cfg` defines a `[project.optional-dependencies]` section.)

---

Would you like me to show you an example of what your `pyproject.toml` or `setup.py` should contain so `pip install -e .` works correctly on RHEL 8?

