"""
Test catching a signal inside a container
"""
# Okay to be less-strict for these cautions/warnings in subtests
# pylint: disable=C0103,C0111,R0904,C0103

import signal
import time

from autotest.client import utils
from dockertest.dockercmd import AsyncDockerCmd
from run import run_base


class run_signal(run_base):

    def run_once(self):
        sig = getattr(signal, self.config['listen_signal'])
        dkrcmd = AsyncDockerCmd(self.parent_subtest, 'run',
                                self.sub_stuff['subargs'],
                                timeout=self.config['docker_timeout'])
        self.logdebug("Starting background docker command, timeout %s seconds: "
                     "%s", self.config['docker_timeout'], dkrcmd.command)
        dkrcmd.verbose = True
        # Runs in background
        cmdresult = self.sub_stuff['cmdresult'] = dkrcmd.execute()
        pid = dkrcmd.process_id
        ss = self.config['secret_sauce']
        while True:
            stdout = dkrcmd.stdout
            if stdout.count(ss) >= 1:
                break
            time.sleep(0.1)
        wait_start = self.config['wait_start']
        self.loginfo("Container running, waiting %d seconds to send signal"
                     % wait_start)
        # Allow noticable time difference for date command,
        # and eat into dkrcmd timeout after receiving signal.
        time.sleep(wait_start)
        self.failif(not utils.pid_is_alive(pid),
                    "Pid %s not running after wait: %s"
                    % (pid, cmdresult))
        self.loginfo("Signaling pid %d with signal %s",
                     pid, self.config['listen_signal'])
        utils.signal_pid(pid, sig)
        self.loginfo("Waiting up to %d seconds for exit",
                     dkrcmd.timeout)
        # Throw exception if takes > docker_timeout to exit
        dkrcmd.wait()

    # TODO: Verify date in 'stop' file advanced by ~10 seconds
    #       def post_process(self):
