#!/bin/sh
# Thin wrapper; all discovery logic lives in dev_install.py (cross-platform).
exec "${PYTHON:-python3}" "$(dirname "$0")/dev_install.py" "$@"
