#!/bin/bash
echo "Starting DEFAI ComplianceOS..."
pkill -f "python3 main.py" 2>/dev/null || true
sleep 1
python3 main.py &
sleep 4
echo "Server ready. Running demo scenarios..."
python3 tests/scenarios.py
