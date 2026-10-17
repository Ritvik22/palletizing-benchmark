"""Exercise the bytecode API in separate processes against a persistent disk."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleasePersistenceTest(unittest.TestCase):
    def run_process(self, env, script):
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_published_release_survives_process_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, DATA_DIR=directory, SECRET_KEY='test-only-key')
            env.pop('DATABASE_URL', None)
            self.run_process(env, '''
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal, engine
from types import SimpleNamespace
from backend.auth import require_admin
app.dependency_overrides[require_admin] = lambda: SimpleNamespace(username='diagnostic')
client = TestClient(app)
r = client.post('/releases/', json={'name': 'Persistent release'})
assert r.status_code == 201, (r.status_code, r.text)
assert client.get('/public/releases/').json()[0]['name'] == 'Persistent release'
engine.dispose()
''')
            self.run_process(env, '''
from fastapi.testclient import TestClient
import serve
client = TestClient(serve.app)
r = client.get('/public/releases/')
assert r.status_code == 200 and r.json()[0]['name'] == 'Persistent release', r.text
rid = r.json()[0]['id']
assert client.get(f'/public/releases/{rid}').status_code == 200
assert client.get(f'/public/releases/{rid}/download/dataset.json').status_code == 200
assert len(client.get('/viz-api/skus').json()) == 500
''')

    def test_database_url_is_honored(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'explicit.db'
            env = dict(os.environ, DATABASE_URL=f'sqlite:///{target}', DATA_DIR='/unused')
            self.run_process(env, '''
import os
from backend.database import engine, DATABASE_URL
assert DATABASE_URL == os.environ['DATABASE_URL']
with engine.begin() as connection:
    connection.exec_driver_sql('CREATE TABLE explicit_database (id INTEGER)')
''')
            self.assertTrue(target.exists())

    def test_bundled_release_is_public_on_fresh_deploys(self):
        # Each directory represents a fresh free-tier container seeded from Git.
        for _ in range(2):
            with tempfile.TemporaryDirectory() as directory:
                env = dict(os.environ, DATA_DIR=directory, SECRET_KEY='test-only-key')
                env.pop('DATABASE_URL', None)
                self.run_process(env, '''
from fastapi.testclient import TestClient
from backend.main import app
client = TestClient(app)
releases = client.get('/public/releases/').json()
r = next(r for r in releases if r['slug'] == 'palletizing-benchmark-v1')
assert (r['sku_count'], r['order_count']) == (500, 1000)
data = client.get(f"/public/releases/{r['id']}").json()
assert len(data['skus']) == 500 and len(data['orders']) == 1000
for file in ['dataset.json', 'skus.csv', 'orders.csv']:
    response = client.get(f"/public/releases/{r['id']}/download/{file}")
    assert response.status_code == 200 and len(response.content) > 1000
''')


if __name__ == '__main__':
    unittest.main()
