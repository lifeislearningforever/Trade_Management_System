#!/bin/bash

# Activate virtual environment
source .venv/bin/activate

# Run tests with coverage
echo "Running tests with coverage..."
pytest \
    --cov=core \
    --cov=portfolio \
    --cov=reference_data \
    --cov=market_data \
    --cov=udf \
    --cov-report=term-missing \
    --cov-report=html \
    --cov-report=xml \
    --tb=short \
    -v

# Display coverage summary
echo ""
echo "======================================"
echo "Coverage Summary"
echo "======================================"
coverage report --skip-covered

# Generate HTML report
echo ""
echo "HTML coverage report generated in htmlcov/index.html"
