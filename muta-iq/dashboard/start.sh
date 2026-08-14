#!/bin/bash
# Launch the MUTA-IQ profiler dashboard. Usage: ./dashboard/start.sh [port] [--no-open]
cd "$(dirname "$0")" && exec python3 app.py "$@"
