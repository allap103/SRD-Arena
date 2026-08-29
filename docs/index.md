# SRD Arena

SRD Arena is a Python combat simulator for the 2024 rules represented by SRD
5.2. The project provides an interactive graphical client and a frontend-neutral
application boundary intended for simulations and future machine-learning
integration.

This site combines the project's authored design documents with an API reference
generated from the source docstrings. Examples beginning with `>>>` are the same
doctests executed by the test suite.

```{toctree}
:maxdepth: 2
:caption: Architecture

application_architecture
frontend_architecture
combat_action_architecture
glossary
```

```{toctree}
:maxdepth: 2
:caption: Rules model

conditions
aoe
rules_interpretation
rules_deviations
```

```{toctree}
:maxdepth: 2
:caption: Authored content

bestiary_action_capability_schema
bestiary_multiattack_schema
spell_capability_schema
spell_mechanics_coverage
spell_implementation_batches
content-schema-visualization
```

```{toctree}
:maxdepth: 1
:caption: Historical design records

capability_effect_system
```

```{toctree}
:maxdepth: 3
:caption: Developer reference

doctest_policy
building_documentation
api
```
