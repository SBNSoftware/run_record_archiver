#!/usr/bin/env bash


set -e
set -o pipefail

ulimit -c 0

export LANG=en_US.UTF-8
export LANGUAGE=en_US.UTF-8
export LC_ALL=en_US.UTF-8

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

log_info() {
  if [[ "${QUIET}" != "true" ]]; then
    echo "$@"
  fi
}

log_info "INFO: Project root directory: ${SCRIPT_DIR}"

ENV_FILE="${SCRIPT_DIR}/archiver.env"
if [[ -f "${ENV_FILE}" ]]; then
  log_info "INFO: Loading environment variables from ${ENV_FILE}"
  set -a
  source "${ENV_FILE}"
  set +a
else
  log_info "INFO: No archiver.env file found, using system environment"
fi

INIT_VENV=false
QUIET=false
FILTERED_ARGS=()
HAS_CONFIG=false
IS_HELP=false

VALID_FLAGS=(
  "-h" "--help" "/?" "/h" "/help"
  "-v" "--verbose"
  "-q" "--quiet"
  "--incremental"
  "--compare-state"
  "--validate"
  "--import-only"
  "--migrate-only"
  "--retry-failed-import"
  "--retry-failed-migrate"
  "--report-status"
  "--recover-import-state"
  "--recover-migrate-state"
)

for arg in "$@"; do
  if [[ "$arg" == "--init-venv" ]]; then
    INIT_VENV=true
  elif [[ "$arg" == "--quiet" ]] || [[ "$arg" == "-q" ]]; then
    QUIET=true
  else
    FILTERED_ARGS+=("$arg")

    if [[ "$arg" == "-h" ]] || [[ "$arg" == "--help" ]] || [[ "$arg" == "/?" ]] || [[ "$arg" == "/h" ]] || [[ "$arg" == "/help" ]]; then
      IS_HELP=true
    fi

    is_flag=false
    for flag in "${VALID_FLAGS[@]}"; do
      if [[ "$arg" == "$flag" ]]; then
        is_flag=true
        break
      fi
    done

    if [[ "$is_flag" == "false" ]]; then
      HAS_CONFIG=true
    fi
  fi
done

if [[ "${HAS_CONFIG}" == "false" ]] && [[ "${IS_HELP}" == "false" ]]; then
  FILTERED_ARGS=("config.yaml" "${FILTERED_ARGS[@]}")
fi

VENV_DIR="${SCRIPT_DIR}/.venv"
VENV_CREATED=false

if [[ "${INIT_VENV}" == "true" ]]; then
  if [[ -d "${VENV_DIR}" ]]; then
    log_info "INFO: Deleting existing virtual environment..."
    rm -rf "${VENV_DIR}"
  fi
  log_info "INFO: Creating fresh Python virtual environment..."
  python3 -m venv "${VENV_DIR}"
  VENV_CREATED=true
elif [[ ! -d "${VENV_DIR}" ]]; then
  log_info "INFO: Creating Python virtual environment..."
  python3 -m venv "${VENV_DIR}"
  VENV_CREATED=true
else
  log_info "INFO: Using existing virtual environment..."
fi

log_info "INFO: Activating virtual environment..."
source "${VENV_DIR}/bin/activate"
export PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH}"

if [[ -d "${SCRIPT_DIR}/lib" ]]; then
  export LD_LIBRARY_PATH="${SCRIPT_DIR}/lib:${LD_LIBRARY_PATH}"
  export PATH="${SCRIPT_DIR}/lib:${PATH}"
  log_info "INFO: Added ${SCRIPT_DIR}/lib to LD_LIBRARY_PATH and PATH"
fi

if [[ "${VENV_CREATED}" == "true" ]]; then
  log_info "INFO: Installing/updating dependencies..."
  if [[ "${QUIET}" == "true" ]]; then
    pip install --upgrade pip &>/dev/null
    pip install -r "${SCRIPT_DIR}/requirements.txt" &>/dev/null
  else
    pip install --upgrade pip
    pip install -r "${SCRIPT_DIR}/requirements.txt"
  fi
fi

log_info "INFO: Environment setup complete."

log_info "INFO: Starting Run Record Archiver..."
if [[ "${QUIET}" == "true" ]]; then
  exec python -m run_record_archiver "${FILTERED_ARGS[@]}" &>/dev/null
else
  exec python -m run_record_archiver "${FILTERED_ARGS[@]}"
fi
