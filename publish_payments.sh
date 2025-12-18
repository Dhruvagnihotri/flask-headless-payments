#!/bin/bash
# Publish flask-headless-payments to PyPI
# Usage: export PYPI_TOKEN="your-token-here" && ./publish_payments.sh

set -e

if [ -z "$PYPI_TOKEN" ]; then
    echo "❌ Error: PYPI_TOKEN environment variable not set"
    echo "Usage: export PYPI_TOKEN=\"your-token-here\" && ./publish_payments.sh"
    exit 1
fi

echo "🚀 Publishing flask-headless-payments to PyPI..."
echo ""

# Get version from __version__.py
VERSION=$(python -c "import re; content = open('flask_headless_payments/__version__.py').read(); print(re.search(r'__version__\s*=\s*[\"']([^\"']+)[\"']', content).group(1))")
echo "📦 Version: $VERSION"
echo ""

# Clean previous builds
echo "🧹 Cleaning old builds..."
rm -rf dist/ build/ *.egg-info flask_headless_payments.egg-info
echo ""

# Update pyproject.toml version
echo "📝 Updating pyproject.toml version..."
python -c "
import re
with open('pyproject.toml', 'r') as f:
    content = f.read()
content = re.sub(r'(^version = \")[^\"]+', f'\\1${VERSION}', content, flags=re.MULTILINE)
with open('pyproject.toml', 'w') as f:
    f.write(content)
"
echo ""

# Build the package
echo "🔨 Building package..."
python -m build
echo ""

# Upload to PyPI
echo "📤 Uploading to PyPI..."
python -m twine upload --username __token__ --password "${PYPI_TOKEN}" dist/*
echo ""

echo "✅ Successfully published flask-headless-payments v${VERSION}!"
echo "🔗 View at: https://pypi.org/project/flask-headless-payments/${VERSION}/"



