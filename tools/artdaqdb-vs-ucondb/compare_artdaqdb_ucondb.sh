#!/usr/bin/env bash


set -e
set -o pipefail

ulimit -c 0

export LANG=en_US.UTF-8
export LANGUAGE=en_US.UTF-8
export LC_ALL=en_US.UTF-8

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
TOOLS_DIR="$(dirname "${SCRIPT_DIR}")"
PROJECT_ROOT="$(dirname "${TOOLS_DIR}")"

echo "INFO: ArtdaqDB vs UconDB comparison tool directory: ${SCRIPT_DIR}"
echo "INFO: Tools directory: ${TOOLS_DIR}"
echo "INFO: Project root: ${PROJECT_ROOT}"

ENV_FILE="${SCRIPT_DIR}/artdaqdb_ucondb.env"
if [[ -f "${ENV_FILE}" ]]; then
  echo "INFO: Loading environment variables from ${ENV_FILE}"
  set -a
  source "${ENV_FILE}"
  set +a
else
  echo "INFO: No artdaqdb_ucondb.env file found"
  echo "WARNING: This tool requires artdaq_database environment to be sourced (or use_tools: true)"
  echo "WARNING: Please ensure ARTDAQ_DATABASE_SETUP is set or create artdaqdb_ucondb.env"
fi

INIT_VENV=false
FILTERED_ARGS=()

for arg in "$@"; do
  if [[ "$arg" == "--init-venv" ]]; then
    INIT_VENV=true
  else
    FILTERED_ARGS+=("$arg")
  fi
done

VENV_DIR="${SCRIPT_DIR}/.venv"
VENV_CREATED=false

if [[ "${INIT_VENV}" == "true" ]]; then
  if [[ -d "${VENV_DIR}" ]]; then
    echo "INFO: Deleting existing virtual environment..."
    rm -rf "${VENV_DIR}"
  fi
  echo "INFO: Creating fresh Python virtual environment..."
  python3 -m venv "${VENV_DIR}"
  VENV_CREATED=true
elif [[ ! -d "${VENV_DIR}" ]]; then
  echo "INFO: Creating Python virtual environment..."
  python3 -m venv "${VENV_DIR}"
  VENV_CREATED=true
else
  echo "INFO: Using existing virtual environment..."
fi

echo "INFO: Activating virtual environment..."
source "${VENV_DIR}/bin/activate"

export PYTHONPATH="${PROJECT_ROOT}:${TOOLS_DIR}:${PROJECT_ROOT}/lib:${PYTHONPATH}"
echo "INFO: PYTHONPATH set to: ${PYTHONPATH}"

if [[ -d "${PROJECT_ROOT}/lib" ]]; then
  export LD_LIBRARY_PATH="${PROJECT_ROOT}/lib:${LD_LIBRARY_PATH}"
  echo "INFO: Added ${PROJECT_ROOT}/lib to LD_LIBRARY_PATH for bundled libraries"
fi

if [[ -d "${PROJECT_ROOT}/lib" ]]; then
  export PATH="${PROJECT_ROOT}/lib:${PATH}"
  echo "INFO: Added ${PROJECT_ROOT}/lib to PATH for CLI tools"
fi

if [[ "${VENV_CREATED}" == "true" ]]; then
  echo "INFO: Installing/updating dependencies..."
  pip install --upgrade pip
  pip install -r "${TOOLS_DIR}/requirements.txt"
fi

echo "INFO: Environment setup complete."

echo "INFO: Starting ArtdaqDB vs UconDB comparison tool..."
exec python "${SCRIPT_DIR}/compare_artdaqdb_ucondb.py" "${FILTERED_ARGS[@]}"
