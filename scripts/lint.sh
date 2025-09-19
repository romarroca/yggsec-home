#!/bin/bash
# Code quality and security linting script

set -e

echo "Running code quality checks..."

# Check if we're in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "Warning: Not in a virtual environment. Install tools with: pip install -r requirements.txt"
fi

# Black code formatting check
echo "Checking code formatting with black..."
black --check --diff . || {
    echo "Code formatting issues found. Run 'black .' to fix."
    exit 1
}

# Import sorting check
echo "Checking import sorting with isort..."
isort --check-only --diff . || {
    echo "Import sorting issues found. Run 'isort .' to fix."
    exit 1
}

# Flake8 linting
echo "Running flake8 linting..."
flake8 . || {
    echo "Linting issues found. Fix the issues above."
    exit 1
}

# Security check with bandit
echo "Running security analysis with bandit..."
bandit -r . -f json -o bandit-report.json || {
    echo "Security issues found. Check bandit-report.json for details."
    exit 1
}

echo "All checks passed!"