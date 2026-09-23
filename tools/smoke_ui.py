"""Start an isolated headless Streamlit server, check health, stop after 15 s."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = dict(os.environ)
    env.pop('OPENAI_API_KEY', None)
    with tempfile.TemporaryFile(mode='w+') as log:
        process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(Path(__file__).resolve().parents[1]/'app.py'),
                                    '--server.headless=true', '--server.address=127.0.0.1', f'--server.port={port}',
                                    '--browser.gatherUsageStats=false'], stdout=log, stderr=subprocess.STDOUT, env=env)
        try:
            deadline = time.monotonic()+15
            healthy = False
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Streamlit exited before smoke check completed')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health', timeout=1) as response:
                        healthy = response.status == 200
                except OSError:
                    pass
                time.sleep(.5)
            log.seek(0)
            output = log.read()
            assert healthy and 'Traceback' not in output, output
            print('Streamlit: health 200, 15 s alive, no startup traceback; stopping smoke server.')
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
