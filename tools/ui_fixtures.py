"""Shared B test setup; creates only the ignored demonstration outputs."""
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.fixture(scope='session', autouse=True)
def ensure_stub():
    root=Path(__file__).resolve().parents[1]
    if not (root/'out_stub/run_meta.json').exists():
        subprocess.run([sys.executable,str(root/'tools/make_stub_outputs.py'),'--data',str(root/'data'),'--out',str(root/'out_stub')],cwd=root,check=True)
