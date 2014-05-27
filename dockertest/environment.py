#!/usr/bin/env python

"""
Low-level/standalone host-environment handling/checking utilities/classes/data

:Note: This module must _NOT_ depend on anything in dockertest package or
       in autotest!
"""

import os.path
import subprocess


class AllGoodBase(object):

    """
    Abstract class representing aggregate True/False value from callables
    """

    #: Mapping of callable name to instance
    callables = None

    #: Mapping of callable name to True/False value
    results = None

    #: Mapping of callable name to detailed results
    details = None

    #: Iterable of callable names to bypass
    skip = None

    def __init__(self, *args, **dargs):
        raise NotImplementedError()

    def __instattrs__(self, skip=None):
        """
        Override class variables with empty instance values

        :param skip: Iterable of callable names to not run
        """

        self.callables = {}
        self.results = {}
        self.details = {}
        if skip is None:
            self.skip = []
        else:
            self.skip = skip

    def __nonzero__(self):
        """
        Implement truth value testing and for the built-in operation bool()
        """

        return False not in self.results.values()

    def __str__(self):
        """
        Make results of individual checkers accessible in human-readable format
        """

        goods = [name for (name, result) in self.results.items() if result]
        bads = [name for (name, result) in self.results.items() if not result]
        if self:  # use self.__nonzero__()
            msg = "All Good: %s" % goods
        else:
            msg = "Good: %s; Not Good: %s; " % (goods, bads)
            msg += "Details:"
            dlst = [' (%s, %s)' % (name, self.detail_str(name))
                    for name in bads]
            msg += ';'.join(dlst)
        return msg

    def detail_str(self, name):
        """
        Convert details value for name into string

        :param name: Name possibly in details.keys()
        :return: String
        """

        return str(self.details.get(name, "No details"))

    #: Some subclasses need this to be a bound method
    def callable_args(self, name):  # pylint: disable=R0201
        """
        Return dictionary of arguments to pass through to each callable

        :param name: Name of callable to return args for
        :return: Dictionary of arguments
        """

        del name  # keep pylint happy
        return dict()

    def call_callables(self):
        """
        Call all instances in callables not in skip, storing results
        """

        _results = {}
        for name, call in self.callables.items():
            if callable(call) and name not in self.skip:
                _results[name] = call(**self.callable_args(name))
        self.results.update(self.prepare_results(_results))

    #: Some subclasses need this to be a bound method
    def prepare_results(self, results):  # pylint: disable=R0201
        """
        Called to process results into instance results and details attributes

        :param results: Dict-like of output from callables, keyed by name
        :returns: Dict-like for assignment to instance results attribute.
        """

        # In case call_callables() overridden but this method is not
        return dict(results)


class EnvCheck(AllGoodBase):

    """
    Represent aggregate result of calling all executables in envcheckdir

    :param config: Dict-like containing configuration options
    :param envcheckdir: Absolute path to directory holding scripts
    """

    #: Dict-like containing configuration options
    config = None

    #: Skip configuration key for reference
    envcheck_skip_option = 'envcheck_skip'

    #: Base path from which check scripts run
    envcheckdir = None

    def __init__(self, config, envcheckdir):
        # base-class __init__ is abstract
        # pylint: disable=W0231
        self.config = config
        self.envcheckdir = envcheckdir
        envcheck_skip = self.config.get(self.envcheck_skip_option)
        # Don't support content less than 'x,'
        if envcheck_skip is None or len(envcheck_skip.strip()) < 2:
            self.__instattrs__()
        else:
            self.__instattrs__(envcheck_skip.strip().split(','))
        for (dirpath, _, filenames) in os.walk(envcheckdir, followlinks=True):
            for filename in filenames:
                fullpath = os.path.join(dirpath, filename)
                relpath = fullpath.replace(self.envcheckdir, '')
                if relpath.startswith('/'):
                    relpath = relpath[1:]
                # Don't add non-executable files
                if not os.access(fullpath, os.R_OK | os.X_OK):
                    continue
                self.callables[relpath] = subprocess.Popen
        self.call_callables()

    def prepare_results(self, results):
        dct = {}
        # Wait for all subprocesses to finish
        for relpath, popen in results.items():
            (stdoutdata, stderrdata) = popen.communicate()
            dct[relpath] = popen.returncode == 0
            self.details[relpath] = {'exit': popen.returncode,
                                     'stdout': stdoutdata,
                                     'stderr': stderrdata}
        return dct

    def callable_args(self, name):
        fullpath = os.path.join(self.envcheckdir, name)
        # Arguments to subprocess.Popen for script "name"
        return {'args': fullpath, 'bufsize': 1, 'stdout': subprocess.PIPE,
                'stderr': subprocess.PIPE, 'close_fds': True, 'shell': True,
                'env': self.config}


def set_selinux_context(pwd, context=None, recursive=True):
    """
    When selinux is enabled it sets the context by chcon -t ...
    :param pwd: target directory
    :param context: desired context (svirt_sandbox_file_t by default)
    :param recursive: set context recursively (-R)
    :raise OSError: In case of failure
    """
    if context is None:
        context = "svirt_sandbox_file_t"
    if recursive:
        flags = 'R'
    else:
        flags = ''
    # changes context in case selinux is supported and is enabled
    _cmd = ("type -P selinuxenabled || exit 0 ; "
            "selinuxenabled || exit 0 ; "
            "chcon -%st %s %s" % (flags, context, pwd))
    cmd = subprocess.Popen(_cmd, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, shell=True)
    if cmd.wait() != 0:
        raise OSError("Fail to set selinux context by '%s' (%s):\nSTDOUT:\n%s"
                      "\nSTDERR:\n%s" % (_cmd, cmd.poll(), cmd.stdout.read(),
                                         cmd.stderr.read()))
