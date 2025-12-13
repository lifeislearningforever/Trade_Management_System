#!/bin/bash
# Trade Management System Startup Script
# This script starts the application without requiring Django admin

echo "==========================================="
echo "Trade Management System V1"
echo "==========================================="
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if database is accessible
echo "Checking database connection..."
python manage.py check --database default

if [ $? -ne 0 ]; then
    echo "❌ Database connection failed!"
    echo "Please check your MySQL configuration in settings.py"
    exit 1
fi

echo "✅ Database connection successful!"
echo ""

# Run migrations if needed
echo "Checking for pending migrations..."
PENDING=$(python manage.py showmigrations --plan 2>&1 | grep "No planned migration operations")
if [ -z "$PENDING" ]; then
    echo "Running migrations..."
    python manage.py migrate
fi

echo ""
echo "==========================================="
echo "Application Ready!"
echo "==========================================="
echo ""
echo "Test Accounts:"
echo "  Maker:   username=maker1,   password=Test@1234"
echo "  Checker: username=checker1, password=Test@1234"
echo "  Admin:   username=admin1,   password=Admin@1234"
echo ""
echo "Starting development server on port 8001..."
echo "Access at: http://127.0.0.1:8001/login/"
echo ""
echo "Press Ctrl+C to stop the server"
echo "==========================================="
echo ""

# Start the development server
python manage.py runserver 8001
