#!/bin/bash

# Function to check if a directory exists
check_dir() {
    if [ ! -d "$1" ]; then
        echo "Directory $1 not found!"
        exit 1
    fi
}

# Function to install requirements
install_requirements() {
    if [ -f "$1/requirements.txt" ]; then
        echo "Installing requirements for $2..."
        pip install -r "$1/requirements.txt"
    else
        echo "No requirements.txt found in $1"
    fi
}

# Function to start a server
start_server() {
    echo "Starting $1 server..."
    python "$2" &
    sleep 2  # Give the server time to start
}

# Check if directories exist
check_dir "esma_mcp"
check_dir "csrc_mcp"
check_dir "common_tools_mcp"

# Install requirements for each server
install_requirements "esma_mcp" "ESMA"
install_requirements "csrc_mcp" "CSRC"
install_requirements "common_tools_mcp" "Common Tools"

# Start each server
start_server "ESMA" "esma_mcp/src/esma_server.py"
start_server "CSRC" "csrc_mcp/src/csrc_server.py"
start_server "Common Tools" "common_tools_mcp/src/common_tools_server.py"

# Wait for all background processes
wait
