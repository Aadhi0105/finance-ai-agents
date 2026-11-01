"""Owned process lifecycle for the opt-in local worker; no arbitrary executable API."""
import os
import select
import subprocess
import sys

from keystone.maintenance import ROOT
from .job_contract import JobError
from .worker import offline_environment


class WorkerProcess:
    def __init__(self, workspace, directory):
        self.process = None
        ready, child = os.pipe()
        try:
            self.process = subprocess.Popen([sys.executable, '-m', 'keystone.workspace.worker',
                '--workspace', str(workspace), '--jobs-dir', str(directory),
                '--parent-pid', str(os.getpid()), '--ready-fd', str(child)], cwd=ROOT,
                env=offline_environment(directory), pass_fds=(child,),
                start_new_session=True, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.close(child)
            child = None
            if not select.select([ready], [], [], 10)[0] or os.read(ready, 1) != b'1':
                raise JobError('job_worker_unavailable')
        except Exception:
            self.close()
            raise JobError('job_worker_unavailable') from None
        finally:
            os.close(ready)
            if child is not None:
                os.close(child)

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def close(self):
        if self.running:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
