#!/usr/bin/env bash
set -u

echo "== Disk usage =="
df -h 2>&1

echo
echo "== Inode usage =="
df -i 2>&1

echo
echo "== Filesystems above 80 percent =="
df -P 2>/dev/null | awk 'NR > 1 {
  pct=$5
  gsub("%", "", pct)
  if (pct + 0 >= 80) {
    print $0
  }
}'

echo
echo "== /var/log directory usage =="
if [ -d /var/log ]; then
  du -xh /var/log 2>/dev/null | sort -h | tail -10
else
  echo "/var/log does not exist on this system."
fi

echo
echo "== Large files under /var/log over 100 MiB =="
if [ -d /var/log ]; then
  find /var/log -xdev -type f -size +100M -printf '%s %p\n' 2>/dev/null | sort -n | tail -20 | awk '{
    size=$1
    $1=""
    printf "%.1f MiB%s\n", size / 1024 / 1024, $0
  }'
else
  echo "Skipped because /var/log does not exist."
fi

echo
echo "== Diagnosis hints =="
echo "- If Use% or IUse% is above 80%, check large files and log rotation."
echo "- If /var/log contains very large files, inspect logrotate settings before deleting anything."
