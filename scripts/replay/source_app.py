"""ABCI stub behind the source Tendermint node: reports the stored chain's height and app hash so Tendermint skips
the handshake replay and serves the original blockstore to peers. Never executes a block.

Usage: python source_app.py <height> <app hash as text, empty to learn it from Tendermint's mismatch panic>
"""
import sys

from abci import ABCI, TmVersion
from abci.application import BaseApplication
from abci.server import ABCIServer


class SourceApp(BaseApplication):
    def info(self, req):
        response = self.abci.ResponseInfo()
        response.last_block_height = int(sys.argv[1])
        response.last_block_app_hash = sys.argv[2].encode('utf-8')
        return response


ABCIServer(app=SourceApp(ABCI(TmVersion.v0_31_5).types)).run()
