#!/usr/bin/env python3
"""Convert Runtipi catalog metadata to ordinary Compose; default is a dry run."""
import argparse
from collections.abc import Mapping
from io import StringIO
import json
import os
from pathlib import Path
import re
import tempfile

from ruamel.yaml import YAML


def yaml_parser():
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    return yaml


def publishes(ports, target):
    for port in ports:
        if isinstance(port, Mapping):
            if str(port.get('target')) == str(target) and port.get('protocol', 'tcp') == 'tcp' and port.get('published') is not None:
                return True
        elif isinstance(port, str):
            binding, _, protocol = port.partition('/')
            if ':' in binding and binding.rsplit(':', 1)[1] == str(target) and protocol in ('', 'tcp'):
                return True
    return False


def normalize_compose(text):
    yaml = yaml_parser()
    doc = yaml.load(text)
    if not isinstance(doc, Mapping) or not isinstance(doc.get('services'), Mapping):
        raise ValueError('expected a Compose services mapping')
    changed = False
    main_count = 0
    for name, service in doc['services'].items():
        if not isinstance(service, Mapping):
            raise ValueError(f'{name}: expected a service mapping')
        if 'x-runtipi' not in service:
            continue
        metadata = service['x-runtipi']
        if not isinstance(metadata, Mapping) or set(metadata) - {'internal_port', 'is_main'}:
            raise ValueError(f'{name}: unsupported x-runtipi metadata; review manually')
        if metadata.get('is_main') is not True:
            raise ValueError(f'{name}: no unambiguous main service; review manually')
        main_count += 1
        if main_count > 1:
            raise ValueError('multiple main services; review manually')
        target = metadata.get('internal_port')
        if type(target) is not int or not 1 <= target <= 65535:
            raise ValueError(f'{name}: internal_port must be 1–65535')
        mode = service.get('network_mode')
        if mode == 'host':
            if service.get('ports'):
                raise ValueError(f'{name}: host networking cannot publish ports')
        elif mode is not None and mode != 'bridge':
            raise ValueError(f'{name}: cannot safely publish with network_mode={mode}')
        else:
            ports = service.setdefault('ports', [])
            if not isinstance(ports, list):
                raise ValueError(f'{name}: expected a ports list')
            if not publishes(ports, target):
                ports.append(f'${{APP_PORT}}:{target}')
        del service['x-runtipi']
        changed = True
    if not changed:
        return text
    output = StringIO()
    yaml.dump(doc, output)
    result = output.getvalue()
    yaml_parser().load(result)
    return result


def normalize_manifest(text):
    doc = json.loads(text)
    if 'dynamic_config' not in doc:
        return text
    # Remove only this retired flag, retaining all unrelated JSON formatting.
    result, count = re.subn(r'^\s*"dynamic_config"\s*:\s*(?:true|false)\s*,\s*\n', '', text, flags=re.M)
    if count != 1:
        raise ValueError('dynamic_config layout is not recognized; review manually')
    expected = dict(doc)
    del expected['dynamic_config']
    if json.loads(result) != expected:
        raise ValueError('manifest transformation changed unrelated values')
    return result


def plan(root):
    updates = []
    for manifest in sorted(root.glob('*/manifest.json')):
        text = manifest.read_text()
        converted = normalize_manifest(text)
        if converted != text:
            updates.append((manifest, converted))
        for path in sorted(manifest.parent.glob('docker-compose*.y*ml')):
            text = path.read_text()
            try:
                converted = normalize_compose(text)
            except Exception as error:
                raise ValueError(f'{path.relative_to(root)}: {error}') from error
            if converted != text:
                updates.append((path, converted))
    return updates


def write_atomic(path, text):
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as file:
            file.write(text)
            os.fchmod(file.fileno(), path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--write', action='store_true', help='apply changes after validating the entire catalog')
    mode.add_argument('--check', action='store_true', help='exit 1 if normalization is needed')
    args = parser.parse_args()
    try:
        updates = plan(args.root)
    except (ValueError, OSError) as error:
        parser.exit(2, f'{error}\n')
    for path, text in updates:
        print(('WRITE ' if args.write else 'WOULD CHANGE ') + str(path.relative_to(args.root)))
        if args.write:
            write_atomic(path, text)
    print(f'{len(updates)} file(s) {"updated" if args.write else "need normalization"}')
    return 1 if args.check and updates else 0


if __name__ == '__main__':
    raise SystemExit(main())
