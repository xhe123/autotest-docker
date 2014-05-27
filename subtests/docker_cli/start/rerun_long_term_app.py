"""
Test output of docker start command

docker start full_name

1. Create new container with run long term process.
2. Try to start again running container.
3. Check if start of running container failed.
"""

from start import short_term_app
from dockertest.output import OutputGood

# Okay to be less-strict for these cautions/warnings in subtests
# pylint: disable=C0103,C0111,R0904,C0103

class rerun_long_term_app(short_term_app):
    config_section = 'docker_cli/start/rerun_long_term_app'

    def outputgood(self):
        # Raise exception if problems found
        # but ignore expected error message
        OutputGood(self.sub_stuff['cmdresult'], ignore_error=True,
                   skip=['error_check'])

    def postprocess(self):
        super(rerun_long_term_app, self).postprocess()
        # Raise exception if problems found
        # but ignore expected error message
        OutputGood(self.sub_stuff['cmdresult'], ignore_error=True,
                   skip=['error_check'])

        if self.config["docker_expected_result"] == "FAIL":
            self.failif(self.sub_stuff['cmdresult'].exit_status == 0,
                        "Zero start exit status: Command should fail due to"
                        " wrong command arguments.")
