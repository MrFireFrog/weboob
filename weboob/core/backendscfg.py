# -*- coding: utf-8 -*-

# Copyright(C) 2010-2011 Romain Bignon
#
# This file is part of weboob.
#
# weboob is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# weboob is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with weboob. If not, see <http://www.gnu.org/licenses/>.

import codecs
import stat
import os
import sys
try:
    from ConfigParser import RawConfigParser, DuplicateSectionError
except ImportError:
    from configparser import RawConfigParser, DuplicateSectionError
from logging import warning

from weboob.tools.compat import unicode


__all__ = ['BackendsConfig', 'BackendAlreadyExists']


class BackendAlreadyExists(Exception):
    pass


class BackendsConfig(object):
    """
    Config of backends.

    A backend is an instance of a module with a config.
    A module can thus have multiple instances.
    """

    class WrongPermissions(Exception):
        pass

    def __init__(self, confpath):
        self.confpath = confpath
        try:
            mode = os.stat(confpath).st_mode
        except OSError:
            if not os.path.isdir(os.path.dirname(confpath)):
                os.makedirs(os.path.dirname(confpath))
            if sys.platform == 'win32':
                fptr = open(confpath, 'w')
                fptr.close()
            else:
                try:
                    fd = os.open(confpath, os.O_WRONLY | os.O_CREAT, 0o600)
                    os.close(fd)
                except OSError:
                    fptr = open(confpath, 'w')
                    fptr.close()
                    os.chmod(confpath, 0o600)
        else:
            if sys.platform != 'win32':
                if mode & stat.S_IRGRP or mode & stat.S_IROTH:
                    raise self.WrongPermissions(
                        u'Weboob will not start as long as config file %s is readable by group or other users.' % confpath)

    def _read_config(self):
        config = RawConfigParser()
        with codecs.open(self.confpath, 'r', encoding='utf-8') as fd:
            config.readfp(fd)
        return config

    def _write_config(self, config):
        for section in config.sections():
            for k, v in config.items(section):
                if isinstance(v, unicode) and sys.version_info.major == 2:
                    # python2's configparser enforces bytes coercion with str(value)...
                    config.remove_option(section, k)
                    config.set(section, k.encode('utf-8'), v.encode('utf-8'))

        if sys.version_info.major == 2:
            f = open(self.confpath, 'wb')
        else:
            f = codecs.open(self.confpath, 'wb', encoding='utf-8')
        with f:
            config.write(f)

    def iter_backends(self):
        """
        Iterate on backends.

        :returns: each tuple contains the backend name, module name and module options
        :rtype: :class:`tuple`
        """

        config = self._read_config()
        changed = False
        for backend_name in config.sections():
            params = dict(config.items(backend_name))
            try:
                module_name = params.pop('_module')
            except KeyError:
                try:
                    module_name = params.pop('_backend')
                    config.set(backend_name, '_module', module_name)
                    config.remove_option(backend_name, '_backend')
                    changed = True
                except KeyError:
                    warning('Missing field "_module" for configured backend "%s"', backend_name)
                    continue
            yield backend_name, module_name, params

        if changed:
            self._write_config(config)

    def backend_exists(self, name):
        """
        Return True if the backend exists in config.
        """
        config = self._read_config()
        return name in config.sections()

    def add_backend(self, backend_name, module_name, params, edit=False):
        """
        Add a backend to config.

        :param backend_name: name of the backend in config
        :param module_name: name of the Python submodule to run
        :param params: params to pass to the module
        :type params: :class:`dict`
        """
        if not backend_name:
            raise ValueError(u'Please give a name to the configured backend.')
        config = self._read_config()
        if not edit:
            try:
                config.add_section(backend_name)
            except DuplicateSectionError:
                raise BackendAlreadyExists(backend_name)
        config.set(backend_name, '_module', module_name)
        for key, value in params.iteritems():
            config.set(backend_name, key, value)

        self._write_config(config)

    def edit_backend(self, backend_name, module_name, params):
        """Edit a backend from config."""
        return self.add_backend(backend_name, module_name, params, True)

    def get_backend(self, backend_name):
        """
        Get options of backend.

        :returns: a tuple with the module name and the module options dict
        :rtype: tuple
        """

        config = self._read_config()
        if not config.has_section(backend_name):
            raise KeyError(u'Configured backend "%s" not found' % backend_name)

        items = dict(config.items(backend_name))

        try:
            module_name = items.pop('_module')
        except KeyError:
            try:
                module_name = items.pop('_backend')
                self.edit_backend(backend_name, module_name, items)
            except KeyError:
                warning('Missing field "_module" for configured backend "%s"', backend_name)
                raise KeyError(u'Configured backend "%s" not found' % backend_name)
        return module_name, items

    def remove_backend(self, backend_name):
        """Remove a backend from config."""

        config = self._read_config()
        if not config.remove_section(backend_name):
            return False
        self._write_config(config)
        return True
