"""Unit tests for the XR_RATE_LIMIT configuration plumbing in plugins/__init__.py."""

import os
import subprocess
import sys
import types
import unittest
from unittest import mock

from plugins import DEFAULT_RATE, _configured_rate, _valid_rate

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_without_rate():
    return {k: v for k, v in os.environ.items() if k != 'XR_RATE_LIMIT'}


class ValidRateTest(unittest.TestCase):
    def test_accepts_consumer_grammar_variants(self):
        # These forms are accepted by limits.parse_many (the actual
        # enforcement parser); the validator must accept them too.
        for value in ('50/minute;3000/hour;72000/day',
                      '10/second',
                      '5 per minute',
                      '1 per 3 seconds',
                      '50/minutes'):
            self.assertTrue(_valid_rate(value), value)

    def test_rejects_garbage_and_empty(self):
        for value in ('', '   ', 'not-a-rate', 'abc/minute'):
            self.assertFalse(_valid_rate(value), repr(value))

    def test_rejects_non_positive_amounts(self):
        # parse_many accepts zero amounts; a zero limit bricks every
        # request, so it must be treated as invalid config instead.
        for value in ('0/minute', '0/hour;50/minute'):
            self.assertFalse(_valid_rate(value), value)


class ConfiguredRateTest(unittest.TestCase):
    def test_env_used_when_uwsgi_absent(self):
        with mock.patch.dict(sys.modules, {'uwsgi': None}), \
                mock.patch.dict(os.environ, {'XR_RATE_LIMIT': '6000/minute'}):
            self.assertEqual(_configured_rate(), '6000/minute')

    def test_default_when_unconfigured(self):
        with mock.patch.dict(sys.modules, {'uwsgi': None}), \
                mock.patch.dict(os.environ, _env_without_rate(), clear=True):
            self.assertEqual(_configured_rate(), DEFAULT_RATE)

    def test_uwsgi_bytes_key_wins_over_env(self):
        fake = types.SimpleNamespace(opt={b'XR_RATE_LIMIT': b'99/hour'})
        with mock.patch.dict(sys.modules, {'uwsgi': fake}), \
                mock.patch.dict(os.environ, {'XR_RATE_LIMIT': '6000/minute'}):
            self.assertEqual(_configured_rate(), '99/hour')

    def test_uwsgi_str_key_used(self):
        fake = types.SimpleNamespace(opt={'XR_RATE_LIMIT': '42/day'})
        with mock.patch.dict(sys.modules, {'uwsgi': fake}), \
                mock.patch.dict(os.environ, _env_without_rate(), clear=True):
            self.assertEqual(_configured_rate(), '42/day')

    def test_undecodable_bytes_skipped_not_fatal(self):
        fake = types.SimpleNamespace(opt={b'XR_RATE_LIMIT': b'\xff\xfe\xfd'})
        with mock.patch.dict(sys.modules, {'uwsgi': fake}), \
                mock.patch.dict(os.environ, _env_without_rate(), clear=True):
            self.assertEqual(_configured_rate(), DEFAULT_RATE)


class ModuleWiringTest(unittest.TestCase):
    def test_invalid_env_warns_and_falls_back_to_default(self):
        # End-to-end through module import: an invalid value must warn on
        # stderr and leave the enforced constant at the public default.
        code = "import plugins; print(plugins.XR_RATE_LIMIT)"
        result = subprocess.run(
            [sys.executable, '-c', code],
            env={**os.environ, 'XR_RATE_LIMIT': 'garbage!!'},
            capture_output=True, text=True, cwd=_REPO_ROOT, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(DEFAULT_RATE, result.stdout.strip())
        self.assertIn('invalid XR_RATE_LIMIT', result.stderr)

    def test_valid_env_is_enforced(self):
        code = "import plugins; print(plugins.XR_RATE_LIMIT)"
        result = subprocess.run(
            [sys.executable, '-c', code],
            env={**os.environ, 'XR_RATE_LIMIT': '6000/minute'},
            capture_output=True, text=True, cwd=_REPO_ROOT, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '6000/minute')


if __name__ == '__main__':
    unittest.main()
