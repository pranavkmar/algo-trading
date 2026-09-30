#!/usr/bin/env bash
# ==============================================================================
# cron_bhavcopy_sync.sh - Automated Daily NSE Bhavcopy Delta & Screener Cron Task
# Runs Monday-Friday after market close (e.g. 20:00 IST / 14:30 UTC)
# ==============================================================================

set -euo pipefail

PROJECT_DIR="/home/beast/algo-trading"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/cron_bhavcopy.log"

mkdir -p "${LOG_DIR}"

echo "======================================================================" >> "${LOG_FILE}"
echo "[CRON] Starting Daily Bhavcopy Sync at $(date -u '+%Y-%m-%d %H:%M:%S UTC') ($(TZ='Asia/Kolkata' date '+%Y-%m-%d %H:%M:%S IST'))" >> "${LOG_FILE}"
echo "======================================================================" >> "${LOG_FILE}"

cd "${PROJECT_DIR}"

# 1. Run incremental delta sync
"${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/data_sync.py" >> "${LOG_FILE}" 2>&1

# 2. Run automated institutional screening and export today's top signals
"${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/delivery_filter.py" \
    --mode both \
    -d 70.0 \
    -v 2.0 \
    --export "${PROJECT_DIR}/data/institutional_signals.csv" >> "${LOG_FILE}" 2>&1

echo "[CRON] Finished successfully at $(date -u '+%Y-%m-%d %H:%M:%S UTC')" >> "${LOG_FILE}"
echo "" >> "${LOG_FILE}"
