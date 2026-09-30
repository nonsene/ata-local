import os
import subprocess
import sys
import pytest


@pytest.mark.skipif(os.name != 'nt', reason='Windows Job Object')
def test_closing_owner_job_terminates_child():
    from ata_local.windows_job import WindowsJob
    job = WindowsJob()
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                               creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        job.add(process)
        job.close()
        # A Job Object may report exit code 0; it must stop the 30-second child promptly.
        assert process.wait(timeout=5) is not None
    finally:
        if process.poll() is None:
            process.kill()
        job.close()
