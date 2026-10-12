"""Opt-in browser regression with real Decision, Planning and HTTP, and synthetic live data."""

import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest


@pytest.mark.skipif(os.environ.get('TG_BROWSER_TEST') != '1', reason='set TG_BROWSER_TEST=1 to run Chromium')
def test_overload_browser_flow(tmp_path, store_kind):
    from decision import Data, Engine as DecisionEngine, Store as DecisionStore, Tools as DecisionTools, load_settings
    from planning import Engine, Tools
    from harness import Harness, Store
    from harness.server import handler
    from plan_fixtures import CFG, FakeLive, CENTRE, spot, fake_matrix, no_geocode
    from test_dispatch import Tools as FakeTools, run
    from test_harness_server import FakeAccounts, USERS
    root = Path(__file__).resolve().parents[2]
    records = [spot(f'p{i}', CENTRE, i % 3, price={'typical_vnd': 10000}) for i in range(16)]
    for record in records:
        record['provenance'] = {'voices': 1}
    dt = DecisionTools(DecisionEngine(Data(records), load_settings(), DecisionStore(None)))
    pt = Tools(Engine(records, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
        matrix_fn=fake_matrix, sun_fn=lambda *a: (360, 1050), lodging_fn=lambda *a: [],
        route_fn=lambda *a: {'points': [], 'source': 'fixture', 'fetched_at': 't'}, background=False))
    h = Harness(FakeTools('trip'), dt, pt, Store(tmp_path / 'journeys'))
    v = h.create(owner=USERS['tok-a'])
    v = run(h, v, 'turn', 'compile', {'kind': 'show'})
    v = run(h, v, 'advance', 'decision')
    for i in range(16):
        v = run(h, v, 'act', f'select-{i}', {'type': 'select', 'place_id': f'p{i}'})
    seed = tmp_path / 'seed.json'
    seed.write_text(json.dumps({'journeyId': v['id'], 'decisionId': v['id'], 'planningId': None,
                              'vehicle': 'motorbike', 'searchInput': v['outputs']['trip']}))
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        web_port = probe.getsockname()[1]
    base = f'http://127.0.0.1:{web_port}'
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(h, FakeAccounts(), base))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    with (tmp_path / 'vite.log').open('w') as log:
        vite = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                                 '--port', str(web_port), '--strictPort'], cwd=root / 'web',
                                env={**os.environ, 'HARNESS_PORT': str(server.server_port)}, stdout=log, stderr=log)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base, timeout=1).close()
                    break
                except OSError:
                    time.sleep(0.1)
            result = subprocess.run(['node', 'scripts/test_overload_ui.mjs', base, str(seed)], cwd=root / 'web',
                                    capture_output=True, text=True, timeout=120)
            assert result.returncode == 0, result.stdout + result.stderr
            assert 'overload browser flow passed' in result.stdout
        finally:
            vite.terminate()
            vite.wait(timeout=10)
            server.shutdown()
            server.server_close()
            worker.join()
