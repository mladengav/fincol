"""Local pytest hooks and notes for this repository.

Run ``pytest`` from the repository root. ``pythonpath`` in ``pyproject.toml``
includes ``src``, so imports such as ``application``, ``domain``, and
``infrastructure`` resolve against ``src/application/``, ``src/domain/``, and
``src/infrastructure/``—the same layout used when the package is installed.
Console entry points live under ``src/presentation_cli/`` (see
``[project.scripts]`` in ``pyproject.toml``).
"""
