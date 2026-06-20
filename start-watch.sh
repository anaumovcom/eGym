#!/usr/bin/env bash

set -euo pipefail

bootstrap=false
backend_watch=false
backend_watch_python=""

while (($# > 0)); do
  case "$1" in
    --bootstrap)
      bootstrap=true
      shift
      ;;
    --backend-watch)
      backend_watch=true
      shift
      if (($# == 0)); then
        printf 'Missing Python executable path for --backend-watch.\n' >&2
        exit 1
      fi
      backend_watch_python="$1"
      shift
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      exit 1
      ;;
  esac
done

script_path="$(readlink -f "${BASH_SOURCE[0]}")"
project_root="$(cd -- "$(dirname -- "$script_path")" && pwd)"
runtime_dir="$project_root/.runtime"
frontend_root="$project_root/frontend"
backend_root="$project_root/backend"
exercises_root="$project_root/exercises"
translations_path="$project_root/exercise_name_translations.csv"

frontend_pid_file="$runtime_dir/frontend-watch.pid"
backend_pid_file="$runtime_dir/backend-watch.pid"
frontend_log_file="$runtime_dir/frontend-watch.log"
backend_log_file="$runtime_dir/backend-watch.log"
backend_error_log_file="${backend_log_file}.err"
backend_supervisor_log_file="$runtime_dir/backend-watch-supervisor.log"
bootstrap_log_file="$runtime_dir/watch-bootstrap.log"
bootstrap_error_log_file="${bootstrap_log_file}.err"

backend_url="http://127.0.0.1:8000"
backend_health_url="$backend_url/api/health"
frontend_url="http://127.0.0.1:5173"

mkdir -p "$runtime_dir"

supports_color=false
if [[ -t 1 ]]; then
  supports_color=true
fi

print_color_line() {
  local color_code="$1"
  local message="$2"

  if $supports_color; then
    printf '\033[%sm%s\033[0m\n' "$color_code" "$message"
  else
    printf '%s\n' "$message"
  fi
}

write_info_line() {
  print_color_line '36' "$1"
}

write_success_line() {
  print_color_line '32' "$1"
}

write_warn_line() {
  print_color_line '33' "$1"
}

write_path_line() {
  local label="$1"
  local value="$2"

  if $supports_color; then
    printf '\033[90m%s\033[0m%s\n' "$label" "$value"
  else
    printf '%s%s\n' "$label" "$value"
  fi
}

write_url_line() {
  local label="$1"
  local value="$2"

  if $supports_color; then
    printf '\033[90m%s\033[0m\033[35m%s\033[0m\n' "$label" "$value"
  else
    printf '%s%s\n' "$label" "$value"
  fi
}

fail() {
  printf '%s\n' "$1" >&2
  exit 1
}

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    fail "Required command not found: $command_name"
  fi
}

test_process_running() {
  local process_id="$1"

  kill -0 "$process_id" 2>/dev/null
}

test_http_ready() {
  local url="$1"
  local status_code=""

  if command -v curl >/dev/null 2>&1; then
    status_code="$(curl --silent --output /dev/null --max-time 2 --write-out '%{http_code}' "$url" || true)"
  else
    local probe_python=""

    if [[ -x "$project_root/.venv/bin/python" ]]; then
      probe_python="$project_root/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
      probe_python="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
      probe_python="$(command -v python)"
    fi

    if [[ -n "$probe_python" ]]; then
      status_code="$("$probe_python" - "$url" <<'PY'
import sys
import urllib.error
import urllib.request

url = sys.argv[1]

try:
    with urllib.request.urlopen(url, timeout=2) as response:
        print(response.status)
except urllib.error.HTTPError as exc:
    print(exc.code)
except Exception:
    pass
PY
      )"
    fi
  fi

  [[ "$status_code" =~ ^[0-9]{3}$ ]] || return 1
  ((10#$status_code >= 200 && 10#$status_code < 500))
}

test_backend_ready() {
  test_http_ready "$backend_health_url"
}

test_frontend_ready() {
  test_http_ready "$frontend_url"
}

stop_process_tree() {
  local process_id="$1"
  local child_process_id

  if ! test_process_running "$process_id"; then
    return 0
  fi

  while IFS= read -r child_process_id; do
    [[ -n "$child_process_id" ]] || continue
    stop_process_tree "$child_process_id"
  done < <(pgrep -P "$process_id" || true)

  kill -TERM "$process_id" 2>/dev/null || true

  for _ in {1..25}; do
    if ! test_process_running "$process_id"; then
      return 0
    fi
    sleep 0.2
  done

  kill -KILL "$process_id" 2>/dev/null || true
}

build_backend_watch_snapshot() {
  {
    if [[ -d "$backend_root" ]]; then
      find "$backend_root" \
        \( -path "$backend_root/openapi" -o -path "$backend_root/openapi/*" \) -prune -o \
        -type f \( -name '*.py' -o -name '*.json' -o -name '*.csv' \) \
        -printf '%p|%T@|%s\n'
    fi

    if [[ -d "$exercises_root" ]]; then
      find "$exercises_root" \
        -type f \( -name '*.py' -o -name '*.json' -o -name '*.csv' \) \
        -printf '%p|%T@|%s\n'
    fi

    if [[ -f "$translations_path" ]]; then
      stat --printf '%n|%Y|%s\n' "$translations_path"
    fi
  } 2>/dev/null | sort
}

backend_server_pid=""

start_logged_backend_server() {
  local python_exe="$1"

  (
    cd "$backend_root"
    "$python_exe" -m uvicorn app.main:app \
      --app-dir "$backend_root" \
      --host 127.0.0.1 \
      --port 8000 \
      --timeout-graceful-shutdown 2
  ) >>"$backend_log_file" 2>>"$backend_error_log_file" &

  backend_server_pid="$!"
  write_success_line "Backend server started. PID: $backend_server_pid"
}

stop_logged_backend_server() {
  if [[ -z "$backend_server_pid" ]]; then
    return 0
  fi

  if test_process_running "$backend_server_pid"; then
    stop_process_tree "$backend_server_pid"
  fi

  wait "$backend_server_pid" 2>/dev/null || true
  backend_server_pid=""
}

invoke_backend_watch() {
  local python_exe="$1"
  local previous_snapshot current_snapshot exit_code

  rm -f "$backend_log_file" "$backend_error_log_file"

  write_info_line 'Backend supervisor is watching backend, exercises and exercise_name_translations.csv.'

  previous_snapshot="$(build_backend_watch_snapshot)"

  trap 'stop_logged_backend_server; exit 0' INT TERM EXIT

  start_logged_backend_server "$python_exe"

  while true; do
    if ! test_process_running "$backend_server_pid"; then
      set +e
      wait "$backend_server_pid"
      exit_code=$?
      set -e

      write_warn_line "Backend server exited with code $exit_code. Restarting."
      start_logged_backend_server "$python_exe"
      previous_snapshot="$(build_backend_watch_snapshot)"
    fi

    current_snapshot="$(build_backend_watch_snapshot)"
    if [[ "$current_snapshot" != "$previous_snapshot" ]]; then
      write_warn_line 'Detected backend file changes. Restarting backend server.'
      stop_logged_backend_server
      start_logged_backend_server "$python_exe"
      previous_snapshot="$current_snapshot"
    fi

    sleep 0.2
  done
}

get_pid_from_file() {
  local pid_file="$1"
  local raw_pid

  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi

  raw_pid="$(tr -d '[:space:]' < "$pid_file" 2>/dev/null || true)"
  if [[ ! "$raw_pid" =~ ^[0-9]+$ ]]; then
    rm -f "$pid_file"
    return 1
  fi

  if ! test_process_running "$raw_pid"; then
    rm -f "$pid_file"
    return 1
  fi

  printf '%s\n' "$raw_pid"
}

show_start_summary() {
  local backend_pid frontend_pid
  local backend_ready=false frontend_ready=false

  backend_pid="$(get_pid_from_file "$backend_pid_file" || true)"
  frontend_pid="$(get_pid_from_file "$frontend_pid_file" || true)"

  if [[ -n "$backend_pid" ]] && test_backend_ready; then
    backend_ready=true
  fi

  if [[ -n "$frontend_pid" ]] && test_frontend_ready; then
    frontend_ready=true
  fi

  if [[ -n "$backend_pid" ]]; then
    if $backend_ready; then
      write_success_line "Backend watch is running. PID: $backend_pid"
    else
      write_warn_line "Backend watch PID exists, but the API is not ready yet. PID: $backend_pid"
    fi
    write_path_line 'Log: ' "$backend_log_file"
    write_path_line 'Errors: ' "$backend_error_log_file"
    write_path_line 'Supervisor: ' "$backend_supervisor_log_file"
  fi

  if [[ -n "$frontend_pid" ]]; then
    if $frontend_ready; then
      write_success_line "Frontend watch is running. PID: $frontend_pid"
    else
      write_warn_line "Frontend watch PID exists, but the server is not ready yet. PID: $frontend_pid"
    fi
    write_path_line 'Log: ' "$frontend_log_file"
    write_path_line 'Errors: ' "${frontend_log_file}.err"
  fi

  if ! $backend_ready || ! $frontend_ready; then
    write_warn_line 'Could not confirm readiness for both servers. Check the logs in .runtime.'
  fi

  printf '\n'
  write_url_line 'Backend URL:  ' "$backend_url"
  write_url_line 'Frontend URL: ' "$frontend_url"
}

start_watch_process() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"
  local working_directory="$4"
  local health_check_name="$5"
  local existing_pid process_id

  shift 5

  existing_pid="$(get_pid_from_file "$pid_file" || true)"
  if [[ -n "$existing_pid" ]]; then
    if [[ -n "$health_check_name" ]] && ! "$health_check_name"; then
      write_warn_line "$name was found by PID, but is not responding. Restarting. PID: $existing_pid"
      stop_process_tree "$existing_pid"
      rm -f "$pid_file"
    else
      write_info_line "$name is already running. PID: $existing_pid"
      write_path_line 'Log: ' "$log_file"
      return 0
    fi
  fi

  rm -f "$log_file" "${log_file}.err"

  (
    cd "$working_directory"
    nohup "$@" >>"$log_file" 2>>"${log_file}.err" < /dev/null &
    printf '%s\n' "$!" > "$pid_file"
  )

  process_id="$(get_pid_from_file "$pid_file")"

  write_success_line "$name started. PID: $process_id"
  write_path_line 'Log: ' "$log_file"
  write_path_line 'Errors: ' "${log_file}.err"
}

resolve_python_exe() {
  if [[ -x "$project_root/.venv/bin/python" ]]; then
    printf '%s\n' "$project_root/.venv/bin/python"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  return 1
}

if $backend_watch; then
  [[ -x "$backend_watch_python" ]] || fail "Python executable not found: $backend_watch_python"
  require_command find
  require_command pgrep
  require_command stat
  invoke_backend_watch "$backend_watch_python"
  exit 0
fi

if ! $bootstrap; then
  local_bootstrap_pid=""
  existing_backend_pid="$(get_pid_from_file "$backend_pid_file" || true)"
  existing_frontend_pid="$(get_pid_from_file "$frontend_pid_file" || true)"

  if [[ -n "$existing_backend_pid" || -n "$existing_frontend_pid" ]]; then
    for _ in {1..50}; do
      if [[ -n "$existing_backend_pid" && -n "$existing_frontend_pid" ]] && test_backend_ready && test_frontend_ready; then
        show_start_summary
        exit 0
      fi

      sleep 0.1
      existing_backend_pid="$(get_pid_from_file "$backend_pid_file" || true)"
      existing_frontend_pid="$(get_pid_from_file "$frontend_pid_file" || true)"
    done

    write_warn_line 'PID files were found, but server readiness was not confirmed. Starting recovery.'
  fi

  rm -f "$bootstrap_log_file" "$bootstrap_error_log_file"

  nohup bash "$script_path" --bootstrap >"$bootstrap_log_file" 2>"$bootstrap_error_log_file" < /dev/null &
  local_bootstrap_pid="$!"

  for _ in {1..50}; do
    backend_pid="$(get_pid_from_file "$backend_pid_file" || true)"
    frontend_pid="$(get_pid_from_file "$frontend_pid_file" || true)"
    if [[ -n "$backend_pid" && -n "$frontend_pid" ]] && test_backend_ready && test_frontend_ready; then
      break
    fi

    if [[ -n "$local_bootstrap_pid" ]] && ! test_process_running "$local_bootstrap_pid"; then
      break
    fi

    sleep 0.1
  done

  backend_pid="$(get_pid_from_file "$backend_pid_file" || true)"
  frontend_pid="$(get_pid_from_file "$frontend_pid_file" || true)"

  if [[ -n "$local_bootstrap_pid" ]] && ! test_process_running "$local_bootstrap_pid" && [[ -z "$backend_pid" || -z "$frontend_pid" ]]; then
    if [[ -s "$bootstrap_error_log_file" ]]; then
      cat "$bootstrap_error_log_file" >&2
    elif [[ -s "$bootstrap_log_file" ]]; then
      cat "$bootstrap_log_file"
    else
      write_warn_line 'Bootstrap process exited before the servers became ready.'
    fi
    exit 1
  fi

  show_start_summary
  exit 0
fi

require_command bash
require_command find
require_command node
require_command nohup
require_command pgrep
require_command stat

python_exe="$(resolve_python_exe || true)"
[[ -n "$python_exe" ]] || fail 'Python executable not found. Expected .venv/bin/python or python3 in PATH.'

if ! "$python_exe" -c 'import fastapi, sqlalchemy, uvicorn' >/dev/null 2>&1; then
  fail "Python environment is missing required backend packages: $python_exe"
fi

vite_bin="$frontend_root/node_modules/.bin/vite"
[[ -x "$vite_bin" ]] || fail "Vite executable not found: $vite_bin"

start_watch_process \
  'Backend watch' \
  "$backend_pid_file" \
  "$backend_supervisor_log_file" \
  "$project_root" \
  test_backend_ready \
  bash "$script_path" --backend-watch "$python_exe"

start_watch_process \
  'Frontend watch' \
  "$frontend_pid_file" \
  "$frontend_log_file" \
  "$frontend_root" \
  test_frontend_ready \
  env "VITE_API_BASE_URL=$backend_url" "$vite_bin" --host 127.0.0.1 --port 5173 --strictPort