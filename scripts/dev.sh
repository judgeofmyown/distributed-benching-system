#!/bin/bash

set -e

echo "[^_^]Starting Exchange Benchmark System...[^_^]"

echo "[1/4] Starting client..."
(
    cd client_ui
    npx serve
) &

echo "[2/4] Starting Backend..."
(
    cd backend
    python3 main.py
) &

echo "[3/4] Starting the test exchange engine..."
(
    cd tests
    ./engine_main.exe
) &

echo "[4/4] Starting trading bots..."
(
    cd trading_bots
    python3 main.py
) &

echo ""
echo "All services started."
echo "Press Ctrl+C to stop."

wait

