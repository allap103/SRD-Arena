# Content schema visualization

The authored-content schemas can be inspected without reading the Pydantic model
files directly:

```powershell
uv run content-schema-docs
```

Open `build/content-schema-docs/index.html` after generation. Each bounded view
offers:

- a relationship diagram for high-level composition;
- a collapsible field reference for unions, fields, defaults, and constraints;
- the raw JSON Schema exported by Pydantic.

The views are deliberately separated by content concern. A recursive diagram of
the entire spell schema is too large to navigate, while the HTML field reference
can retain the complete detail through linked definitions.

Generate one or more views while working on a specific concern:

```powershell
uv run content-schema-docs --only spells --only spell-capabilities
```

Use `--no-diagrams` when Graphviz rendering is unavailable or only the exact
field reference is needed.
