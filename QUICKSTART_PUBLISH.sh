#!/bin/bash
# Quick script to build and publish flask-headless-payments to PyPI

set -e

echo "🚀 Building flask-headless-payments..."

# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build the package
python -m build

echo "✅ Build complete!"
echo ""
echo "📦 Package files created in dist/:"
ls -lh dist/

echo ""
echo "To publish to PyPI:"
echo "  1. Test upload: python -m twine upload --repository testpypi dist/*"
echo "  2. Production:  python -m twine upload dist/*"
echo ""
echo "Make sure you have twine installed: pip install twine"

