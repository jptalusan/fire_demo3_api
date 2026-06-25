FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgeos-dev \
    libgdal-dev \
    libspatialindex-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The fire_simulator binary is dynamically linked against libonnxruntime.so.1.
# Pull the matching prebuilt Linux release (Microsoft) and stage the shared lib
# where the dynamic linker can find it. Build arg keeps the version bump auditable.
ARG ONNXRUNTIME_VERSION=1.16.3
RUN ARCH="$(uname -m)" \
    && case "$ARCH" in \
         x86_64)  ONNX_ARCH=x64 ;; \
         aarch64) ONNX_ARCH=aarch64 ;; \
         *) echo "Unsupported arch: $ARCH" >&2; exit 1 ;; \
       esac \
    && curl -fsSL "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/onnxruntime-linux-${ONNX_ARCH}-${ONNXRUNTIME_VERSION}.tgz" \
       | tar -xz -C /opt/ \
    && cp /opt/onnxruntime-linux-${ONNX_ARCH}-${ONNXRUNTIME_VERSION}/lib/libonnxruntime.so.${ONNXRUNTIME_VERSION} /usr/local/lib/ \
    && ln -sf /usr/local/lib/libonnxruntime.so.${ONNXRUNTIME_VERSION} /usr/local/lib/libonnxruntime.so.1 \
    && ln -sf /usr/local/lib/libonnxruntime.so.${ONNXRUNTIME_VERSION} /usr/local/lib/libonnxruntime.so \
    && ldconfig \
    && rm -rf /opt/onnxruntime-linux-${ONNX_ARCH}-${ONNXRUNTIME_VERSION}

# The .so SONAME is libonnxruntime.so.1.16.3, so the ldconfig cache doesn't
# answer dlopen("libonnxruntime.so.1"). Add /usr/local/lib to LD_LIBRARY_PATH
# so the loader resolves the bare-major-version symlink we created above.
ENV LD_LIBRARY_PATH=/usr/local/lib

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --upgrade pip setuptools wheel && pip install uv

COPY src ./src
RUN uv pip install --system .

RUN mkdir -p /data/storage && chmod -R 777 /data/storage
ENV STORAGE_ROOT=/data/storage

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
