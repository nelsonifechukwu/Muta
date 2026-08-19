#!/bin/bash
# Launch the Muta IQ experiment report and profiler. Usage: ./dashboard/start.sh [port] [--no-open]
cd "$(dirname "$0")" && exec python3 app.py "$@"
