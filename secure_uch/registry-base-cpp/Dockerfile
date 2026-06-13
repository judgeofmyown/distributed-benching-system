FROM debian:bookworm-slim

# Pre-installs
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    # Networking & Concurrency
    libboost-all-dev \
    libssl-dev \
    libuv1-dev \
    # Common serialization used in trading APIs
    nlohmann-json3-dev \
    libprotobuf-dev \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN mkdir -p /app/submission

EXPOSE 8888

# Compile with optimization AND link standard libraries automatically
CMD ["sh", "-c", "g++ -O3 -std=c++20 /app/submission/exchange_server.cpp -o /app/engine -lpthread -lssl -lcrypto && /app/engine"]
