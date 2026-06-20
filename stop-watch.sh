#!/usr/bin/env bash

set -euo pipefail

script_path="$(readlink -f "${BASH_SOURCE[0]}")"
project_root="$(cd -- "$(dirname -- "$script_path")" && pwd)"
runtime_dir="$project_root/.runtime"
frontend_root="$project_root/frontend"
backend_root="$project_root/backend"

frontend_pid_file="$runtime_dir/frontend-watch.pid"
backend_pid_file="$runtime_dir/backend-watch.pid"
pid_files=("$frontend_pid_file" "$backend_pid_file")

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

test_process_running() {
  local process_id="$1"

  kill -0 "$process_id" 2>/dev/null
}

get_pid_from_file() {
  local pid_file="$1"
  local raw_pid

  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi

  raw_pid="$(tr -d '[:space:]' < "$pid_file" 2>/dev/null || true)"
  [[ "$raw_pid" =~ ^[0-9]+$ ]] || return 1

  printf '%s\n' "$raw_pid"
}

get_project_process_ids() {
  local process_id command_line

  while IFS= read -r line; do
    process_id="${line%% *}"
    command_line="${line#* }"

    if [[ "$command_line" == *"$frontend_root"* ]] && [[ "$command_line" =~ vite|npm(\.cmd)?[[:space:]]+run[[:space:]]+dev ]]; then
      printf '%s\n' "$process_id"
      continue
    fi

    if [[ "$command_line" == *"$backend_root"* ]] || { [[ "$command_line" == *'uvicorn'* ]] && [[ "$command_line" == *'app.main:app'* ]] && [[ "$command_line" =~ --port[[:space:]]+8000 ]]; }; then
      printf '%s\n' "$process_id"
      continue
    fi

    if [[ "$command_line" == *"$project_root/start-watch.sh"* ]] && [[ "$command_line" == *'--backend-watch'* ]]; then
      printf '%s\n' "$process_id"
    fi
  done < <(ps -eo pid=,args=)
}

collect_process_tree_pids() {
  local process_id="$1"
  local child_process_id

  printf '%s\n' "$process_id"

  while IFS= read -r child_process_id; do
    [[ -n "$child_process_id" ]] || continue
    collect_process_tree_pids "$child_process_id"
  done < <(pgrep -P "$process_id" || true)
}

stop_process() {
  local process_id="$1"

  if ! test_process_running "$process_id"; then
    return 0
  fi

  kill -TERM "$process_id" 2>/dev/null || true

  for _ in {1..20}; do
    if ! test_process_running "$process_id"; then
      return 0
    fi
    sleep 0.2
  done

  kill -KILL "$process_id" 2>/dev/null || true
}

declare -A all_pids=()

for pid_file in "${pid_files[@]}"; do
  process_id="$(get_pid_from_file "$pid_file" || true)"
  if [[ -n "$process_id" ]]; then
    while IFS= read -r tree_pid; do
      [[ -n "$tree_pid" ]] || continue
      all_pids["$tree_pid"]=1
    done < <(collect_process_tree_pids "$process_id")
  fi
done

while IFS= read -r process_id; do
  [[ -n "$process_id" ]] || continue
  while IFS= read -r tree_pid; do
    [[ -n "$tree_pid" ]] || continue
    all_pids["$tree_pid"]=1
  done < <(collect_process_tree_pids "$process_id")
done < <(get_project_process_ids)

if ((${#all_pids[@]} == 0)); then
  for pid_file in "${pid_files[@]}"; do
    rm -f "$pid_file"
  done
  write_info_line 'No running frontend/backend processes were found for this project.'
  exit 0
fi

while IFS= read -r process_id; do
  [[ -n "$process_id" ]] || continue

  if ! test_process_running "$process_id"; then
    continue
  fi

  process_name="$(ps -p "$process_id" -o comm= 2>/dev/null | xargs || true)"

  stop_process "$process_id"

  if test_process_running "$process_id"; then
    write_warn_line "Could not stop PID $process_id${process_name:+ ($process_name)}"
  else
    write_success_line "Stopped PID: $process_id${process_name:+ ($process_name)}"
  fi
done < <(printf '%s\n' "${!all_pids[@]}" | sort -nr)

for pid_file in "${pid_files[@]}"; do
  rm -f "$pid_file"
done