# Catalog normalization

Install the script dependency in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python scripts/normalize_catalog.py          # preview changes
.venv/bin/python scripts/normalize_catalog.py --write  # apply
.venv/bin/python scripts/normalize_catalog.py --check  # CI: fail if changes needed
.venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
```

The script converts service-level `x-runtipi` main-service metadata into
`${APP_PORT}:<internal_port>` bindings and removes the obsolete manifest
`dynamic_config` flag. It checks every catalog manifest and Compose variant
before writing. Unknown metadata or ambiguous main services require manual
review rather than guessed changes. Repeating the migration makes no changes.

Existing port bindings, including auxiliary TCP/UDP ports, are preserved.
Host-network services retain host networking and receive no port mapping;
their listening port is controlled by the application itself. Main services
with an existing published TCP binding retain it unchanged.

Unrelated manifest values, Compose service settings, environment variables,
volumes, dependency order, quotes, and comments are retained. Modified YAML
may receive whitespace normalization. The script changes templates only;
it does not deploy, restart, or reconfigure installed applications. Review
`git diff` before publishing the catalog. The earlier 2FAuth instance's
manual runtime port override should be removed when that instance is
redeployed from its normalized template to avoid duplicate port bindings.
