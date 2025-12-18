# Contributing to Flask-Headless-Payments

Thank you for your interest in contributing to Flask-Headless-Payments!

## 🚀 Getting Started

1. **Fork the repository**
2. **Clone your fork:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/flask-headless-payments.git
   cd flask-headless-payments
   ```

3. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. **Install dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

## 🧪 Running Tests

```bash
pytest
pytest --cov=flask_headless_payments  # With coverage
```

## 📝 Code Style

We use:
- **Black** for code formatting
- **Flake8** for linting

Before submitting, run:
```bash
black flask_headless_payments/
flake8 flask_headless_payments/
```

## 🔧 Development Workflow

1. Create a new branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes

3. Run tests:
   ```bash
   pytest
   ```

4. Commit your changes:
   ```bash
   git commit -m "Add: your feature description"
   ```

5. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

6. Open a Pull Request

## 📋 Pull Request Guidelines

- Keep changes focused and atomic
- Add tests for new features
- Update documentation as needed
- Follow existing code style
- Write clear commit messages

## 🐛 Reporting Bugs

Open an issue with:
- Clear description of the bug
- Steps to reproduce
- Expected vs actual behavior
- Python version and dependencies
- Code snippet if applicable

## 💡 Feature Requests

Open an issue describing:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives considered

## 📚 Documentation

Documentation improvements are always welcome! This includes:
- README updates
- Code comments
- Example applications
- Tutorials and guides

## ❓ Questions

Have questions? Open a discussion or issue!

Thank you for contributing! 🎉

