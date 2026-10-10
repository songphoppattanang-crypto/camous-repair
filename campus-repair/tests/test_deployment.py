import os
import sys
import unittest
import tomllib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app


class DeploymentTests(unittest.TestCase):
    def test_dependency_lists_match(self):
        root = Path(__file__).resolve().parents[1]
        config = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
        requirements = set((root / 'requirements.txt').read_text(encoding='utf-8').splitlines())
        self.assertEqual(requirements, set(config['project']['dependencies']))
        self.assertEqual(config['tool']['vercel']['entrypoint'], 'index:app')

    def test_vercel_requires_explicit_secrets_and_remote_database(self):
        with patch.dict(os.environ, {'VERCEL':'1'}, clear=True):
            with self.assertRaises(RuntimeError):
                create_app()
        with patch.dict(os.environ, {'VERCEL':'1', 'SECRET_KEY':'test-key'}, clear=True):
            with self.assertRaises(RuntimeError):
                create_app()

    def test_vercel_factory_never_writes_to_instance_directory(self):
        with patch.dict(os.environ, {'VERCEL':'1', 'SECRET_KEY':'test-key',
                                   'DATABASE_URL':'postgresql://example.invalid/test'}, clear=True):
            with patch.object(Path, 'mkdir', side_effect=AssertionError('No runtime writes')):
                app = create_app()
        self.assertTrue(app.config['SESSION_COOKIE_SECURE'])
        self.assertEqual(app.config['SECRET_KEY'], 'test-key')


if __name__ == '__main__':
    unittest.main()
