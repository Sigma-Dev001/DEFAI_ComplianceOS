#!/bin/bash
echo "Starting DEFAI ComplianceOS..."
pkill -f "python3 main.py" 2>/dev/null || true
sleep 1
python3 main.py &
echo "Waiting for server to be ready..."
until curl -s http://localhost:8000/health > /dev/null 2>&1; do
    sleep 1
done
echo "Server ready. Running demo scenarios..."
python3 tests/scenarios.py
