#!/usr/bin/env bash
# TenaciousBench ORPO Training — Launcher Script
# Run from repo root: bash training/run_training.sh
# Requires: CUDA GPU with >=28 GB VRAM (tested: A100 40 GB SXM4)
# Estimated time: ~18 minutes for 3 epochs on 110 preference pairs

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$REPO_ROOT/training/config.yaml"
LOG_FILE="$REPO_ROOT/training/training_run.log"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "[$TIMESTAMP] TenaciousBench ORPO training starting" | tee "$LOG_FILE"
echo "Config: $CONFIG" | tee -a "$LOG_FILE"
echo "GPU: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'GPU info unavailable')" | tee -a "$LOG_FILE"

# Dry-run first to validate config
echo "" | tee -a "$LOG_FILE"
echo "=== Config validation (dry run) ===" | tee -a "$LOG_FILE"
python "$REPO_ROOT/training/train.py" \
    --config "$CONFIG" \
    --dry-run \
    2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "=== Starting training run ===" | tee -a "$LOG_FILE"
python "$REPO_ROOT/training/train.py" \
    --config "$CONFIG" \
    2>&1 | tee -a "$LOG_FILE"

FINAL_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "" | tee -a "$LOG_FILE"
echo "[$FINAL_TIMESTAMP] Training run complete. Log: $LOG_FILE" | tee -a "$LOG_FILE"
