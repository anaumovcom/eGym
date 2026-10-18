#!/usr/bin/env bash

set -euo pipefail
umask 077

script_path="$(readlink -f "${BASH_SOURCE[0]}")"
project_root="$(dirname -- "$script_path")"
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/egym"
runtime_dir="${XDG_RUNTIME_DIR:-$state_dir}"
browser_profile="$HOME/snap/chromium/common/egym-kiosk"

mkdir -p "$state_dir" "$runtime_dir"

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  printf 'Kiosk mode requires a graphical desktop session.\n' >&2
  exit 1
fi

browser=""
for candidate in chromium chromium-browser; do
  if command -v "$candidate" >/dev/null 2>&1; then
    browser="$(command -v "$candidate")"
    break
  fi
done
if [[ -z "$browser" && -x /snap/bin/chromium ]]; then
  browser='/snap/bin/chromium'
fi
if [[ -z "$browser" ]]; then
  printf 'Chromium executable not found.\n' >&2
  exit 1
fi

# Share the lock and profile with desktop autostart to prevent duplicates.
exec 9>"$runtime_dir/egym-autostart.lock"
if ! flock -n 9; then
  printf 'eGym kiosk is already running.\n'
  exit 0
fi

cd "$project_root"
bash "$project_root/start-watch.sh"

# Backend startup can take longer while hardware is initializing.
"$project_root/.venv/bin/python" - <<'PY'
import sys
import time
import urllib.error
import urllib.request

urls = (
    'http://127.0.0.1:8000/api/health',
    'http://127.0.0.1:5173/',
)
deadline = time.monotonic() + 180
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

print('Waiting for backend and frontend...', flush=True)
while time.monotonic() < deadline:
    try:
        for url in urls:
            with opener.open(url, timeout=2) as response:
                if response.status != 200:
                    raise RuntimeError(f'{url}: HTTP {response.status}')
    except (OSError, urllib.error.URLError, RuntimeError):
        time.sleep(1)
    else:
        print('Backend and frontend are ready.', flush=True)
        break
else:
    sys.exit('Servers did not become ready within 180 seconds; check .runtime logs.')
PY

printf 'Opening Chromium in kiosk mode. Close with Alt+F4.\n'
"$browser" \
  --user-data-dir="$browser_profile" \
  --no-first-run \
  --no-default-browser-check \
  --disable-session-crashed-bubble \
  --kiosk \
  http://127.0.0.1:5173/