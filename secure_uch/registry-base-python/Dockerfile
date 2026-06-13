FROM python:3.11-slim

# Fix Python's buffering and caching behaviors
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install high-performance math, validation, and async networking tools
RUN pip install --no-cache-dir \
    numpy \
    pydantic \
    # Ultra-fast JSON parsing and low-latency network primitives
    orjson \
    websockets \
    aiohttp

RUN mkdir -p /app/submission

EXPOSE 8888

# Explicitly invoke python using the unbuffered flag as a secondary safeguard
CMD ["python", "-u", "/app/submission/exchange_server.py"]
