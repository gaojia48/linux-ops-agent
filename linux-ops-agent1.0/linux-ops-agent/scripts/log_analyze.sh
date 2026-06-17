#!/usr/bin/env bash
set -u

echo "== Log source detection =="
AUTH_LOG=""
if [ -n "${AUTH_LOG_FILE:-}" ] && [ -r "${AUTH_LOG_FILE:-}" ]; then
  AUTH_LOG="$AUTH_LOG_FILE"
elif [ -r /var/log/auth.log ]; then
  AUTH_LOG="/var/log/auth.log"
elif [ -r /var/log/secure ]; then
  AUTH_LOG="/var/log/secure"
fi

if [ -n "$AUTH_LOG" ]; then
  echo "Using auth log: $AUTH_LOG"
else
  echo "No readable /var/log/auth.log or /var/log/secure found."
fi

echo
echo "== Recent authentication failures =="
if [ -n "$AUTH_LOG" ]; then
  grep -Ei 'failed|failure|invalid|authentication failure' "$AUTH_LOG" 2>/dev/null | tail -30
elif command -v journalctl >/dev/null 2>&1; then
  journalctl -u ssh -u sshd --since "24 hours ago" --no-pager 2>/dev/null | grep -Ei 'failed|failure|invalid' | tail -30
else
  echo "No readable auth log and journalctl is unavailable."
fi

echo
echo "== Top failed SSH source IPs =="
if [ -n "$AUTH_LOG" ]; then
  grep -Ei 'failed password|invalid user|authentication failure' "$AUTH_LOG" 2>/dev/null \
    | sed -nE 's/.*from ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+).*/\1/p' \
    | sort | uniq -c | sort -nr | head -10
else
  echo "Skipped because no readable auth log file was found."
fi

echo
echo "== Recent system errors =="
if command -v journalctl >/dev/null 2>&1; then
  journalctl -p warning..alert --since "24 hours ago" --no-pager 2>/dev/null | tail -50
elif [ -r /var/log/syslog ]; then
  grep -Ei 'error|warn|fail|critical' /var/log/syslog 2>/dev/null | tail -50
elif [ -r /var/log/messages ]; then
  grep -Ei 'error|warn|fail|critical' /var/log/messages 2>/dev/null | tail -50
else
  echo "No readable journalctl, syslog, or messages source found."
fi

echo
echo "== Diagnosis hints =="
echo "- Many failed SSH attempts from one IP may indicate brute-force scanning."
echo "- Repeated service warnings should be correlated with process and network checks."
