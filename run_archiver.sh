#!/usr/bin/env bash

# ==============================================================================
# Run Record Archiver Execution Script
# ==============================================================================
# This script is the recommended way to run the Run Record Archiver application.
# It handles all necessary environment setup, including sourcing the artdaq
# software stack and managing a local Python virtual environment.
#
# All command-line arguments passed to this script will be forwarded directly
# to the 'run-record-archiver' Python application.
# ==============================================================================

# --- Script Configuration ---
# Stop the script if any command fails
set -e
# Ensure that pipelines fail on the first command that fails
set -o pipefail

# --- User Configuration ---
# PLEASE EDIT THE FOLLOWING VARIABLES TO MATCH YOUR SYSTEM'S ENVIRONMENT
#
# Path to the main setup script for your artdaq software stack (UPS or Spack).
# Example for DUNE CVMFS: "/cvmfs/dune.opensciencegrid.org/products/dune/setup_dune.sh"
ARTDAQ_SETUP_PATH="/path/to/your/experiment/setup"

# The version of the artdaq_database product to set up.
ARTDAQ_DB_VERSION="v1_11_02"

# The qualifiers for the artdaq_database product.
# Example: "e20:prof:s122"
ARTDAQ_DB_QUALS="e20:prof:s122"


# --- Script Logic ---

# 1. Determine the script's location to find other project files.
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
echo "INFO: Project root directory is: ${SCRIPT_DIR}"

# 2. Source the artdaq software environment.
# This is a critical step to make the 'conftoolp' library available.
echo "INFO: Sourcing artdaq environment..."
if [ ! -f "${ARTDAQ_SETUP_PATH}" ]; then
    echo "ERROR: ARTDAQ_SETUP_PATH not found at '${ARTDAQ_SETUP_PATH}'"
    echo "ERROR: Please edit this script to provide the correct path."
    exit 1
fi

# shellcheck source=/dev/null
source "${ARTDAQ_SETUP_PATH}"
setup artdaq_database "${ARTDAQ_DB_VERSION}" -q "${ARTDAQ_DB_QUALS}"

# Verify that the environment was set up correctly
if ! command -v conftoolp &> /dev/null; then
    echo "ERROR: 'conftoolp' command not found after sourcing the environment."
    echo "ERROR: Please check your ARTDAQ_SETUP_PATH, ARTDAQ_DB_VERSION, and ARTDAQ_DB_QUALS."
    exit 1
fi
echo "INFO: artdaq environment setup successful."

# 3. Set up and activate the Python virtual environment.
VENV_DIR="${SCRIPT_DIR}/.venv"
if [ ! -d "${VENV_DIR}" ]; then
    echo "INFO: Python virtual environment not found. Creating it now..."
    python3 -m venv "${VENV_DIR}"
    echo "INFO: Activating new virtual environment."
    # shellcheck source=/dev/null
    source "${VENV_DIR}/bin/activate"
    echo "INFO: Installing/updating Python dependencies..."
    pip install --upgrade pip
    # Install the project in editable mode, which handles all dependencies
    # from pyproject.toml, including the git-based ucondb dependency.
    pip install -e "${SCRIPT_DIR}"
    echo "INFO: Dependency installation complete."
else
    # shellcheck source=/dev/null
    source "${VENV_DIR}/bin/activate"
    echo "INFO: Activated existing Python virtual environment."
fi

# 4. Execute the main application, passing all script arguments to it.
# The 'exec' command replaces the shell process with the python process.
echo "INFO: Starting the Run Record Archiver application..."
echo "----------------------------------------------------------------------"

exec run-record-archiver "$@"
