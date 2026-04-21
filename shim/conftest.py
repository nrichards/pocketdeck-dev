"""Empty conftest — its presence marks shim/ as a pytest rootdir so
`pdeck_sim` resolves as a package without needing PYTHONPATH or pip install.
Duplicated by pyproject.toml's pythonpath setting on your machine; having
both doesn't hurt.
"""
