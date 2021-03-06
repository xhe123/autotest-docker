"""
Adapt/extend autotest.client.test.test for Docker test sub-framework

This module provides two helper classes intended to make writing
subtests easier.  They hide some of the autotest ``test.test``
complexity, while providing some helper methods for logging
output to the controlling terminal (only) and automatically
loading the specified configuration section (see `configuration module`_)
"""

# Pylint runs from a different directory, it's fine to import this way
# pylint: disable=W0403

import warnings
import logging
import tempfile
import os.path
import imp
import sys
import traceback
from autotest.client.shared import error
from autotest.client.shared import base_job
from autotest.client.shared.error import AutotestError
from autotest.client.shared.version import get_version
from autotest.client import job, test
import version
import config
from xceptions import DockerTestFail
from xceptions import DockerTestNAError
from xceptions import DockerTestError


class Subtest(test.test):

    """
    Extends autotest test.test with dockertest-specific items
    """
    #: Version number from configuration, read-only / setup inside __init__
    #: affects one-time building of bundled content in 'self.srcdir' by
    #: controlling the call to setup() method only when it changes.  Compared
    #: to dockertest API, when specified in configuration.  Test will not
    #: execute if there is a MAJOR/MINOR mismatch (revision is okay).
    version = None

    #: The current iteration being run, read-only / set by the harness.
    iteration = None  # set from test.test

    #: The number of iterations to run in total, override this in subclass.
    iterations = 1

    #: Configuration section used for subclass, read-only / set by Subtest class
    config_section = 'DEFAULTS'

    #: Private namespace for use by subclasses **ONLY**.  This attribute
    #: is completely ignored everywhere inside the dockertest API.  Subtests
    #: are encouraged to use it for temporarily storing results/info. It is
    #: initialized to an empty dictionary, but subtests can reassign it to any
    #: type needed.
    stuff = None

    #: private method used by log*() methods internally, do not use.
    _re = None

    def __init__(self, *args, **dargs):
        r"""
        Initialize new subtest, passes all arguments through to parent class

        :param *args & **dargs:  Ignored, passed through to parent class.
        """

        def _init_config():  # private, no docstring pylint: disable=C0111
            # So tests don't need to set this up every time
            config_parser = config.Config()
            self.config = config_parser.get(self.config_section)
            if self.config is None:
                logging.warning("No configuration section found '%s'",
                                self.config_section)
                self.config = config_parser['DEFAULTS']
                # Mark this to not be checked, no config, no version info.
                self.config['config_version'] = version.NOVERSIONCHECK
                self.version = 0
            else:
                # Version number used by one-time setup() test.test method
                self.version = version.str2int(self.config['config_version'])

        def _init_logging():  # private, no docstring pylint: disable=C0111
            # log indentation level not easy to get at, so use opaque impl.
            _si = job.status_indenter(self.job)
            _sl = base_job.status_logger(self.job, _si)
            self._re = _sl.render_entry  # will return string w/ proper indent
            # Log original key/values before subtest could modify them
            self.write_test_keyval(self.config)

        super(Subtest, self).__init__(*args, **dargs)
        _init_config()
        if not self.config.get('enable', True):
            raise DockerTestNAError("Subtest disabled in configuration.")
        _init_logging()
        # Optionally setup different iterations if option exists
        self.iterations = self.config.get('iterations', self.iterations)
        # subclasses can do whatever they like with this
        self.stuff = {}

    # Private workaround due to job/test instance private attributes/methods :(
    def _log(self, level, message, *args):  # pylint: disable=C0111
        method = getattr(logging, level)
        message = '%s: %s' % (level.upper(), message)
        sle = base_job.status_log_entry("RUNNING", None, None, message, {})
        rendered = self._re(sle)
        return method(rendered, *args)

    def execute(self, *args, **dargs):
        """**Do not override**, needed to pull data from super class"""
        super(Subtest, self).execute(iterations=self.iterations,
                                     *args, **dargs)

    # These methods can optionally be overridden by subclasses

    def setup(self):
        """
        Called once per version change
        """
        self.loginfo("setup() for subtest version %s", self.version)

    def initialize(self):
        """
        Called every time the test is run.
        """
        # Fail test if autotest is too old
        version.check_autotest_version(self.config, get_version())
        # Fail test if configuration being used doesn't match dockertest API
        version.check_version(self.config)
        self.loginfo("initialize()")

    def run_once(self):
        """
        Called to run test for each iteration
        """
        self.loginfo("run_once() iteration %d of %d",
                     self.iteration, self.iterations)

    def postprocess_iteration(self):
        """
        Called for each iteration, used to process results
        """
        self.loginfo("postprocess_iteration(), iteration #%d",
                     self.iteration)

    def postprocess(self):
        """
        Called after all postprocess_iteration()'s, processes all results
        """
        self.loginfo("postprocess()")

    def cleanup(self):
        """
        Called after all other methods, even if exception is raised.
        """
        self.loginfo("cleanup()")

    # Some convenience methods for tests to use

    @staticmethod
    def failif(condition, reason):
        """
        Convenience method for subtests to avoid importing TestFail exception

        :param condition: Boolean condition, fail test if True.
        :param reason: Helpful text describing why the test failed
        :raise DockerTestFail: If condition evaluates ``True``
        """
        if bool(condition):
            raise DockerTestFail(reason)

    def logdebug(self, message, *args):
        r"""
        Log a DEBUG level message to the controlling terminal **only**

        :param message: Same as logging.debug()
        :\*args: Same as logging.debug()
        """
        return self._log('debug', message, *args)

    def loginfo(self, message, *args):
        r"""
        Log a INFO level message to the controlling terminal **only**

        :param message: Same as logging.info()
        :\*args: Same as logging.info()
        """
        return self._log('info', message, *args)

    def logwarning(self, message, *args):
        r"""
        Log a WARNING level message to the controlling terminal **only**

        :param message: Same as logging.warning()
        :\*args: Same as logging.warning()
        """
        return self._log('warning', message, *args)

    def logerror(self, message, *args):
        r"""
        Log a ERROR level message to the controlling terminal **only**

        :param message: Same as logging.error()
        :\*args: Same as logging.error()
        """
        return self._log('error', message, *args)

    def logtraceback(self, name, exc_info, error_source, detail):
        r"""
        Log error to error, traceback to debug, of controlling terminal **only**
        """
        error_head = ("%s failed to %s: %s: %s" % (name,
                      error_source, detail.__class__.__name__,
                      detail))
        error_tb = traceback.format_exception(exc_info[0],
                                              exc_info[1],
                                              exc_info[2])

        error_tb = "".join(error_tb).strip()
        self.logerror(error_head)
        self.logdebug(error_tb)


class SubSubtest(object):

    """
    Simplistic/minimal subtest interface matched with config section

    :*Note*: Contains, and is similar to, but DOES NOT represent
             the same interface as the Subtest class (above).
    """
    #: Reference to outer, parent test.  Read-only / set in __init__
    parent_subtest = None

    #: subsubsub test config instance, read-write, setup in __init__ but
    #: persists across iterations.  Handy for storing temporary results.
    config = None

    #: Path to a temporary directory which will automatically be
    #: removed during cleanup()
    tmpdir = None  # automatically determined in initialize()

    #: Private namespace for use by subclasses **ONLY**.  This attribute
    #: is completely ignored everywhere inside the dockertest API.  Subtests
    #: are encouraged to use it for temporarily storing results/info.  It
    #: is initialized to an empty dictionary, however subsubtests may
    #: re-assign it to any other type as needed.
    sub_stuff = None

    def __init__(self, parent_subtest):
        """
        Initialize sub-subtest

        :param parent_subtest: The Subtest instance calling this instance
        """
        # Allow parent_subtest to use any interface this
        # class is setup to support. Don't check type.
        self.parent_subtest = parent_subtest
        # Append this subclass's name onto parent's section name
        # e.g. [parent_config_section/child_class_name]
        config_section = (os.path.join(self.parent_subtest.config_section,
                                       self.__class__.__name__))
        # Allow child to inherit and override parent config
        all_configs = config.Config()
        # make_subsubtest_config will modify this
        parent_config = self.parent_subtest.config.copy()
        # subsubtest config is optional, overrides parent.
        if config_section not in all_configs:
            self.config = parent_config
        else:
            self.make_subsubtest_config(all_configs,
                                        parent_config,
                                        all_configs[config_section])
        # FIXME: Honor SubSubtest ``enable`` conf. option
        # Not automatically logged along with parent subtest
        # for records/archival/logging purposes
        note = {'Configuration_for_Subsubtest': config_section}
        self.parent_subtest.write_test_keyval(note)
        self.parent_subtest.write_test_keyval(self.config)
        # subclasses can do whatever they like with this
        self.sub_stuff = {}

    def make_subsubtest_config(self, all_configs, parent_config,
                               subsubtest_config):
        """
        Form subsubtest configuration by inheriting parent subtest config
        """
        self.config = parent_config  # a copy
        # global defaults mixed in, even if overriden in parent :(
        for key, val in subsubtest_config.items():
            if key in all_configs['DEFAULTS']:
                def_val = all_configs['DEFAULTS'][key]
                par_val = parent_config[key]
                if val == def_val:
                    if par_val != def_val:
                        # Parent overrides default, subsubtest inherited default
                        self.config[key] = par_val
                    else:
                        # Parent uses default, subsubtest did not override
                        self.config[key] = def_val
                else:
                    self.config[key] = val
            else:
                self.config[key] = val
            self.logdebug("Config.: %s = %s", key, self.config[key])
        return self.config

    def initialize(self):
        """
        Called every time the test is run.
        """
        self.loginfo("%s initialize()", self.__class__.__name__)
        self.tmpdir = tempfile.mkdtemp(prefix=self.__class__.__name__,
                                       suffix='tmp',
                                       dir=self.parent_subtest.tmpdir)

    def run_once(self):
        """
        Called once only to exercise subject of sub-subtest
        """
        self.loginfo("%s run_once()", self.__class__.__name__)

    def postprocess(self):
        """
        Called to process results of subject
        """
        self.loginfo("%s postprocess()", self.__class__.__name__)

    def cleanup(self):
        """
        Always called, even despite any exceptions thrown.
        """
        self.loginfo("%s cleanup()", self.__class__.__name__)
        # tmpdir is cleaned up automatically by harness

    # FIXME: This method should be @staticmethod on on images.DockerImage
    #        duplicating containers.DockerContainersBase.get_unique_name()
    def make_repo_name(self):
        """
        Convenience function to generate a unique test-repo name

        :**note**: This method will be going away sometime
        """
        warnings.warn(PendingDeprecationWarning())
        prefix = self.parent_subtest.config['repo_name_prefix']
        name = os.path.basename(self.tmpdir)
        postfix = self.parent_subtest.config['repo_name_postfix']
        return "%s%s%s" % (prefix, name, postfix)

    # Handy to have here also
    failif = staticmethod(Subtest.failif)

    def logdebug(self, message, *args):
        """
        Same as Subtest.logdebug
        """
        newmsg = 'SubSubtest %s DEBUG: %s' % (self.__class__.__name__, message)
        return self.parent_subtest.logdebug(newmsg, *args)

    def loginfo(self, message, *args):
        """
        Same as Subtest.loginfo
        """
        newmsg = 'SubSubtest %s INFO: %s' % (self.__class__.__name__, message)
        return self.parent_subtest.loginfo(newmsg, *args)

    def logwarning(self, message, *args):
        """
        Same as Subtest.logwarning
        """
        newmsg = 'SubSubtest %s WARN: %s' % (self.__class__.__name__, message)
        return self.parent_subtest.logwarning(newmsg, *args)

    def logerror(self, message, *args):
        """
        Same as Subtest.logerror
        """
        newmsg = 'SubSubtest %s ERROR: %s' % (self.__class__.__name__, message)
        return self.parent_subtest.logerror(newmsg, *args)


class SubSubtestCaller(Subtest):

    """
    Extends Subtest by automatically discovering and calling child subsubtests.

    Child subsubtest methods ``initialize``, ``run_once``, and ``postprocess``,
    are executed together, for each subsubtest.  Whether or not any exception
    is raised, the ``cleanup`` method will always be called last.  The
    subsubtest the order is specified by the  ``subsubtests`` (CSV) config.
    option.  Child subsubtest configuration section is formed by appending the
    child's subclass name onto the parent's ``config_section`` value.  Parent
    configuration is passed to subsubtest, with the subsubtest's section
    overriding values with the same option name.
    """

    #: A list holding the ordered names of each subsubtest to load and run.
    #: (read-only).
    subsubtest_names = None

    #: A dictionary of subsubtest names to instances loaded (read-only), used
    #: for comparison during ``postprocess()`` against final_subtests to
    #: determine overall subtest success or failure.
    start_subsubtests = None

    #: The set of subsubtests which successfully completed all stages w/o
    #: exceptions.  Compared against ``start_subsubtests``. (read-only)
    final_subsubtests = None

    #: Dictionary containing exc_info, error_source data for a subsubtest
    #: for logging/debugging purposes while calling methods.  (read-only)
    exception_info = None

    def __init__(self, *args, **dargs):
        r"""
        Call subtest __init__ and setup local attributes

        :param \*args & \*\*dargs: Opaque, passed through to super-class
        """
        super(SubSubtestCaller, self).__init__(*args, **dargs)
        #: Need separate private dict similar to `sub_stuff` but different name

        self.subsubtest_names = []
        self.start_subsubtests = {}
        self.final_subsubtests = set()
        self.exception_info = {}

    def initialize(self):
        """
        Perform initialization steps needed before loading subsubtests.  Split
        up the ``subsubtests`` config. option by commas, into instance attribute
        ``subsubtest_names`` (list).
        """
        super(SubSubtestCaller, self).initialize()
        # Private to this instance, outside of __init__
        self.subsubtest_names = self.config['subsubtests'].strip().split(",")

    def try_all_stages(self, name, subsubtest):
        """
        Attempt to execute each subsubtest stage (initialize, run_once,
        and postprocess).  For those that don't raise any exceptions,
        record subsubtest name in ``final_subsubtests`` set instance
        attribute. Hides _all_ AutotestError subclasses but logs traceback.

        :param name:  String, name of subsubtest class (and possibly module)
        :param subsubtest:  Instance of subsubtest or subclass
        """
        try:
            self.call_subsubtest_method(subsubtest.initialize)
            self.call_subsubtest_method(subsubtest.run_once)
            self.call_subsubtest_method(subsubtest.postprocess)
            # No exceptions, contribute to subtest success
            self.final_subsubtests.add(name)
        except AutotestError, detail:
            self.logtraceback(name,
                              self.exception_info["exc_info"],
                              self.exception_info["error_source"],
                              detail)
        except Exception, detail:
            self.logtraceback(name,
                              self.exception_info["exc_info"],
                              self.exception_info["error_source"],
                              detail)
            exc_info = self.exception_info["exc_info"]
            # cleanup() will still be called before this propigates
            raise exc_info[0], exc_info[1], exc_info[2]

    def run_all_stages(self, name, subsubtest):
        """
        Catch any exceptions coming from any subsubtest's stage to ensure
        it's ``cleanup()`` always runs.  Updates ``start_subsubtests``
        attribute with subsubtest names and instance to successfully
        loaded/imported.

        :param name:  String, name of subsubtest class (and possibly module)
        :param subsubtest:  Instance of subsubtest or subclass
        :raise DockerTestError: On subsubtest ``cleanup()`` failures **only**
        """
        if subsubtest is not None:
            # Guarantee cleanup() runs even if autotest exception
            self.start_subsubtests[name] = subsubtest
            try:
                self.try_all_stages(name, subsubtest)
            finally:
                try:
                    subsubtest.cleanup()
                except Exception, detail:
                    self.logtraceback(name,
                                      sys.exc_info(),
                                      "Cleanup",
                                      detail)
                    raise error.TestError("Sub-subtest %s cleanup"
                                          " failures: %s" % (name, detail))

        else:
            logging.warning("Failed importing sub-subtest %s", name)


    def run_once(self):
        """
        Find, instantiate, and call all testing methods on each subsubtest, in
        order, subsubtest by subsubtest.  Autotest-specific exceptions are
        logged but non-fatal.  All other exceptions raised after calling
        subsubtest's ``cleanup()`` method.  Subsubtests which successfully
        execute all stages are appended to the ``final_subsubtests`` set
        (instance attribute) to determine overall subtest success/failure.
        """
        super(SubSubtestCaller, self).run_once()
        for name in self.subsubtest_names:
            self.run_all_stages(name, self.new_subsubtest(name))

    def postprocess(self):
        """
        Compare set of subsubtest name (keys) from ``start_subsubtests``
        to ``final_subsubtests`` set.

        :raise DockerTestFail: if start_subsubtests != final_subsubtests
        """
        super(SubSubtestCaller, self).postprocess()
        # Dictionary is overkill for pass/fail determination
        start_subsubtests = set(self.start_subsubtests.keys())
        failed_tests = start_subsubtests - self.final_subsubtests

        if failed_tests:
            raise DockerTestFail('Sub-subtest failures: %s' %
                                 str(failed_tests))

    def call_subsubtest_method(self, method):
        """
        Call ``method``, recording execution info. on exception.
        """
        try:
            method()
        except Exception:
            # Log problem, don't add to run_subsubtests
            self.exception_info["error_source"] = method.func_name
            self.exception_info["exc_info"] = sys.exc_info()
            raise

    def import_if_not_loaded(self, name, pkg_path):
        """
        Import module only if module is not loaded.
        """
        # Safe because test is running in a separate process from main test
        if not name in sys.modules:
            mod = imp.load_module(name, *imp.find_module(name, pkg_path))
            sys.modules[name] = mod
            return mod
        else:
            return sys.modules[name]

    def new_subsubtest(self, name):
        """
        Attempt to import named subsubtest subclass from subtest module or
        module name.

        :param name: Class name, optionally external module-file name.
        :return: SubSubtest subclass instance or None if failed to load
        """
        # Try in external module-file named 'name' also
        mydir = self.bindir
        # Look in module holding this subclass for subsubtest class first.
        myname = self.__class__.__name__
        mod = self.import_if_not_loaded(myname, [mydir])
        cls = getattr(mod, name, None)
        # Not found in this module, look in external module file with same name
        if cls is None:
            # FIXME: subsubtest modules should be able to import and
            #        reference eachother within the context of their
            #        parent subtest.  Currently this doesn't work.
            #   -->  Maybe inject bindir into sys.path, then remove in
            #        cleanup()?
            # Only look in "this" directory
            mod = self.import_if_not_loaded(name, [mydir])
            cls = getattr(mod, name, None)
        if issubclass(cls, SubSubtest):
            # Create instance, pass this subtest subclass as only parameter
            return cls(self)
        # Load failure will be caught and loged later
        return None

    def cleanup(self):
        super(SubSubtestCaller, self).cleanup()


class SubSubtestCallerSimultaneous(SubSubtestCaller):

    """
    Variation on SubSubtestCaller that calls test methods in subsubtest order.

    Child subsubtest methods ``initialize``, ``run_once``, and ``postprocess``,
    are executed separately, for each subsubtest.  Whether or not any exception
    is raised, the ``cleanup`` method will always be called last.  The
    subsubtest the order is specified by the  ``subsubtests`` (CSV) config.
    option.  Child subsubtest configuration section is formed by appending the
    child's subclass name onto the parent's ``config_section`` value.  Parent
    configuration is passed to subsubtest, with the subsubtest's section
    overriding values with the same option name.
    """

    #: Dictionary of subsubtests names to instances which successfully
    #: executed ``initialize()`` w/o raising exception
    run_subsubtests = None

    #: Dictionary of subsubtests names to instances which successfully
    #: executed ``run_once()`` w/o raising exception
    post_subsubtests = None

    def __init__(self, *args, **dargs):
        super(SubSubtestCallerSimultaneous, self).__init__(*args, **dargs)
        self.run_subsubtests = {}
        self.post_subsubtests = {}

    def initialize(self):
        super(SubSubtestCallerSimultaneous, self).initialize()
        for name in self.subsubtest_names:
            subsubtest = self.new_subsubtest(name)
            if subsubtest is not None:
                # Guarantee it's cleanup() runs
                self.start_subsubtests[name] = subsubtest
                try:
                    subsubtest.initialize()
                    # Allow run_once() on this subsubtest
                    self.run_subsubtests[name] = subsubtest
                except AutotestError, detail:
                    # Log problem, don't add to run_subsubtests
                    self.logtraceback(name, sys.exc_info(), "initialize",
                                      detail)

    def run_once(self):
        # DO NOT CALL superclass run_once() this variation works
        # completely differently!
        for name, subsubtest in self.run_subsubtests.items():
            try:
                subsubtest.run_once()
                # Allow postprocess()
                self.post_subsubtests[name] = subsubtest
            except AutotestError, detail:
                # Log problem, don't add to post_subsubtests
                self.logtraceback(name, sys.exc_info(), "run_once", detail)

    def postprocess(self):
        # DO NOT CALL superclass run_once() this variation works
        # completely differently!
        start_subsubtests = set(self.start_subsubtests.keys())
        final_subsubtests = set()
        for name, subsubtest in self.post_subsubtests.items():
            try:
                subsubtest.postprocess()
                # Will form "passed" set
                final_subsubtests.add(name)
            except AutotestError, detail:
                # Forms "failed" set by exclusion from final_subsubtests
                self.logtraceback(name, sys.exc_info(), "postprocess",
                                  detail)
        if not final_subsubtests == start_subsubtests:
            raise DockerTestFail('Sub-subtest failures: %s'
                                 % str(start_subsubtests - final_subsubtests))

    def cleanup(self):
        super(SubSubtestCallerSimultaneous, self).cleanup()
        cleanup_failures = set()  # just for logging purposes
        for name, subsubtest in self.start_subsubtests.items():
            try:
                subsubtest.cleanup()
            except AutotestError, detail:
                cleanup_failures.add(name)
                self.logtraceback(name, sys.exc_info(), "cleanup",
                                  detail)
        if len(cleanup_failures) > 0:
            raise DockerTestError("Sub-subtest cleanup failures: %s"
                                  % cleanup_failures)
