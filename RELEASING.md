# Releasing (TestPyPI -> PyPI)

## One-time setup

- Create API tokens on TestPyPI and PyPI.
- Add GitHub Actions secrets:
  - TEST_PYPI_API_TOKEN
  - PYPI_API_TOKEN (optional for real PyPI later)

## Local build + TestPyPI upload

```bash
# Clean old builds
rmdir /s /q dist build 2>nul

# Build
python -m pip install -U pip
python -m pip install -e ".[release]"
python -m build
python -m twine check dist/*

# Upload to TestPyPI
python -m twine upload --repository testpypi dist/*
```

## Install from TestPyPI

```bash
python -m pip install -i https://test.pypi.org/simple/ synesis-lsp --extra-index-url https://pypi.org/simple
```

## GitHub Actions (TestPyPI)

- Run the workflow "Publish to TestPyPI" manually or trigger it on a prerelease tag.
- Ensure TEST_PYPI_API_TOKEN is set in repo secrets.

## PyPI (after TestPyPI validation)

```bash
# Upload to real PyPI
python -m twine upload dist/*
```
