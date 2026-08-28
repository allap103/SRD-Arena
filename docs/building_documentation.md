# Building the documentation

The documentation environment is part of the project's development dependency
group. Build the HTML site from the repository root:

```powershell
uv run sphinx-build --fail-on-warning --builder html docs docs/_build/html
```

Open `docs/_build/html/index.html` in a browser to inspect the result. The API
reference uses Sphinx autodoc to read the intentional application, engine,
content, and domain facades. This keeps internal modules and package re-exports
from appearing as competing public definitions. Rendered HTML does not belong
in version control.

Pytest remains the authoritative runner for doctests embedded in Python
docstrings:

```powershell
uv run pytest
```

Sphinx renders those examples in the API reference, but the HTML build does not
execute them. The Python examples rely on the owning module's namespace, which
pytest supplies and Sphinx's separate documentation namespaces do not. Keeping
pytest authoritative avoids duplicating imports and setup solely for a second
runner.

Documentation-only examples can still use Sphinx's `doctest`, `testsetup`, and
`testcleanup` directives if the site later needs independently executable
examples with explicit setup.
