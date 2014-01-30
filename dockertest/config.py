"""
Extension of standard ConfigParser.SafeConfigParser abstracting section names
"""

import sys, os, os.path, logging
from collections import MutableMapping
import xceptions
from ConfigParser import SafeConfigParser

MYDIR = os.path.dirname(sys.modules[__name__].__file__)
PARENTDIR = os.path.dirname(MYDIR)
CONFIGDIR = os.path.join(PARENTDIR, 'config.d')
DEFAULTSFILE = 'defaults.ini'

class ConfigSection(object):
    """
    Wraps SafeConfigParser with static section handling
    """

    def __init__(self, defaults, section):
        """
        Create new config parser

        :param defaults: dict-like containing default keys/values
        :param section: name of section to initially bind to
        """
        self._section = section
        # SafeConfigParser is old-style, and we're changing method parameters
        self._scp = SafeConfigParser(defaults)
        self._scp.add_section(self._section)

    def defaults(self):
        """
        Returns dictionary of default options
        """
        return self._scp.defaults()

    def sections(self):
        """
        Returns a list containing this instances section-name
        """
        return [self._section]

    def add_section(self, section):
        """
        Add this instances section to config if it doesn't exist

        :param section: Section name to add

        :raise: dockertest.xceptions.DockerValueError
                If ``instance-section != section``
        """
        if section != self._section:
            raise xceptions.DockerValueError("Only section %s is supported "
                                             "for this instance"
                                             % self._section)
        else:
            return self._scp.add_section(self._section)

    def has_section(self, section):
        """
        Returns True if instance-section == section
        """
        if section == self._section:
            return True
        else:
            return False

    def options(self):
        """
        Returns dictionary of all options keys/values
        """
        return self._scp.options(self._section)

    def has_option(self, option):
        """
        Returns True if key-named option exists and is set to something
        """
        return self._scp.has_option(self._section, option)

    def _prune_sections(self):
        for section in self._scp.sections():
            if section != self._section:
                self._scp.remove_section(section)

    def read(self, filenames):
        """
        Replace current contents with content from filename(s)/list

        :param filenames: Same as for SafeConfigParser read method
        """
        result = self._scp.read(filenames)
        self._prune_sections()
        return result

    def readfp(self, fp, filename=None):
        """
        Replace current contents with content from file

        :param fp: Same as for SafeConfigParser readfp method
        :param filename: Same as for SafeConfigParser readfp method
        """
        result = self._scp.readfp(fp, filename)
        self._prune_sections()
        return result

    def get(self, option):
        """
        Return value assigned to key named option
        """
        return self._scp.get(self._section, option)

    def getint(self, option):
        """
        Convert/Return value assigned to key named option
        """
        return self._scp.getint(self._section, option)

    def getfloat(self, option):
        """
        Convert/Return value assigned to key named option
        """
        return self._scp.getfloat(self._section, option)

    def getboolean(self, option):
        """
        Convert/Return value assigned to key named option
        """
        return self._scp.getboolean(self._section, option)

    def set(self, option, value):
        """
        Set value assigned to key named option
        """
        return self._scp.set(self._section, option, str(value))

    def write(self, fileobject):
        """
        Overwrite current contents of fileobject.name
        """
        return self._scp.write(open(fileobject.name, "wb"))

    def merge_write(self, fileobject):
        """
        Update section contents of fileobject.name by instance section only.
        """
        scp = SafeConfigParser()
        # Safe if file doesn't exist
        scp.read(fileobject.name)
        if not scp.has_section(self._section):
            scp.add_section(self._section)
        for key, value in self.items():
            scp.set(self._section, key, value)
        scp.write(open(fileobject.name, "w+b"))  # truncates file first

    def remove_option(self, option):
        """
        Remove option-key option
        """
        return self._scp.remove_option(self._section, option)

    def remove_section(self):
        """
        Remove all options and section
        """
        return self._scp.remove_section(self._section)

    def items(self):
        """
        Return list of key/value tuples for all options and string contents
        """
        return self._scp.items(self._section)


class ConfigDict(MutableMapping):
    """Wraps ConfigSection instance in a dict-like"""

    def __init__(self, section, defaults=None, *args, **dargs):
        """
        Initialize a new dict-like for section using optional defaults dict-like
        """
        self._config_section = ConfigSection(defaults=defaults, section=section)
        super(ConfigDict, self).__init__(*args, **dargs)

    def _keyset(self):
        mine = set([val.lower()
                    for val in self._config_section.options()])
        default = set([val.lower()
                       for val in self._config_section.defaults().keys()])
        complete = mine | default
        return complete

    def __len__(self):
        return len(self._keyset())

    def __iter__(self):
        return (option for option in self._keyset())

    def __contains__(self, item):
        return item.lower() in self._keyset()

    def __getitem__(self, key):
        # ConfigParser forces this, force it so any errors are clear
        key = key.lower()
        # Don't call more methods than necessary
        if not self.__contains__(key):
            raise xceptions.DockerKeyError(key)
        # No suffix calls regular get(), boolean wants to gobble '0' and '1' :(
        for suffix in ('int', 'boolean', 'float', ''):
            method = getattr(self._config_section, 'get%s' % suffix)
            try:
                return method(key)
            except (ValueError, AttributeError):
                continue
        raise xceptions.DockerConfigError('', '', key)

    def __setitem__(self, key, value):
        return self._config_section.set(key, str(value))

    def __delitem__(self, key):
        return self._config_section.remove_option(key)

    def read(self, filelike):
        """Load configuration from file-like object filelike"""
        filelike.seek(0)
        return self._config_section.readfp(filelike)

    @staticmethod
    def write(filelike):
        """Raise an IOError exception"""
        raise xceptions.DockerIOError("Instance does not permit writing to %s"
                                       % filelike.name)


class Config(dict):
    """
    Dict-like of dict-like per section with default values from config.d files
    """
    defaults_ = None
    configs_ = None
    _singleton = None

    def __new__(cls, *args, **dargs):
        """
        Return new dict copy based on parsing of config.d + defaults
        """
        if cls._singleton is None:
            # Apply *args, *dargs _after_ making deep-copy
            cls._singleton = dict.__new__(cls)
        copy = cls._singleton.copy()  # deep-copy cache into regular dict
        copy.update(dict(*args, **dargs))
        return copy

    @property
    def defaults(self):
        if self.__class__.defaults_ is None:
            defaults_ = SafeConfigParser()
            defaults_.read(os.path.join(CONFIGDIR, DEFAULTSFILE))
            self.__class__.defaults_ = dict(defaults_.items('DEFAULTS'))
        return self.__class__.defaults_

    @property
    def configs(self):
        if self.__class__.configs_ is None:
            # Save some typing in loops below by also setting local reference
            configs_ = self.__class__.configs_ = {}
            for dirpath, dirnames, filenames in os.walk(CONFIGDIR):
                # These are not needed
                del dirnames
                for filename in filenames:
                    fullpath = os.path.join(dirpath, filename)
                    if (filename.startswith('.') or
                        not filename.endswith('.ini')):
                        logging.warning("Skipping unknown config file '%s'",
                                        fullpath)
                        continue
                    config_file = open(fullpath, 'r')
                    # Temp use sections variable for reading sections list
                    sections = SafeConfigParser()
                    sections.readfp(config_file)
                    sections = sections.sections()
                    for section in sections:
                        # First call to self.defaults will cache result
                        configs_[section] = ConfigDict(section, self.defaults)
                        # Will seek(0) and incorporate defaults
                        configs_[section].read(config_file)
        return self.__class__.configs_

    def copy(self):
        """
        Return deep-copy/export as a regular dict containing regular dicts
        """
        the_copy = {}
        for sec_key, sec_value in self.configs.items():
            sec_copy = {}
            for cfg_key, cfg_value in sec_value.items():
                sec_copy[cfg_key] = cfg_value
            the_copy[sec_key] = sec_copy
        return the_copy