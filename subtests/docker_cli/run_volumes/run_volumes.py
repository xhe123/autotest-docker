"""
Test read & write to various host-paths as container volumes

1. Write unique value to file on host path
2. Start container, hash file, store has in second file
3. Check second file on host, verify hash matches.
"""

# Okay to be less-strict for these cautions/warnings in subtests
# pylint: disable=C0103,C0111,R0904,C0103

import time
import os
import os.path
import hashlib
from string import Template

from autotest.client import utils
from dockertest.subtest import Subtest
from dockertest.containers import DockerContainers
from dockertest.dockercmd import NoFailDockerCmd
from dockertest.images import DockerImage
from dockertest.xceptions import DockerTestNAError
from dockertest.xceptions import DockerCommandError
from dockertest.xceptions import DockerExecError

class run_volumes(Subtest):
    config_section = 'docker_cli/run_volumes'

    @staticmethod
    def make_test_files(host_path):
        # Symlink can't be mountpoint (e.g. for NFS, SMB, etc.)
        if (not os.path.isdir(host_path) or
            os.path.islink(host_path)):
            raise DockerTestNAError('Configured path "%s" is a symlink '
                                    'or not a directory' % host_path)
        read_fn = utils.generate_random_string(24)
        write_fn = utils.generate_random_string(24)
        read_data = utils.generate_random_string(24)
        read_hash = hashlib.md5(read_data).hexdigest()
        tr_file = open(os.path.join(host_path, read_fn), 'wb')
        tr_file.write(read_data)
        tr_file.close()
        return (read_fn, write_fn, read_data, read_hash)

    @staticmethod
    def make_test_dict(read_fn, write_fn, read_data, read_hash,
                       host_path, cntr_path):
        return {'read_fn':read_fn, 'write_fn':write_fn,
                'read_data':read_data, 'read_hash':read_hash,
                'write_hash':None,  # Filled in after execute()
                'host_path':host_path, 'cntr_path':cntr_path}

    @staticmethod
    def init_path_info(path_info, host_paths, cntr_paths):
        for host_path, cntr_path in zip(host_paths, cntr_paths):
            #check for a valid host path for the test
            if not host_path or len(host_path) < 4:
                raise DockerTestNAError("host_path '%s' invalid." % host_path)
            if not cntr_path or len(cntr_path) < 4:
                raise DockerTestNAError("cntr_path '%s' invalid." % cntr_path)
            # keys must coorespond with those used in *_template strings
            args = run_volumes.make_test_files(os.path.abspath(host_path))
            args += (host_path, cntr_path)
            # list of dicts {'read_fn', 'write_fn', 'read_data', ...}
            test_dict = run_volumes.make_test_dict(*args)
            path_info.append(test_dict)

    @staticmethod
    def make_dockercmd(subtest, dockercmd_class, fqin,
                       run_template, cmd_tmplate, test_dict):
        # safe_substutute ignores unknown tokens
        subargs = run_template.safe_substitute(test_dict).strip().split(',')
        subargs.append(fqin)
        subargs.append(cmd_tmplate.safe_substitute(test_dict))
        return dockercmd_class(subtest, 'run', subargs)

    @staticmethod
    def init_dkrcmds(subtest, path_info, dockercmds):
        run_template = Template(subtest.config['run_template'])
        cmd_tmplate = Template(subtest.config['cmd_template'])
        fqin = DockerImage.full_name_from_defaults(subtest.config)
        for test_dict in path_info:
            dockercmds.append(subtest.make_dockercmd(subtest,
                                                     NoFailDockerCmd,
                                                     fqin,
                                                     run_template,
                                                     cmd_tmplate,
                                                     test_dict))

    def initialize(self):
        super(run_volumes, self).initialize()
        host_paths = self.config['host_paths'].strip().split(',')
        cntr_paths = self.config['cntr_paths'].strip().split(',')
        path_info = self.stuff['path_info'] = []
        # Throws DockerTestNAError if any host_paths is bad
        self.init_path_info(path_info, host_paths, cntr_paths)
        dockercmds = self.stuff['dockercmds'] = []
        # Does not execute()
        self.init_dkrcmds(self, path_info, dockercmds)
        self.stuff['cmdresults'] = []
        for dcmd in dockercmds:
           self.logdebug("Initialized Docker command: %s", dcmd.command)

    def run_once(self):
        super(run_volumes, self).run_once()
        for dockercmd in self.stuff['dockercmds']:
            self.stuff['cmdresults'].append(dockercmd.execute())
        wait_stop = self.config['wait_stop']
        self.loginfo("Waiting %d seconds for docker to catch up", wait_stop)
        time.sleep(wait_stop)
        for test_dict in self.stuff['path_info']:
            host_path = test_dict['host_path']
            write_fn = test_dict['write_fn']
            try:
                write_path = os.path.join(host_path, write_fn)
                write_file = open(write_path, 'rb')
                data = write_file.read()
                # md5sum output format:  hash + ' ' + filename|-
                test_dict['write_hash'] = data.strip().split(None, 1)[0]
            except (IOError, OSError, IndexError, AttributeError), xcept:
                self.logerror("Problem reading hash from output file: %s: %s",
                               write_path, xcept.__class__.__name__, xcept)

    def postprocess(self):
        super(run_volumes, self).postprocess()
        results_data = zip(self.stuff['cmdresults'], self.stuff['path_info'])
        for cmdresult, test_dict in results_data:
            self.failif(cmdresult.exit_status != 0,
                        "Non-zero exit status: %s" % cmdresult)
            wh = test_dict['write_hash']
            rh = test_dict['read_hash']
            self.failif(wh != rh, "Test hash mismatch for %s; "
                                  "%s (test wrote) != %s (test read)"
                                   # order is backwards for output readability
                                   % (cmdresult.command, rh, wh))

    @staticmethod
    def try_kill(subtest, cmdresult):
        docker_containers = DockerContainers(subtest)
        try:
            cid = cmdresult.stdout.strip()
            docker_containers.kill_container_by_long_id(cid)
        except ValueError:
            pass  # not running is the goal
        except KeyError:
            subtest.logwarning("Container %s not found for for command %s",
                            cid, cmdresult.command)

    @staticmethod
    def try_rm(subtest, cmdresult):
        cid = cmdresult.stdout.strip()
        subargs = ['--force', '--volumes', cid]
        nfdc = NoFailDockerCmd(subtest, 'rm', subargs)
        try:
            nfdc.execute()
        except DockerExecError:
            pass  # removal was the goal
        except DockerCommandError, xcept:
            subtest.logwarning("Container remove failed: %s", xcept)

    def cleanup(self):
        super(run_volumes, self).cleanup()
        if self.config['remove_after_test']:
            if self.stuff.get('cmdresults') is None:
                return
            for cmdresult in self.stuff['cmdresults']:
                self.try_kill(self, cmdresult)
                self.try_rm(self, cmdresult)
            for test_data in self.stuff['path_info']:
                write_path = os.path.join(test_data['host_path'],
                                          test_data['write_fn'])
                read_path = os.path.join(test_data['host_path'],
                                         test_data['read_fn'])
                if write_path is not None and os.path.isfile(write_path):
                    os.unlink(write_path)
                    self.logdebug("Removed %s", write_path)
                if read_path is not None and os.path.isfile(read_path):
                    os.unlink(read_path)
                    self.logdebug("Removed %s", read_path)
