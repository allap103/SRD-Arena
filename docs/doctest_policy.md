# Doctest policy

The project uses doctests as executable usage examples for concrete public
methods. `uv run pytest` collects these examples from `src/srd_arena` alongside
the ordinary unit tests. Interrogate remains a separate check for documentation
coverage: a documented method is not necessarily a doctested method.

## Expected coverage

Concrete public methods should normally include at least one short example that
demonstrates observable behavior. Examples should explain a useful contract,
boundary, or state transition rather than merely proving that an object is
callable. Complex rule interactions continue to belong in focused unit tests;
doctests complement those tests and do not replace them.

The following declarations are documented exceptions:

- Protocol and abstract method declarations, because their concrete
  implementations own the behavior being demonstrated.
- GUI framework event overrides such as `paintEvent`, `resizeEvent`, and mouse
  events, because Qt creates and invokes their event objects. Their behavior is
  covered by GUI tests rather than examples requiring a live event loop.
- Property setters when the corresponding property example already exercises
  both reading and writing the value.

These exceptions keep the requirement focused on executable project behavior
and avoid examples that only mock away the method being documented.

## Auditing coverage

Run `uv run doctest-audit` to report executable-example coverage independently
from ordinary docstring coverage. The report counts concrete public functions,
methods, and properties, while listing protocol declarations, abstract methods,
property setters, and Qt event overrides as policy exclusions.

An optional threshold makes the command suitable for a formal check without
hard-coding that policy into the tool, for example:

```text
uv run doctest-audit --fail-under 90
```
