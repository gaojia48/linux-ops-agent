#!/usr/bin/env bash
set -u

echo "== Uptime and load average =="
uptime 2>&1

echo
echo "== Memory usage =="
free -h 2>&1

echo
echo "== CPU summary from top =="
if command -v top >/dev/null 2>&1; then
  top -b -n 1 2>/dev/null | head -5
else
  echo "top command is unavailable."
fi

echo
echo "== Top processes by CPU =="
ps aux --sort=-%cpu 2>/dev/null | head -11

echo
echo "== Top processes by memory =="
ps aux --sort=-%mem 2>/dev/null | head -11

echo
echo "== Process states =="
ps -eo stat= 2>/dev/null | awk '{count[$1]++} END {for (state in count) print state, count[state]}' | sort

echo
echo "== Diagnosis hints =="
echo "- High load with low CPU may indicate I/O wait or blocked processes."
echo "- A single process dominating CPU or memory should be checked with logs before restarting."
