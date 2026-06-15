#!/bin/bash
# Fix the stale WSL view of CalendarPage.vue (filesystem metadata cache)
# 用法: wsl -e bash scripts/fix_calendar_wsl.sh
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$PROJECT_ROOT/frontend/src/pages/CalendarPage.vue"

if [ ! -f "$TARGET" ]; then
  echo "ERROR: $TARGET not found"
  exit 1
fi

cd "$(dirname "$TARGET")"

# Touch forces metadata cache refresh
touch "$(basename "$TARGET")"
sleep 1

echo "=== BEFORE fix ==="
grep -n 'events\.value' "$(basename "$TARGET")"

# Apply the fix: events.value -> interviewEvents.value
sed -i 's/events\.value/interviewEvents.value/g' "$(basename "$TARGET")"
sed -i 's/const hasDeadlines = computed(() => interviewEvents.value\.some.*deadline.*)/const hasDeadlines = computed(() => deadlineEvents.value.length > 0)/g' "$(basename "$TARGET")"

python3 - <<'PYEOF'
import re, os
p = "CalendarPage.vue"
with open(p, 'r', encoding='utf-8') as f:
    s = f.read()

old_t = '!loading && events.length === 0 && !hasDeadlines'
new_t = '!loading && interviewEvents.length === 0 && deadlineEvents.length === 0'
if old_t in s:
    s = s.replace(old_t, new_t)
    print(f"Replaced template: {old_t} -> {new_t}")
else:
    print("Template pattern not found, may already be fixed")

with open(p, 'w', encoding='utf-8') as f:
    f.write(s)
print("File written")
PYEOF

echo "=== AFTER fix ==="
grep -n 'events\.value\|events\.length' "$(basename "$TARGET")" || echo "(no remaining matches)"
