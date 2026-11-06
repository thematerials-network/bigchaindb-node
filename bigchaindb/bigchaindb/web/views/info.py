# Copyright © 2020 Interplanetary Database Association e.V.,
# BigchainDB and IPDB software contributors.
# SPDX-License-Identifier: (Apache-2.0 AND CC-BY-4.0)
# Code is Apache-2.0 and docs are CC-BY-4.0

"""API Index endpoint"""

import flask
from flask_restful import Resource

from bigchaindb.web.views.base import base_ws_uri
from bigchaindb import version
from bigchaindb.web.websocket_server import EVENTS_ENDPOINT

# Upstream's versioned docs pages return 404 (v2.1.0 to v2.2.2, checked 2026-11-06); only latest is served.
DOCS_URL = 'https://docs.bigchaindb.com/projects/server/en/latest/'


class RootIndex(Resource):
    def get(self):
        return flask.jsonify({
            'api': {
                'v1': get_api_v1_info('/api/v1/')
            },
            'docs': DOCS_URL,
            'software': 'BigchainDB',
            'version': version.__version__,
        })


class ApiV1Index(Resource):
    def get(self):
        return flask.jsonify(get_api_v1_info('/'))


def get_api_v1_info(api_prefix):
    """Return a dict with all the information specific for the v1 of the
    api.
    """
    websocket_root = base_ws_uri() + EVENTS_ENDPOINT
    return {
        'docs': DOCS_URL + 'http-client-server-api.html',
        'transactions': '{}transactions/'.format(api_prefix),
        'blocks': '{}blocks/'.format(api_prefix),
        'assets': '{}assets/'.format(api_prefix),
        'outputs': '{}outputs/'.format(api_prefix),
        'streams': websocket_root,
        'metadata': '{}metadata/'.format(api_prefix),
        'validators': '{}validators'.format(api_prefix),
    }
