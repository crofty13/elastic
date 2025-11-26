#!/bin/bash

echo "Setting up Elasticsearch RAG Application..."
echo "==========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "Installing required packages..."
pip install -r requirements.txt

echo ""
echo "==========================================="
echo "Setup complete!"
echo ""
echo "To use the application:"
echo "  1. source venv/bin/activate"
echo "  2. source keys.sh"
echo "  3. python3 main.py"
echo ""

