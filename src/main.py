import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response
import src.core.config as config
from src.api.main import api_router

logger = logging.getLogger("...")

app = FastAPI(title="Fire Simulator Backend", openapi_url="/api/v1/openapi.json")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5173",  # Vite dev server default port
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next) -> Response:
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    # Add a custom header to the response with the total time
    response.headers["X-Process-Time"] = f"{process_time:.4f}"

    logger.info(f"{request.method} {request.url.path} - Completed in {process_time:.4f}s", extra={"process_time": process_time})

    return response


# app.include_router(api_router)
app.include_router(api_router, prefix="/api")
