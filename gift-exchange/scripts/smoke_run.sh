#!/bin/sh
# Manual smoke test: copies the tracked files to a temp folder, runs ./run there, waits for health.
# Not called from check.sh or any test. Needs network (uv downloads).
URL=http://localhost:8501/_stcore/health
HERE=$(cd "$(dirname "$0")/.." && pwd)

if curl -fsS "$URL" >/dev/null 2>&1; then
  echo "fail: something already answers on localhost:8501"
  exit 1
fi

WORK=$(mktemp -d)
cd "$HERE" || exit 1
git ls-files --cached | while IFS= read -r f; do
  [ -f "$f" ] || continue
  mkdir -p "$WORK/app/$(dirname "$f")"
  cp -p "$f" "$WORK/app/$f"
done

cd "$WORK/app" || exit 1
UV_CACHE_DIR="$WORK/uv-cache" GIFTX_DATA_DIR="$WORK/data" GIFTX_NO_OPEN=1 \
  python3 -c 'import os,sys; os.setsid(); os.execv("./run", ["./run"])' >"$WORK/run.log" 2>&1 &
PID=$!

result=fail
i=0
while [ $i -lt 600 ]; do
  if curl -fsS "$URL" 2>/dev/null | grep -q ok; then
    result=pass
    break
  fi
  kill -0 "$PID" 2>/dev/null || break
  sleep 0.5
  i=$((i + 1))
done

# the child called setsid, so its process group id is its own pid
kill -TERM -- "-$PID" 2>/dev/null
sleep 1
kill -KILL -- "-$PID" 2>/dev/null
if [ "$result" = fail ]; then
  tail -20 "$WORK/run.log"
fi
rm -rf "$WORK"
echo "$result"
[ "$result" = pass ]
