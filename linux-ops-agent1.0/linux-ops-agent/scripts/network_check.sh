#!/usr/bin/env bash
set -u

echo "== IP addresses =="
if command -v ip >/dev/null 2>&1; then
  ip -brief addr 2>&1
else
  echo "ip command is unavailable."
fi

echo
echo "== Routes =="
if command -v ip >/dev/null 2>&1; then
  ip route 2>&1
else
  echo "ip command is unavailable."
fi

echo
echo "== Listening TCP/UDP ports =="
if command -v ss >/dev/null 2>&1; then
  ss -tulnp 2>/dev/null | head -50
else
  echo "ss command is unavailable."
fi

echo
echo "== DNS and connectivity check =="
if command -v ping >/dev/null 2>&1; then
  ping -c 2 -W 2 223.5.5.5 2>&1
  echo
  ping -c 2 -W 2 baidu.com 2>&1
else
  echo "ping command is unavailable."
fi

echo
echo "== Diagnosis hints =="
echo "- If IP address or default route is missing, check network configuration first."
echo "- If IP ping works but domain ping fails, check DNS settings."
echo "- Unknown listening ports should be mapped to owning processes and business purpose."
