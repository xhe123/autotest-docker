"""
Provides helpers for frequently used docker container operations.

This module defines several independent interfaces using an abstract-base-class
pattern.   They are extended through a few subclasses to meet basic needs.
There is an assumption that the full 64-character long IDs are safer
to use than the short, 12-character ones.  It is also assumed that callers
are in the best position to decide what if any 'tag' content is used
and how to mangle repo/image names.

Where/when ***possible***, both parameters and return values follow this order:

*  ``image_name``
*  ``command``
*  ``ports``
*  ``container_name``
*  ``long_id``
*  ``created``
*  ``status``
*  ``size``
"""

# Pylint runs from another directory, ignore relative import warnings
# pylint: disable=W0403

import json
from autotest.client import utils
from autotest.client.shared import error
from images import DockerImages
from output import OutputGood
from output import TextTable


# Many attributes simply required here
class DockerContainer(object):  # pylint: disable=R0902

    """
    Represent a container, image, and command as a set of instance attributes.
    """

    #: There will likely be many instances, limit memory consumption.
    __slots__ = ["image_name", "command", "ports", "container_name",
                 "long_id", "created", "status", "size"]

    def __init__(self, image_name, command, ports=None, container_name=None):
        """
        Create a new container representation based on parameter content.

        :param image_name: FQIN, fully qualified image name
        :param command: String of command container is/was running
        :param ports: String of comma-separated port mappings
        :param container_name: String representing name of container
        """
        self.image_name = image_name
        self.command = command
        if ports is None:
            self.ports = ''
        else:
            self.ports = ports
        self.container_name = str(container_name)
        #: These are typically all generated at runtime
        self.long_id = None
        self.created = None
        self.status = None
        self.size = None

    def __eq__(self, other):
        """
        Compare this instance to another

        :param other: An instance of this class (or subclass) for comparison.
        """
        self_val = [getattr(self, name) for name in self.__slots__]
        other_val = [getattr(other, name) for name in self.__slots__]
        for _self, _other in zip(self_val, other_val):
            if _self != _other:
                return False
        return True

    def __str__(self):
        """
        Represent instance in a human-readable form
        """
        return ("image: %s, command: %s, ports: %s, container_name: %s, "
                "long_id: %s, created: %s, status: %s, size: %s"
                % (self.image_name, self.command, self.ports,
                   self.container_name, self.long_id, self.created,
                   self.status, self.size))

    def __repr__(self):
        """
        Return python-standard representation of instance
        """
        return "DockerContainer(%s)" % str(self)

    def cmp_id(self, container_id):
        """
        Compares long and short version of ID depending on length.

        :param container_id: Exactly 12-character string or longer image ID
        :return: True/False equality
        """
        if len(container_id) == 12:
            return container_id == self.long_id[:12]
        else:
            return container_id == self.long_id

    def cmp_name(self, container_name):
        """
        Compares container_name string value to instance container_name

        :param container_name: Name of a container
        :return: True/False equality
        """
        return self.container_name == str(container_name)


class DockerContainersBase(object):

    """
    Implementation defined collection of DockerContainer-like instances with
    helpers
    """

    #: Operational timeout, may be overridden by subclasses and/or parameters.
    #: May not be used/enforced equally by all implementations.
    timeout = 60.0

    #: Control verbosity level of operations, implementation may be
    #: subclass-specific.  Actual verbosity level may vary across
    #: implementations.
    verbose = False

    #: Gathering layer-size data is potentially very slow, skip by default
    get_size = False

    # abstract methods need not worry about disused parameters
    # pylint: disable=W0613

    # abstract methods need not worry about methods that could be functions
    # pylint: disable=R0201

    def __init__(self, subtest, timeout, verbose):
        """
        Initialize subclass operational instance.

        :param subtest: A subtest.Subtest (**NOT** a SubSubtest) subclass
                        instance
        :param timeout: An int or float timeout value that overrides
                        ``docker_timeout`` config. option
        :param verbose: A boolean non-default verbose value to use on instance
        """

        if timeout is None:
            # Defined in [DEFAULTS] guaranteed to exist
            self.timeout = subtest.config['docker_timeout']
        else:
            # config() auto-converts otherwise catch non-float convertible
            self.timeout = float(timeout)

        if verbose:
            self.verbose = verbose

        self.subtest = subtest

    def get_container_list(self):
        """
        Standard name for behavior specific to subclass implementation details

        :note: This is probably not the method you're looking for,
               try ``list_containers()`` instead.

        :raises RuntimeError: if not defined by subclass
        :return: **implementation-specific**
        """
        raise RuntimeError()

    def list_containers(self):
        """
        Return a python-list of DockerContainer-like instances

        :return: [DockerContainer-like, DockerContainer-like, ...]
        """
        return self.get_container_list()

    def list_containers_with_name(self, container_name):
        """
        Return a python-list of DockerContainer-like instances

        :param container_name: String name of container
        :return: Python list of DockerContainer-like instances
        """
        clist = self.list_containers()
        return [cnt for cnt in clist if cnt.cmp_name(container_name)]

    def list_containers_with_cid(self, cid):
        """
        Return a python-list of DockerContainer-like instances

        :param cid: String of long or short container id
        :return: Python list of DockerContainer-like instances
        """
        clist = self.list_containers()
        return [cnt for cnt in clist if cnt.cmp_id(cid)]

    def list_container_ids(self):
        """
        Return python-list of all 64-character (long) container IDs

        :return:  [Cntr ID, Cntr ID, ...]
        """
        dcl = self.list_containers()
        return [cntr.long_id for cntr in dcl]

    def get_container_metadata(self, long_id):
        """
        Return implementation-specific metadata for container with long_id

        :param long_id: String of long-id for container
        :return: None if long_id invalid/not found or
                 implementation-specific value
        """
        del long_id  # Keep pylint quiet
        return None

    def json_by_long_id(self, long_id):
        """
        Return json-object for container with long_id if supported by
        implementation

        :param long_id: String of long-id for container
        :return: JSON object
        :raises ValueError: on invalid/not found long_id
        :raises RuntimeError: on not supported by implementation
        """
        del long_id  # Keep pylint quiet
        raise RuntimeError()

    def json_by_name(self, container_name):
        """
        Return json-object for container with name if supported by
        implementation

        :param container_name: String name of container
        :return: JSON object
        :raises ValueError: on invalid/not found long_id
        :raises RuntimeError: on not supported by implementation
        """
        cnts = self.list_containers_with_name(str(container_name))
        if len(cnts) == 1:
            return self.json_by_long_id(cnts[0].long_id)
        elif len(cnts) == 0:
            raise ValueError("Container not found with name %s"
                             % container_name)
        else:
            raise ValueError("Multiple containers with name %s found: (%s)"
                             % (container_name, cnts))

    def get_unique_name(self, prefix="", suffix="", length=4):
        """
        Get unique name for a new container

        :param prefix: Name prefix string
        :param suffix: Name suffix string
        :param length: Length of random string (greater than 1)
        :return: Container name guaranteed to not be in-use.
        """
        assert length > 1
        all_containers = [_.container_name for _ in self.list_containers()]
        check = lambda name: name not in all_containers
        return utils.get_unique_name(check, prefix, suffix, length)

    def kill_container_by_long_id(self, long_id):
        """
        Use docker CLI 'kill' command on container's long_id

        :param long_id: String of long-id for container
        :return: implementation specific value
        :raises RuntimeError: if not supported by implementation
        :raises KeyError: if container not found
        :raises ValueError: if container not running, defunct, or zombie
        """
        raise RuntimeError()

    def kill_container_by_obj(self, container_obj):
        """
        Use docker CLI 'kill' command on DockerContainer-like instance

        :param container_obj: DockerContainer-like instance
        :return: implementation specific value
        :raises RuntimeError: if not supported by implementation
        :raises KeyError: if container not found
        :raises ValueError: if container not running, defunct, or zombie
        """
        return self.kill_container_by_long_id(container_obj.long_id)

    def kill_container_by_name(self, container_name):
        """
        Use docker CLI 'kill' command on container's long_id, by name lookup.

        :param long_id: String of long-id for container
        :return: implementation specific value
        :raises RuntimeError: if not supported by implementation
        :raises KeyError: if container not found
        :raises ValueError: if container not running, defunct, or zombie
        """
        raise RuntimeError()

    # Disbled by default extension point, can't be static.
    def remove_by_id(self, container_id):  # pylint: disable=R0201
        """
        Remove an container by 64-character (long) or 12-character
           (short) container ID.

        :raise: RuntimeError when implementation does not permit container
                removal
        :raise: Implementation-specific exception
        :return: Implementation specific value
        """
        del container_id  # keep pylint happy
        raise RuntimeError()
        # Return value is defined as undefined
        return None  # pylint: disable=W0101

    def remove_by_obj(self, container_obj):
        """
        Alias for remove_by_id(container_obj.long_id)

        :raise: Same as remove_by_id()
        :raise: Implementation-specific exception
        :return: Same as remove_by_id()
        """
        return self.remove_by_id(container_obj.long_id)

    # Extension point, can't be static.
    def remove_by_name(self, name):  # pylint: disable=R0201
        """
        Remove an container by container Name.

        :raise: RuntimeError when implementation does not permit container
                removal
        :raise: Implementation-specific exception
        :return: Implementation specific value
        """
        cnts = self.list_containers_with_name(str(name))
        if len(cnts) == 1:
            return self.remove_by_obj(cnts[0])
        elif len(cnts) == 0:
            raise ValueError("Container not found with name %s"
                             % name)
        else:
            raise ValueError("Multiple containers with name found: %s" % cnts)

    def wait_by_long_id(self, long_id):
        """
        Block for container to exit, if not already.

        :raises RuntimeError: if not supported by implementation
        :raises ValueError: on invalid/not found long_id
        :param long_id: String of long-id for container
        :return: Implementation specific value
        """
        cnts = self.list_containers_with_cid(long_id)
        if len(cnts) == 1:
            raise RuntimeError()
        else:
            raise ValueError("Error retrieving container with id %s"
                             % long_id)

    def wait_by_obj(self, container_obj):
        """
        Block for container to exit, if not already.

        :raises RuntimeError: if not supported by implementation
        :raises ValueError: on invalid/not found container
        :param container_obj: DockerContainer-like instance
        :return: Implementation specific value
        """
        return self.wait_by_long_id(container_obj.long_id)

    def wait_by_name(self, name):
        """
        Block for container to exit, if not already.

        :raises RuntimeError: if not supported by implementation
        :raises ValueError: on invalid/not found container
        :param name: String name of container
        :return: Implementation specific value
        """
        cnts = self.list_containers_with_name(str(name))
        if len(cnts) == 1:
            return self.wait_by_obj(cnts[0])
        elif len(cnts) == 0:
            raise ValueError("Container not found with name %s"
                             % name)
        else:
            raise ValueError("Multiple containers found with name: %s" % cnts)


class DockerContainersCLI(DockerContainersBase):

    """
    Docker command supported DockerContainer-like instance collection and
    helpers
    """

    #: Name of signal to send when killing container, None for default
    kill_signal = None

    #: Run important docker commands output through OutputGood when True
    verify_output = False

    #: Extra arguments to use with remove methods
    remove_args = None

    def __init__(self, subtest, timeout=120, verbose=False):
        super(DockerContainersCLI, self).__init__(subtest,
                                                  timeout,
                                                  verbose)

    def get_container_list(self):
        """
        Run docker ps (w/ or w/o --size), return stdout
        """
        if not self.get_size:
            cmdresult = self.docker_cmd("ps -a --no-trunc",
                                        self.timeout)
        else:
            cmdresult = self.docker_cmd("ps -a --no-trunc --size",
                                        self.timeout)
        return cmdresult.stdout.strip()

    # private methods don't need docstrings
    def _dc_from_row(self, row):  # pylint: disable=C0111
        image_name = row['IMAGE']
        command = row['COMMAND']
        ports = row['PORTS']
        container_name = row['NAMES']
        dcntr = DockerContainer(image_name, command, ports, container_name)
        dcntr.long_id = row['CONTAINER ID']
        dcntr.created = row['CREATED']
        dcntr.status = row['STATUS']
        if self.get_size:
            # Raise documented get_container_list() exception
            try:
                dcntr.size = row['SIZE']  # throw
            except KeyError:
                raise ValueError("No size data present in table!")
        return dcntr

    # private methods don't need docstrings
    def _parse_lines(self, stdout_strip):  # pylint: disable=C0111
        texttable = TextTable(stdout_strip)
        return [self._dc_from_row(row) for row in texttable]

    def docker_cmd(self, cmd, timeout=None):
        """
        Called on to execute docker subcommand cmd with timeout

        :param cmd: Command which should be called using docker
        :param timeout: Override self.timeout if not None
        :return: autotest.client.utils.CmdResult instance
        """
        docker_cmd = ("%s %s" % (self.subtest.config['docker_path'],
                                 cmd))
        if timeout is None:
            timeout = self.timeout
        return utils.run(docker_cmd,
                         verbose=self.verbose,
                         timeout=timeout)

    def docker_cmd_check(self, cmd, timeout=None):
        """
        Wrap docker_cmd, running result through OutputGood before returning
        """
        result = self.docker_cmd(cmd, timeout)
        OutputGood(result)
        return result

    def list_containers(self):
        return self._parse_lines(self.get_container_list())

    def get_container_metadata(self, long_id):
        try:
            cmdresult = self.docker_cmd('inspect "%s"' % str(long_id),
                                        self.timeout)
            if cmdresult.exit_status == 0:
                _json = json.loads(cmdresult.stdout.strip())
                if len(_json) > 0:
                    # No items in _json list should be empty either
                    if all([len(item) > 0 for item in _json]):
                        return _json
            #  failed command, empty list, or empty list item
            return None
        except (TypeError, ValueError, error.CmdError), details:
            self.subtest.logdebug("docker inspect %s raised: %s: %s",
                                  long_id, details.__class__.__name__,
                                  str(details))
            return None

    def json_by_long_id(self, long_id):
        _json = self.get_container_metadata(long_id)
        if _json is None:
            raise ValueError("Metadata retrieval for container with long_id "
                             "%s not found or not supported" % long_id)
        else:
            return _json

    def kill_container_by_long_id(self, long_id):
        """
        Use docker CLI 'kill' command on container's long_id

        :return: pid of container's process
        """
        # Raise KeyError if not found
        try:
            _json = self.json_by_long_id(long_id)
        except TypeError:  # NoneType object blah blah blah
            raise KeyError("Container %s not found" % long_id)
        pid = _json[0]["State"]["Pid"]
        if not _json[0]["State"]["Running"] or not utils.pid_is_alive(pid):
            raise ValueError("Cannot kill container %s, it is not running,"
                             " or is a defunct or zombie process. Status: "
                             " %s." % (long_id, _json[0]["State"]))
        _signal = self.kill_signal
        cmd = 'kill '
        if _signal is not None:
            if _signal.upper().startswith('SIG'):
                _signal = _signal[3:]
            cmd += "--signal=%s " % str(_signal)
        cmd += str(long_id)
        if self.verify_output:
            dkrcmd = self.docker_cmd_check
        else:
            dkrcmd = self.docker_cmd
        self.subtest.logdebug("Killing %s with command: %s", long_id[:12], cmd)
        # Raise exception if not exit zero
        dkrcmd(cmd)
        return pid

    def kill_container_by_name(self, container_name):
        """
        Use docker CLI 'kill' command on container's long_id, by name lookup.

        :return: pid of container's process
        """
        cntrs = self.list_containers_with_name(str(container_name))
        try:
            return self.kill_container_by_long_id(cntrs[0].long_id)
        except IndexError:
            raise KeyError("Container %s not found" % container_name)

    def remove_by_id(self, image_id):
        """
        Use docker CLI to removes container matching long or short image_ID

        :returns: autotest.client.utils.CmdResult instance
        """
        if self.verify_output:
            dkrcmd = self.docker_cmd_check
        else:
            dkrcmd = self.docker_cmd
        if self.remove_args is not None:
            return dkrcmd("rm %s %s" % (self.remove_args, image_id),
                          self.timeout)
        else:
            return dkrcmd("rm %s" % (image_id), self.timeout)

    def wait_by_long_id(self, long_id):
        """
        :return: autotest.client.utils.CmdResult instance
        """
        # Validate parameters
        try:
            super(DockerContainersCLI, self).wait_by_long_id(long_id)
        except RuntimeError:
            pass  # expected
        _json = self.json_by_long_id(long_id)[0]
        if not _json["State"]["Running"]:
            return  # already exited
        if self.verify_output:
            dkrcmd = self.docker_cmd_check
        else:
            dkrcmd = self.docker_cmd
        return dkrcmd("wait %s" % (long_id), self.timeout)


class DockerContainers(DockerImages):

    """
    Exact same interface-encapsulator as images.DockerImages but for containers
    """

    #: Mapping of interface short-name string to DockerContainersBase subclass.
    interfaces = {'cli': DockerContainersCLI}
