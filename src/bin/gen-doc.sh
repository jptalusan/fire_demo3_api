#!/bin/bash
# This script generates static API documentation from a FastAPI server using OpenAPI spec.
# It starts the FastAPI server, waits for it to be ready, downloads the OpenAPI spec, and generates HTML documentation using Redoc.
# Usage: ./bin/static_docs.sh

# Start FastAPI server in the background
uv run fastapi dev ./src/main.py &
SERVER_PID=$!

# Wait for the server to be ready
until curl --output /dev/null --silent --head --fail http://127.0.0.1:8000/api/v1/openapi.json; do
    sleep 1
done

# Download OpenAPI spec
curl http://127.0.0.1:8000/api/v1/openapi.json -o openapi.json

# Generate HTML docs
npx redoc-cli bundle openapi.json -o index.html

# Kill the FastAPI server
kill $SERVER_PID

# Clean up
rm openapi.json