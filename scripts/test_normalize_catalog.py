import json
from pathlib import Path
import tempfile
import unittest

from normalize_catalog import normalize_compose, normalize_manifest, plan, yaml_parser


class NormalizeTests(unittest.TestCase):
    def convert(self, service):
        text = 'services:\n  app:\n' + ''.join('    ' + line + '\n' for line in service.splitlines())
        result = normalize_compose(text)
        self.assertEqual(normalize_compose(result), result)
        return yaml_parser().load(result)['services']['app']

    def test_main_port(self):
        service = self.convert('image: app\nx-runtipi:\n  is_main: true\n  internal_port: 8000')
        self.assertEqual(service['ports'], ['${APP_PORT}:8000'])
        self.assertNotIn('x-runtipi', service)

    def test_auxiliary_ports_preserved(self):
        service = self.convert('ports:\n  - "53:53/udp"\nx-runtipi:\n  is_main: true\n  internal_port: 80')
        self.assertEqual(service['ports'], ['53:53/udp', '${APP_PORT}:80'])

    def test_existing_mapping_not_duplicated(self):
        for mapping in ['"127.0.0.1:8235:8000/tcp"', '{target: 8000, published: "${APP_PORT}", protocol: tcp}']:
            service = self.convert('ports:\n  - ' + mapping + '\nx-runtipi:\n  is_main: true\n  internal_port: 8000')
            self.assertEqual(len(service['ports']), 1)

    def test_host_network_does_not_publish(self):
        service = self.convert('network_mode: host\nx-runtipi:\n  is_main: true\n  internal_port: 45876')
        self.assertNotIn('ports', service)
        self.assertEqual(service['network_mode'], 'host')

    def test_unknown_metadata_refused(self):
        with self.assertRaises(ValueError):
            self.convert('x-runtipi:\n  is_main: true\n  internal_port: 80\n  extra: true')

    def test_manifest_keeps_other_fields(self):
        text = '{\n  "name": "App",\n  "dynamic_config": true,\n  "uid": 1000\n}\n'
        result = normalize_manifest(text)
        self.assertEqual(json.loads(result), {'name': 'App', 'uid': 1000})
        self.assertEqual(normalize_manifest(result), result)

    def test_invalid_file_prevents_partial_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'app').mkdir()
            manifest = root/'app/manifest.json'
            text = '{\n "dynamic_config": true,\n "name": "App"\n}\n'
            manifest.write_text(text)
            (root/'app/docker-compose.yml').write_text('services: []')
            with self.assertRaises(ValueError):
                plan(root)
            self.assertEqual(manifest.read_text(), text)


if __name__ == '__main__':
    unittest.main()
