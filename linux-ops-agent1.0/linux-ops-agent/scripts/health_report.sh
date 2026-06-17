#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "== Health report started at $(date '+%F %T') =="
echo

echo "######## Disk ########"
bash "$SCRIPT_DIR/disk_check.sh"
echo

echo "######## Process ########"
bash "$SCRIPT_DIR/process_check.sh"
echo

echo "######## Network ########"
bash "$SCRIPT_DIR/network_check.sh"
echo

echo "######## Logs ########"
bash "$SCRIPT_DIR/log_analyze.sh"
echo

echo "== Health report finished at $(date '+%F %T') =="
