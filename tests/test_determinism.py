"""Offline determinism (§23): synthetic history reproducible across processes."""

import subprocess
import sys
from tools.data import _history_synthetic, _stable_seed


def test_stable_seed_repeatable():
    assert _stable_seed("ASML.AS") == _stable_seed("ASML.AS")


def test_stable_seed_differs_by_ticker():
    assert _stable_seed("ASML.AS") != _stable_seed("SAP.DE")


def test_history_repeatable_in_process():
    a = _history_synthetic("ASML.AS")["history"]
    b = _history_synthetic("ASML.AS")["history"]
    assert [r["close"] for r in a] == [r["close"] for r in b]


def test_history_reproducible_across_processes():
    # The real §23 bug: hash() randomization differed between interpreters.
    snippet = ("from tools.data import _history_synthetic; "
               "print(_history_synthetic('ASML.AS')['history'][0]['close'])")
    env = {"PYTHONHASHSEED": "random", "AGENT_DATA_SOURCE": "fixture"}
    import os
    env = {**os.environ, **env}
    out1 = subprocess.check_output([sys.executable, "-c", snippet], env=env).strip()
    env["PYTHONHASHSEED"] = "12345"
    out2 = subprocess.check_output([sys.executable, "-c", snippet], env=env).strip()
    assert out1 == out2
