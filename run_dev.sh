#!/bin/bash
# Omninet Development Launcher for Linux/Mac

echo "Starting Omninet Development Server..."
echo

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set environment to dev
export ENVIRONMENT=dev

# Run the server
python -m omninet.main
