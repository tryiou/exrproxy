# Copyright (c) 2020 The Blocknet developers
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.

import logging
import os

from flask import Blueprint
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from limits import parse_many

def get_real_remote_address():
    from flask import request
    return request.headers.get('X-Forwarded-For') or request.remote_addr

limiter = Limiter(key_func=get_real_remote_address)


app = Blueprint('exr', __name__)

DEFAULT_RATE = '50/minute;3000/hour;72000/day'


def _configured_rate():
    """Rate-limit string from runtime config (uwsgi set-ph or env).

    uwsgi.opt keys are bytes; container environment reaches os.environ.
    Undecodable values are skipped, not fatal. Unconfigured deployments
    keep the historical public default.
    """
    try:
        import uwsgi  # present when running under the uwsgi entrypoint
        for key in (b'XR_RATE_LIMIT', 'XR_RATE_LIMIT'):
            value = uwsgi.opt.get(key)
            if isinstance(value, bytes):
                try:
                    value = value.decode()
                except UnicodeDecodeError:
                    continue
            if value:
                return str(value)
    except ImportError:
        pass
    return os.environ.get('XR_RATE_LIMIT') or DEFAULT_RATE


def _valid_rate(value):
    """True iff the consumer's own parser accepts every limit in the
    string and no amount is zero/negative. Validating with limits'
    grammar (not a parallel regex) keeps this in lockstep with what
    Flask-Limiter will actually enforce.
    """
    if not value:
        return False
    try:
        return all(limit.amount > 0 for limit in parse_many(value))
    except ValueError:
        return False


XR_RATE_LIMIT = _configured_rate()
if not _valid_rate(XR_RATE_LIMIT):
    logging.warning('invalid XR_RATE_LIMIT %r, falling back to default',
                    XR_RATE_LIMIT)
    XR_RATE_LIMIT = DEFAULT_RATE
limiter.limit(XR_RATE_LIMIT)(app)


@app.route('/', methods=['GET', 'POST', 'HEAD'])
def a():
    return info()


@app.route('/xr', methods=['GET', 'POST', 'HEAD'])
def b():
    return info()


@app.route('/xrs', methods=['GET', 'POST', 'HEAD'])
def c():
    return info()


@app.route('/xr/', methods=['GET', 'POST', 'HEAD'])
def d():
    return info()


@app.route('/xrs/', methods=['GET', 'POST', 'HEAD'])
def e():
    return info()


def info():
    return '<h1>Enterprise XRouter host</h1>'
