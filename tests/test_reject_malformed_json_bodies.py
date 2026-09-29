# Copyright (c) 2026 The Blocknet developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.

"""Body-guard tests for the evm_passthrough and xquery routes.

A missing, malformed, or wrong-mimetype JSON body must be rejected with
the missing-parameters error BEFORE any backend round-trip, instead of
being forwarded to the backend with an empty body. Infrastructure the
handlers need at import time (the uwsgi worker module, project
auth/database) is stubbed at module import; what runs under test is the
real guard code in both route modules.
"""

import sys
import types
import unittest
from functools import wraps
from types import SimpleNamespace
from unittest import mock

from flask import Flask, g


def _install_stubs():
    if 'uwsgi' not in sys.modules:
        uwsgi = types.ModuleType('uwsgi')
        uwsgi.opt = {}
        sys.modules['uwsgi'] = uwsgi

    middleware_name = 'plugins.projects.middleware'
    if middleware_name not in sys.modules:
        middleware = types.ModuleType(middleware_name)

        def authenticate(view):
            @wraps(view)
            def wrapper(*args, **kwargs):
                g.project = SimpleNamespace(api_token_count=10,
                                            used_api_tokens=2)
                return view(*args, **kwargs)
            return wrapper

        middleware.authenticate = authenticate
        sys.modules[middleware_name] = middleware

    handler_name = 'plugins.projects.util.request_handler'
    if handler_name not in sys.modules:
        handler_mod = types.ModuleType(handler_name)

        class RequestHandler:
            def post_update_api_count(self, project_id):
                return {}

        handler_mod.RequestHandler = RequestHandler
        sys.modules[handler_name] = handler_mod

    models_name = 'plugins.projects.database.models'
    if models_name not in sys.modules:
        models = types.ModuleType(models_name)
        models.db_session = mock.MagicMock(name='db_session')
        models.select = mock.MagicMock(name='select')
        models.Project = mock.MagicMock(name='Project')
        sys.modules[models_name] = models


_install_stubs()

from plugins.evm_passthrough import routes as evm_routes  # noqa: E402
from plugins.xquery import routes as xquery_routes  # noqa: E402


def _record_backend():
    """Patch requests.post with a recording stub backend.

    Records calls instead of raising: both route handlers swallow all
    exceptions into a generic error body, so a raising stub would be
    indistinguishable from any other backend failure. Asserting a zero
    call count proves no backend round-trip was paid.
    """

    class _FakeBackend:
        def __init__(self):
            self.headers = {}

        def json(self):
            return {'data': {}}

    return mock.patch('requests.post', return_value=_FakeBackend())


class EvmPassthroughBodyGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = Flask(__name__)
        app.register_blueprint(evm_routes.app)
        cls.client = app.test_client()

    def _post(self, body, content_type='application/json'):
        return self.client.post('/xrs/evm_passthrough/ETH/PID',
                                data=body, content_type=content_type)

    def test_malformed_json_rejected_without_backend(self):
        with _record_backend() as post:
            resp = self._post('{this is not valid json}')
        self.assertEqual(post.call_count, 0)
        self.assertIn('missing parameters', resp.get_data(as_text=True))

    def test_empty_body_rejected_without_backend(self):
        with _record_backend() as post:
            resp = self._post('')
        self.assertEqual(post.call_count, 0)
        self.assertIn('missing parameters', resp.get_data(as_text=True))

    def test_wrong_mimetype_rejected_without_backend(self):
        with _record_backend() as post:
            resp = self._post('{"jsonrpc": "2.0"}', content_type='text/plain')
        self.assertEqual(post.call_count, 0)
        self.assertIn('missing parameters', resp.get_data(as_text=True))

    def test_valid_body_passes_guard_to_handler(self):
        with _record_backend() as post:
            resp = self._post('{"jsonrpc": "2.0", "method": "eth_blockNumber",'
                              ' "params": [], "id": 1}')
        self.assertEqual(post.call_count, 0)
        # ETH is not in the (empty stub) HYDRA config, so the handler itself
        # answers; the point is the guard let a good body through and no
        # backend was touched.
        self.assertIn('not found in HYDRA', resp.get_data(as_text=True))


class XqueryBodyGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = Flask(__name__)
        app.register_blueprint(xquery_routes.app)
        cls.client = app.test_client()

    def _post(self, body, content_type='application/json'):
        return self.client.post('/xrs/xquery/PID/indexer',
                                data=body, content_type=content_type)

    def test_malformed_json_rejected_without_backend(self):
        with _record_backend() as post:
            resp = self._post('{this is not valid json}')
        self.assertEqual(post.call_count, 0)
        self.assertIn('missing parameters', resp.get_data(as_text=True))

    def test_empty_body_rejected_without_backend(self):
        with _record_backend() as post:
            resp = self._post('')
        self.assertEqual(post.call_count, 0)
        self.assertIn('missing parameters', resp.get_data(as_text=True))

    def test_wrong_mimetype_rejected_without_backend(self):
        with _record_backend() as post:
            resp = self._post('{"query": "{ x }"}', content_type='text/plain')
        self.assertEqual(post.call_count, 0)
        self.assertIn('missing parameters', resp.get_data(as_text=True))

    def test_valid_body_reaches_backend_intact(self):
        sent = {'query': '{ x }'}

        class _FakeBackend:
            def __init__(self, payload):
                self.payload = payload
                self.headers = {}

            def json(self):
                return {'data': self.payload}

        with mock.patch('requests.post',
                        return_value=_FakeBackend(sent)) as post:
            resp = self._post('{"query": "{ x }"}')
        post.assert_called_once()
        _, kwargs = post.call_args
        self.assertEqual(kwargs.get('json'), sent)
        self.assertEqual(resp.status_code, 200)


if __name__ == '__main__':
    unittest.main()
