# Releasing IntelScan

IntelScan `0.1.0` is now published on PyPI and installable with:

```bash
pip install intelscan
```

Install that exact first public release with:

```bash
pip install intelscan==0.1.0
```

## One-time setup

1. Create a PyPI account at <https://pypi.org>.
2. Decide whether you want manual uploads or GitHub-based Trusted Publishing.
3. If you want Trusted Publishing, add a PyPI trusted publisher for this repository and workflow file:

```text
Repository owner: Debanshu2005
Repository name: IntelScan
Workflow filename: publish.yml
Environment name: pypi
```

PyPI docs:

- <https://docs.pypi.org/trusted-publishers/>
- <https://docs.pypi.org/trusted-publishers/adding-a-publisher/>

## Release checklist

1. Update the version in `pyproject.toml`.
2. Run the test suite:

```bash
python -m unittest -q
python -m py_compile workspace_scanner.py agent_coordinator.py src/intelscan/workspace_scanner.py src/intelscan/agent_coordinator.py
```

3. Build distributions:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

4. Optional but recommended: upload to TestPyPI first:

```bash
python -m twine upload --repository testpypi dist/*
```

5. Publish to PyPI:

Manual upload:

```bash
python -m twine upload dist/*
```

GitHub Actions Trusted Publishing:

- push the version bump
- create a GitHub release or push a `v*` tag, depending on your preferred trigger
- let `.github/workflows/publish.yml` build and publish automatically

## Notes

- `0.1.0` is the first published PyPI release for this project.
- PyPI requires each uploaded release to have a new version number.
- `twine check` catches common README and metadata issues before upload.
- Trusted Publishing is the recommended PyPI flow because it avoids long-lived API tokens.
