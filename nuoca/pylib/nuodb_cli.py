#!/usr/bin/env python
# (C) Copyright NuoDB, Inc. 2018  All Rights Reserved.

import argparse
import collections
import datetime
import hashlib
import imp
import inspect
import json
import os
import re
import shutil
import string
import StringIO
import subprocess
import sys
import tempfile
import textwrap
import time
import threading
import traceback
import zipfile

from xml.etree import ElementTree

try:
    import requests
    import nuodb_mgmt
    requests_installed = True
except ImportError as e:
    # we expect an ImportError for requests if it is not installed; re-raise if
    # that is not the cause
    if e.message != 'No module named requests':
        raise e

    # we want to be able to do all checking in main method;
    # set nuodb_mgmt to be a dummy object that just raises this ImportError
    # whenever an attribute is accessed on it
    class _DelayImportError(object):
        def __getattr__(self, name):
            raise e

    nuodb_mgmt = _DelayImportError()
    requests_installed = False

try:
    # use argcomplete if it is available to enable tab-completion
    import argcomplete

    class NonrepeatingCompleter(argcomplete.CompletionFinder):
        """
        CompletionFinder subclass that removes arguments already specified.
        """

        def collect_completions(self, active_parsers, parsed_args,
                                cword_prefix, debug):
            # get completions from superclass and filter out any repeats

            # silence bogus pylint error, 'Use of super on an old style class'
            # pylint: disable=E1002
            completions = super(
                NonrepeatingCompleter, self).collect_completions(
                    active_parsers, parsed_args, cword_prefix, debug)
            return [arg for arg in completions
                    if not NonrepeatingCompleter._is_repeat(
                            arg, parsed_args, active_parsers[-1])]

        @staticmethod
        def _is_repeat(arg, parsed_args, parser):
            # ignore any tokens that don't have prefix
            if not arg.startswith('--'):
                return False
            dest = arg.lstrip('-').replace('-', '_')
            # since argparse injects defaults, we have to check that the value
            # is different from the default to see if it has been specified
            default = parser.get_default(dest)
            return getattr(parsed_args, dest, default) != default

    autocomplete = NonrepeatingCompleter()
    argcomplete_installed = True
except ImportError:
    # argcomplete is not available, so define autocomplete to be a no-op
    def autocomplete(parser):
        pass

    argcomplete_installed = False


def check_version():
    major, minor, micro = sys.version_info[:3]
    if (major, minor) != (2, 7):
        sys.stderr.write('NuoDB Management CLI requires Python 2.7\n')
        sys.stderr.write('Invoked with Python version {}.{}.{} ({})\n'.format(
            major, minor, micro, sys.executable))
        sys.exit(1)


def from_nuodb_home(*args):
    if 'NUODB_HOME' in os.environ:
        return os.path.join(os.environ['NUODB_HOME'], *args)
    # NUODB_HOME is not set, so try to infer it from nuocmd location assuming
    # that nuocmd is in $NUODB_HOME/drivers/pynuoadmin
    nuocmd_dir = get_nuocmd_dir()
    nuodb_home = os.path.dirname(os.path.dirname(nuocmd_dir))
    # if file exists, return it
    filepath = os.path.join(nuodb_home, *args)
    if os.path.exists(filepath):
        return filepath


def get_nuocmd_dir():
    nuocmd_file = os.path.abspath(__file__)
    return os.path.dirname(nuocmd_file)


def get_install_commands():
    # if setup script does not exist, there is nothing to do
    nuocmd_dir = get_nuocmd_dir()
    setup_script = os.path.join(nuocmd_dir, 'setup.py')
    if not os.path.exists(setup_script):
        return []
    install_cmd = '{} -m pip install "{}[completion]"'.format(
        sys.executable, nuocmd_dir)
    try:
        # if pip is already installed, just invoke it with the same Python
        # interpreter this is running in (we're assuming nuocmd chose it
        # because its the most suitable one) to install all dependencies
        imp.find_module('pip')
        return [install_cmd]
    except ImportError:
        # otherwise the user has to download pip and install it; also
        # install all nuocmd dependencies
        major, minor, micro = sys.version_info[:3]
        if micro >= 9:
            # ensurepip introduced in version 2.7.9
            return [sys.executable + ' -m ensurepip', install_cmd]
        else:
            # ensurepip not available, so use get-pip.py
            return ['curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py',
                    sys.executable + ' get-pip.py', install_cmd]


def check_dependencies():
    # requests is the only required non-standard dependency; since we're
    # requiring Python 2.7, we know that argparse is available
    if not requests_installed:
        sys.stderr.write('NuoDB Management CLI requires \'requests\' module\n')
        install_commands = get_install_commands()
        if len(install_commands) != 0:
            sys.stderr.write('To install dependencies run the following:\n')
            for command in install_commands:
                sys.stderr.write('  {}\n'.format(command))
        sys.exit(1)


def exceptional_fn(callable):
    def catch_exc(*args, **kwargs):
        try:
            callable(*args, **kwargs)
        except Exception:
            threading.current_thread().exc = sys.exc_info()
    return catch_exc


class ShowInstallCommandsAction(argparse.Action):
    """
    Action invoked if --show-install-commands is specified. Displays commands
    to install dependencies and exit.
    """

    def __init__(self, option_strings, dest=argparse.SUPPRESS,
                 default=argparse.SUPPRESS, help=None):
        super(ShowInstallCommandsAction, self).__init__(
            option_strings=option_strings, dest=dest, default=default, nargs=0,
            help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        for line in get_install_commands():
            print(line)
        sys.exit(0)


class CustomHelpFormatter(argparse.RawTextHelpFormatter):
    """
    HelpFormatter that shows defaults similarly to
    argparse.ArgumentDefaultsHelpFormatter but with some minor tweaks.
    """

    def _get_help_string(self, action):
        help = '\n'.join(textwrap.wrap(action.help))
        if (action.default and '%(default)' not in action.help and
            action.default is not argparse.SUPPRESS):  # noqa
            defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
            if action.option_strings or action.nargs in defaulting_nargs:
                if (isinstance(action.default, basestring) and
                    len(action.default.split()) > 1):  # noqa
                    # default value is a string that has spaces in it; add
                    # quotes around it for clarity
                    help += '\n(default: \'%(default)s\')'
                else:
                    help += '\n(default: %(default)s)'
        return help


class Subcommand(object):
    """
    Decorator applied to methods of AdminCommands to associate them with
    subcommands.
    """

    def __init__(self, action, entity, **kwargs):
        """
        :param str action: the action
        :param str entity: the object to perform action on
        :param dict kwargs: kwargs applicable to ArgumentParser.add_parser()
        """

        self.action = action
        self.entity = entity
        self.kwargs = kwargs

    def __call__(self, func):
        func._is_subcommand = True
        func._action = self.action
        func._entity = self.entity
        func._kwargs = self.kwargs
        return func

    @staticmethod
    def add_subcommand(processor, func):
        if not getattr(func, '_is_subcommand', False):
            return

        if func._action not in processor.sp_dict:
            processor.sp_dict[func._action] = processor.subparsers.add_parser(
                func._action).add_subparsers(
                    title='\'{}\' subcommands'.format(func._action))
        parser = processor.sp_dict[func._action].add_parser(
            func._entity, formatter_class=CustomHelpFormatter, **func._kwargs)
        # associate `func` with the function to invoke for this subcommand
        parser.set_defaults(func=func)
        # add arguments that the function was decorated with
        for arg_spec in Argument.get_arg_specs(func):
            arg_spec.add_argument(parser)


class EnvironmentalDefault(object):

    ENV_PREFIX = 'NUOCMD_'

    def __init__(self, default=None):
        """
        :param object default: the default to use if there is no value inferred
                               from the environment
        """

        self.default = default

    def __call__(self, arg_name):
        field_name = arg_name.lstrip('-').replace('-', '_')
        env_var = EnvironmentalDefault.ENV_PREFIX + field_name.upper()
        return os.environ.get(env_var, self.default)


class Argument(object):
    """
    Decorator to apply to methods to specify arguments. All arguments
    appearing in the signature of the method must have a corresponding
    Argument decorator.

    Example:

    ```
    @Subcommand('do', 'something')
    @Argument('--the-arg')
    def do_something(self, the_arg):
        ...
    ```

    """

    @staticmethod
    def inject_env_default(args, kwargs):
        default = kwargs.get('default')
        if isinstance(default, EnvironmentalDefault):
            kwargs['default'] = default(args[0])
            # if a default was inferred, remove required=True so that the
            # parameter does not have to be explicitly specified
            if kwargs['default'] is not None and kwargs.get('required', False):
                del kwargs['required']

    def __init__(self, *args, **kwargs):
        """
        :param tuple args: args applicable to ArgumentParser.add_argument()
        :param dict kwargs: kwargs applicable to ArgumentParser.add_argument()
        """

        self.inject_env_default(args, kwargs)
        self.args = args
        self.kwargs = kwargs

    def __call__(self, func):
        func.arg_specs = [self] + Argument.get_arg_specs(func)
        return func

    def add_argument(self, parser):
        completer = self.kwargs.pop('completer', None)
        ret = parser.add_argument(*self.args, **self.kwargs)
        # add value completer if one was specified
        if completer is not None:
            ret.completer = completer

    @staticmethod
    def get_arg_specs(func):
        return getattr(func, 'arg_specs', [])


class MutuallyExclusive(Argument):
    """
    Decorator to wrap multiple Arguments to specify that the arguments are
    mutually exclusive.

    Example:

    ```
    @Subcommand('do', 'something')
    @MutuallyExclusive(Argument('--this'), Argument('--that'))
    def do_something(self, this=None, that=None):
        # either this or that is specified, but not both
        ...
    ```

    """

    def __init__(self, *arg_specs, **kwargs):
        self.arg_specs = arg_specs
        self.kwargs = kwargs

    def add_argument(self, parser):
        group = parser.add_mutually_exclusive_group(**self.kwargs)
        for arg_spec in self.arg_specs:
            arg_spec.add_argument(group)


class CommandProcessor(object):
    """
    The main class used to build argument parser and execute commands.
    """

    DEFAULT_API_SERVER = 'localhost:8888'
    FOREVER = 9999999999

    @classmethod
    def _get_admin_conn(cls, parsed_args):
        client_key = parsed_args.client_key
        if client_key is not None and ',' in client_key:
            client_key = client_key.split(',')
            if len(client_key) != 2:
                raise ValueError(
                    'Expected at most two tokens for --client-key')
        api_server = parsed_args.api_server
        if (not api_server.startswith('http://') and
            not api_server.startswith('https://')):  # noqa
            if client_key is None:
                api_server = 'http://' + api_server
            else:
                api_server = 'https://' + api_server
        # set server verification as follows:
        # 1. if HTTP, set to None
        # 2. if --no-verify specified, set to False and disable any warning
        #    messages emitted about unverified HTTPS requests
        # 3. if trusted certificate specified with --verify-server, use it
        # 4. otherwise, set to True so that system CA certificates are used to
        #    verify server
        verify = None
        if api_server.startswith('https://'):
            if parsed_args.no_verify:
                verify = False
                nuodb_mgmt.disable_ssl_warnings()
            elif parsed_args.verify_server is not None:
                verify = parsed_args.verify_server
            else:
                verify = True

        return nuodb_mgmt.AdminConnection(api_server, client_key, verify)

    @staticmethod
    def get_archive(parsed_args):
        """
        :returns nuodb_mgmt.Archive:
        """

        try:
            # if --archive-id is specified, return the archive
            if (hasattr(parsed_args, 'archive_id') and
                parsed_args.archive_id is not None):  # noqa
                return CommandProcessor._get_admin_conn(
                    parsed_args).get_archive(
                        parsed_args.archive_id)
        except:
            pass

    @staticmethod
    def get_server_ids(prefix, parsed_args, **kwargs):
        try:
            # if --archive-id is specified, return the server it belongs to
            archive = CommandProcessor.get_archive(parsed_args)
            if archive is not None and archive.server_id is not None:
                return [archive.server_id]

            servers = CommandProcessor._get_admin_conn(
                parsed_args).get_servers(
                    id='{}.*'.format(prefix))
            return [server.id for server in servers]
        except:
            return []

    @staticmethod
    def get_db_names(prefix, parsed_args, **kwargs):
        try:
            # if --archive-id is specified, return the database it belongs to
            archive = CommandProcessor.get_archive(parsed_args)
            if archive is not None:
                return [archive.db_name]

            databases = CommandProcessor._get_admin_conn(
                parsed_args).get_databases(
                    name='{}.*'.format(prefix))
            return [db.name for db in databases]
        except:
            return []

    @staticmethod
    def get_db_names_from_archives(prefix, parsed_args, **kwargs):
        try:
            conn = CommandProcessor._get_admin_conn(parsed_args)
            archives = conn.get_archives()
            databases = conn.get_databases(name='{}.*'.format(prefix))
            db_names = [db.name for db in databases if db.state != 'TOMBSTONE']
            return set(archive.db_name for archive in archives
                       if archive.db_name not in db_names)
        except:
            return []

    @staticmethod
    def get_archive_ids(prefix, parsed_args, **kwargs):
        try:
            archives = CommandProcessor._get_admin_conn(
                parsed_args).get_archives(
                    parsed_args.db_name, id='{}.*'.format(prefix))
            return [str(archive.id) for archive in archives]
        except:
            return []

    @staticmethod
    def get_non_running_archive_ids(prefix, parsed_args, **kwargs):
        try:
            archives = CommandProcessor._get_admin_conn(
                parsed_args).get_archives(
                    parsed_args.db_name, id='{}.*'.format(prefix))
            return [str(archive.id) for archive in archives
                    if getattr(parsed_args, 'server_id', None) is None
                    or archive.server_id == parsed_args.server_id
                    or archive.server_id is None]
        except:
            return []

    @staticmethod
    def get_running_archive_ids(prefix, parsed_args, **kwargs):
        try:
            archives = CommandProcessor._get_admin_conn(
                parsed_args).get_archives(
                    parsed_args.db_name, id='{}.*'.format(prefix),
                    state='RUNNING')
            return [str(archive.id) for archive in archives]
        except:
            return []

    @staticmethod
    def get_region_names(prefix, parsed_args, **kwargs):
        try:
            regions = CommandProcessor._get_admin_conn(
                parsed_args).get_regions(
                    name='{}.*'.format(prefix))
            return [str(region.name) for region in regions]
        except:
            return []

    @staticmethod
    def get_region_ids(prefix, parsed_args, **kwargs):
        try:
            regions = CommandProcessor._get_admin_conn(
                parsed_args).get_regions(
                    id='{}.*'.format(prefix))
            return [str(region.id) for region in regions]
        except:
            return []

    @staticmethod
    def get_dict_completer(arg_name, key_completer, value_completer,
                           unique_values=False):
        def func(prefix, parsed_args, **kwargs):
            try:
                # check if we have an odd or even number of tokens
                tokens = getattr(parsed_args, arg_name, None)
                if tokens is not None and len(tokens) % 2 == 1:
                    # use value completer if odd
                    values = value_completer(prefix, parsed_args,
                                             **kwargs)
                    if unique_values:
                        # filter out values already entered
                        values_seen = CommandProcessor.dict_from_tokens(
                            tokens[:-1]).values()
                        return [value for value in values
                                if value not in values_seen]
                    return values
                # use key completer if even; filter out keys already entered
                keys_seen = CommandProcessor.dict_from_tokens(tokens).keys()
                return [key for key
                        in key_completer(prefix, parsed_args, **kwargs)
                        if key not in keys_seen]
            except:
                return []
        return func

    @staticmethod
    def get_region_assignment_token(prefix, parsed_args, **kwargs):
        return CommandProcessor.get_dict_completer(
            'region_assignment',
            CommandProcessor.get_server_ids,
            CommandProcessor.get_region_names)(prefix, parsed_args, **kwargs)

    @staticmethod
    def get_archive_assignment_token(prefix, parsed_args, **kwargs):
        return CommandProcessor.get_dict_completer(
            'archive_assignment',
            CommandProcessor.get_non_running_archive_ids,
            CommandProcessor.get_server_ids)(prefix, parsed_args, **kwargs)

    @staticmethod
    def get_backup_dirs_token(prefix, parsed_args, **kwargs):
        return CommandProcessor.get_dict_completer(
            'backup_dirs',
            CommandProcessor.get_running_archive_ids,
            lambda *args, **kwargs: [])(prefix, parsed_args, **kwargs)

    @staticmethod
    def get_option_keys(prefix, parsed_args, engine_options=False):
        try:
            types = ['SIMPLE']
            if engine_options:
                types += ['PROCESS_ONLY']
            else:
                types += ['DATABASE_ONLY']
            options = CommandProcessor._get_admin_conn(
                parsed_args).get_process_options()
            return [option[2:] for option, option_type in options.items()
                    if option[2:].startswith(prefix) and option_type in types]
        except:
            return []

    @staticmethod
    def get_engine_options_completer(arg_name, engine_options=True):
        def key_fn(prefix, parsed_args, **kwargs):
            return CommandProcessor.get_option_keys(
                prefix, parsed_args, engine_options=engine_options)
        return CommandProcessor.get_dict_completer(
            arg_name, key_fn, lambda *args, **kwargs: [])

    @staticmethod
    def get_captured_stable_ids(prefix, parsed_args, **kwargs):
        try:
            capture_xml = ElementTree.parse(parsed_args.capture_file)
            return [host.attrib['StableId']
                    for host in capture_xml.findall('./Hosts/Host')
                    if 'StableId' in host.attrib]
        except:
            return []

    @staticmethod
    def get_server_mapping_token(prefix, parsed_args, **kwargs):
        return CommandProcessor.get_dict_completer(
            'server_mapping',
            CommandProcessor.get_captured_stable_ids,
            CommandProcessor.get_server_ids,
            True)(prefix, parsed_args, **kwargs)

    @staticmethod
    def get_epilog():
        """
        Return a message that is appended to help output describing how to
        enable to tab completion.
        """

        completion_file = os.path.join(get_nuocmd_dir(), 'nuocmd-complete')
        # if completion file isn't found for some reason, don't bother
        if not os.path.exists(completion_file):
            return None

        return 'To enable tab completion in bash:\n  . ' + completion_file

    @staticmethod
    def dict_from_tokens(tokens, key_type=str, value_type=str):
        if tokens is None or len(tokens) == 0:
            return {}

        if len(tokens) % 2 != 0:
            raise ValueError('Cannot convert odd number of tokens to dict: '
                             + str(tokens))
        ret = {}
        for i in xrange(0, len(tokens), 2):
            key = key_type(tokens[i])
            if key in ret:
                raise ValueError('Duplicate key in dict: ' + str(key))
            ret[key] = value_type(tokens[i + 1])
        return ret

    @staticmethod
    def incarnation_from_str(s):
        parts = s.split('.')
        if len(parts) == 1 and parts[0].isdigit():
            return dict(major=int(parts[0]))
        if len(parts) == 2 and all(map(str.isdigit, parts)):
            major, minor = map(int, parts)
            return dict(major=major, minor=minor)
        raise argparse.ArgumentTypeError(
            'Cannot convert \'{}\' to incarnation. Expected format \'<major>[.<minor>]\' where \'major\' and \'minor\' are both integers'.format(s))  # noqa

    def _add_argument(self, *args, **kwargs):
        Argument.inject_env_default(args, kwargs)
        self.parser.add_argument(*args, **kwargs)

    def __init__(self):
        # global arguments relevant for all commands
        self.parser = argparse.ArgumentParser(
            'nuocmd', description='NuoDB Management CLI',
            epilog=CommandProcessor.get_epilog(),
            formatter_class=CustomHelpFormatter)
        self._add_argument('--api-server',
                           default=EnvironmentalDefault(CommandProcessor.DEFAULT_API_SERVER),  # noqa
                           help='the REST API server to send request to')
        self._add_argument('--show-json', action='store_true',
                           help='show the full JSON response')
        self._add_argument('--show-json-fields', required=False,
                           help='the JSON fields to show from the response')
        self._add_argument('--debug', action='store_true',
                           default=EnvironmentalDefault(),
                           help=argparse.SUPPRESS)
        self._add_argument('--show-install-commands',
                           action=ShowInstallCommandsAction,
                           help=argparse.SUPPRESS)
        self._add_argument('--client-key', required=False,
                           default=EnvironmentalDefault(),
                           help='client key-pair if server requires client authentication (see \'needClientAuth\' REST setting); specified as a single file containing both certificate and private key, or as \'<certificate>,<private key>\'')  # noqa
        self._add_argument('--verify-server', required=False,
                           default=EnvironmentalDefault(),
                           help='trusted certificate used to verify the server when using HTTPS; if no argument is specified then the default set of trusted CA certificates for the system is used')  # noqa
        self._add_argument('--no-verify', action='store_true',
                           help='if specified, then server verification is disabled; this takes precedence over --verify-server')  # noqa

        # add subcommands for each action and build dictionary of subparsers
        self.subparsers = self.parser.add_subparsers(title='subcommands')
        self.sp_dict = {}
        # sort methods by name so that subcommands are displayed in a
        # consistent order
        methods = inspect.getmembers(AdminCommands, inspect.ismethod)
        methods.sort(key=lambda pair: pair[0])
        for pair in methods:
            name, method = pair
            # have to pass in `im_func` since that is the object that metadata
            # was added to by the decorator
            Subcommand.add_subcommand(self, method.im_func)

    def execute(self, argv=None, out=sys.stdout, err=sys.stderr,
                command_handler=None):
        """
        Parse arguments and execute command using registered command method
        for supplied subcommand.

        :param list[str] argv: arguments to parse; if None, use `sys.argv[1:]`
        """

        autocomplete(self.parser)
        args = self.parser.parse_args(argv)
        conn = self._get_admin_conn(args)
        if command_handler is None:
            command_handler = AdminCommands
        # combine --show-json and --show-json-fields to form a ternary value to
        # indicate whether we should dump raw JSON response, and if so, should
        # we filter the set of attributes to dump
        show_json = args.show_json_fields or args.show_json
        commands = command_handler(conn, show_json, out)
        # args.func is set to the AdminCommands method associated with
        # the invoked subcommand
        if 'func' in args:
            # create kwargs for method by filtering out all global parameters
            kwargs = dict((k, v) for k, v in args._get_kwargs()
                          if k not in ['api_server', 'show_json',
                                       'show_json_fields', 'debug', 'func',
                                       'client_key', 'verify_server',
                                       'no_verify'])
            try:
                return args.func(commands, **kwargs)
            except Exception as e:
                # if debug is set, show stacktrace
                if args.debug:
                    traceback.print_exc(file=err)
                # avoid cryptic error message from requests
                if isinstance(e, requests.exceptions.ConnectionError):
                    err.write('Unable to connect to {}: {}\n'.format(
                        conn.url_base, str(e)))
                else:
                    err.write('\'{} {}\' failed: {}\n'.format(
                        args.func._action, args.func._entity, str(e)))
                sys.exit(1)
            except SystemExit as e:
                # if debug is set, show stacktrace; this is in a separate
                # `except` clause because SystemExit does not subclass
                # Exception
                if args.debug:
                    traceback.print_exc(file=err)
                sys.exit(e.code)
            except KeyboardInterrupt:
                if args.debug:
                    traceback.print_exc(file=err)
                err.write("Exiting due to interrupt...\n")
                sys.exit(1)


class AdminCommands(object):
    """
    Class containing all registered subcommands.
    """

    def __init__(self, conn, show_json=False, out=sys.stdout, err=sys.stderr):
        """
        :param nuodb_mgmt.AdminConnection conn:
        """

        self.conn = conn
        self.show_json = show_json
        self.out = out
        self.err = err

    @Subcommand('get', 'processes', help='get database processes')
    @Argument('--db-name', required=False, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database to list processes for')
    @Argument('--exited', action='store_true', help='get exited processes')
    def get_processes(self, db_name=None, exited=False):
        func = (self.conn.get_exited_processes if exited
                else self.conn.get_processes)
        procs = func() if db_name is None else func(db_name)
        for proc in procs:
            self._show(proc)
        return procs

    @Subcommand('start', 'process', help='start a database process')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database for the process')
    @MutuallyExclusive(
        Argument('--server-id',
                 completer=CommandProcessor.get_server_ids,
                 help='the ID of the server the process belongs to'),
        Argument('--this-server', action='store_true',
                 help='whether to start process through API server'),
        required=True)
    @Argument('--engine-type', choices=['TE', 'SM', 'SSM'],
              help='the engine type')
    @Argument('--archive-id', required=False,
              completer=CommandProcessor.get_non_running_archive_ids,
              help='the ID of the archive if engine-type is SM or SSM')
    @Argument('--expected-incarnation', required=False,
              type=CommandProcessor.incarnation_from_str,
              help='the expected incarnation for the database in the form \'<major>[.<minor>]\'')  # noqa
    @Argument('--nuodb-cmd', required=False,
              help='the command to invoke the NuoDB executable, if starting externally')  # noqa
    @Argument('--options', required=False, nargs='*',
              completer=CommandProcessor.get_engine_options_completer(
                  'options', engine_options=True),
              help='engine options')
    @Argument('--labels', required=False, nargs='*',
              help='labels for engine process')
    def start_process(self, db_name, server_id, engine_type, archive_id=None,
                      nuodb_cmd=None, options=None, this_server=False,
                      expected_incarnation=None, labels=None):
        server_id, config = self._get_server_id(server_id, this_server)
        if not isinstance(options, collections.Mapping):
            options = CommandProcessor.dict_from_tokens(options)
        if not isinstance(labels, collections.Mapping):
            labels = CommandProcessor.dict_from_tokens(labels)
        major = None
        minor = None
        if expected_incarnation is not None:
            major = expected_incarnation.get('major')
            minor = expected_incarnation.get('minor')
        return self._start_process(
            db_name, server_id, engine_type, archive_id=archive_id,
            incarnation_major=major, incarnation_minor=minor,
            nuodb_cmd=nuodb_cmd, is_cmd=True, labels=labels, **options)

    def _start_process(self, db_name, server_id, engine_type, archive_id=None,
                       incarnation_major=None, incarnation_minor=None,
                       nuodb_cmd=None, is_cmd=False, labels=None, **options):
        is_external = nuodb_cmd is not None
        proc_info = self.conn.start_process(
            db_name, server_id, engine_type,
            archive_id, is_external,
            incarnation_major=incarnation_major,
            incarnation_minor=incarnation_minor,
            labels=labels, **options)
        if is_external:
            # start process externally
            # define environment variables that `nuodb_cmd` can use to get
            # information about the process that's being started
            env = dict(os.environ,
                       DB_NAME=db_name,
                       ENGINE_TYPE=engine_type,
                       START_ID=proc_info.start_id)
            if archive_id is not None:
                env['ARCHIVE_ID'] = str(archive_id)
                env['ARCHIVE'] = self.conn.get_archive(archive_id).archive_path
            ret = subprocess.call(
                nuodb_cmd.split() + proc_info['commandLineArgs'], env=env)
            if is_cmd:
                # invoked as "start process" subcommand; otherwise, `nuodb_cmd`
                # needs to be asynchronous (i.e. it forks off the nuodb
                # process, possibly in a container, and then exits), and in
                # that case we do not care about the exit code and we want to
                # start other nuodb processes since we are starting the entire
                # database using "start/enforce/create database" subcommands
                sys.exit(ret)
        elif is_cmd:
            # invoked as "start process" subcommand, so print the started
            # process; otherwise, this was invoked inside of
            # "start/enforce/create database" subcommands, which print started
            # processes themselves
            self._show(proc_info)
        return proc_info

    @Subcommand('shutdown', 'process', help='shutdown a database process')
    @Argument('--start-id', required=True,
              help='the start ID of the process to shutdown')
    @MutuallyExclusive(
        Argument('--evict', action='store_true',
                 help='evict process from database'),
        Argument('--kill', action='store_true',
                 help='forcibly kill process'),
        Argument('--kill-with-core', action='store_true',
                 help='forcibly kill process and dump core'),
        required=False)
    @Argument('--timeout', required=False,
              help='the timeout in seconds to wait for the process to disconnect from the admin server; if not specified, the shutdown request is issued without waiting')  # noqa
    def shutdown_process(self, start_id, evict=False, kill=False,
                         kill_with_core=False, timeout=None):
        if timeout is None:
            timeout = 0
        self.conn.shutdown_process(start_id, evict, kill, kill_with_core,
                                   timeout)

    @Subcommand('get', 'databases', help='get database state')
    def get_databases(self):
        databases = self.conn.get_databases()
        for db in databases:
            self._show(db)
        return databases

    @Subcommand('create', 'database',
                help='create a database, but do not start any processes')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names_from_archives,
              help='the name of the database')
    @Argument('--dba-user', required=True, default=EnvironmentalDefault(),
              help='the database administrator user')
    @Argument('--dba-password', required=True, default=EnvironmentalDefault(),
              help='the database administrator password')
    @Argument('--te-server-ids', nargs='+', required=False,
              completer=CommandProcessor.get_server_ids,
              help='the IDs of the servers to start TEs on')
    @MutuallyExclusive(
        Argument('--capture-file',
                 help='the path to the file to capture database to'),
        Argument('--nuodb-cmd',
                 help='the command to invoke the NuoDB executable, if starting externally'),  # noqa
        required=False)
    @Argument('--is-external', action='store_true',
              help='whether database processes will be started externally')
    @Argument('--archive-assignment', nargs='+', required=False,
              completer=CommandProcessor.get_archive_assignment_token,
              help='mapping of archive ID to server ID, for external start')
    @Argument('--region-assignment', required=False, nargs='*',
              completer=CommandProcessor.get_region_assignment_token,
              help='mapping of server ID to region name')
    @Argument('--default-options', required=False, nargs='*',
              completer=CommandProcessor.get_engine_options_completer(
                  'default_options', engine_options=False),
              help='default engine options')
    def create_database(self, db_name, dba_user, dba_password,
                        default_options=None, te_server_ids=None,
                        capture_file=None, is_external=False, nuodb_cmd=None,
                        archive_assignment=None, region_assignment=None):
        if not isinstance(default_options, collections.Mapping):
            options = CommandProcessor.dict_from_tokens(default_options)
        else:
            options = default_options
        if is_external and capture_file is None and nuodb_cmd is None:
            raise ValueError('If --is-external is specified, one of --capture-file, --nuodb-cmd must be specified')  # noqa
        if is_external or nuodb_cmd is not None:
            options['ext-start'] = True
        elif archive_assignment is not None:
            raise ValueError('--archive-assignment requires --is-external')
        if not isinstance(archive_assignment, collections.Mapping):
            archive_assignment = CommandProcessor.dict_from_tokens(
                archive_assignment, key_type=int)
        if not isinstance(region_assignment, collections.Mapping):
            regions_by_name = self._get_regions_by_name()
            region_assignment = CommandProcessor.dict_from_tokens(
                region_assignment,
                value_type=lambda region_name: self._get_region_id(
                    region_name, regions_by_name))
        startplan = self.conn.create_database(
            db_name, dba_user, dba_password, te_server_ids=te_server_ids,
            host_assignments=region_assignment,
            archive_assignment=archive_assignment, **options)

        # start database if no capture file is specified
        if capture_file is None:
            for proc in startplan['processes']:
                try:
                    self._start_process_iter(
                        nuodb_mgmt.StartProcessRequest(proc),
                        nuodb_cmd=nuodb_cmd)
                except Exception as e:
                    self._raise_on_failed_process(db_name, 1, str(e))
        else:
            self._write_json(startplan, capture_file)

    @Subcommand('delete', 'database', help='delete a non-running database')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database to delete')
    def delete_database(self, db_name):
        self.conn.delete_database(db_name)

    @Subcommand('capture', 'database',
                help='capture the state of a running database')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database to capture')
    @Argument('--capture-file', required=True,
              help='the path to the file to write startplan to')
    def capture_database(self, db_name, capture_file):
        self._write_json(self.conn.capture_database(db_name),
                         capture_file)

    @Subcommand('get', 'startplan', help='get the startplan for a database')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database')
    @Argument('--output-file', required=True,
              help='the path to the file to capture database to')
    @Argument('--te-server-ids', nargs='+', required=False,
              completer=CommandProcessor.get_server_ids,
              help='the IDs of the servers to start additional TEs on')
    @Argument('--archive-assignment', nargs='+', required=False,
              completer=CommandProcessor.get_archive_assignment_token,
              help='mapping of archive ID to server ID, for external start')
    @Argument('--one-time', action='store_true',
              help='get a startplan for one-time use')
    def get_startplan(self, db_name, output_file, te_server_ids=None,
                      archive_assignment=None, one_time=False):
        if not isinstance(archive_assignment, collections.Mapping):
            archive_assignment = CommandProcessor.dict_from_tokens(
                archive_assignment, key_type=int)
        startplan = self.conn.get_database_startplan(
            db_name, not one_time, te_server_ids, archive_assignment)
        self._write_json(startplan, output_file)

    def _write_json(self, data, output_file):
        with open(output_file, 'w') as f:
            f.write(json.dumps(data, indent=2, sort_keys=True))
            f.write('\n')

    @Subcommand('start', 'database', help='start a database')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database to start')
    @Argument('--te-server-ids', nargs='+', required=False,
              completer=CommandProcessor.get_server_ids,
              help='the IDs of the servers to start additional TEs on')
    @Argument('--archive-assignment', nargs='+', required=False,
              completer=CommandProcessor.get_archive_assignment_token,
              help='mapping of archive ID to server ID, for external start')
    @Argument('--incremental', action='store_true',
              help='start the database incrementally based on running state')
    @Argument('--nuodb-cmd', required=False,
              help='the command to invoke the NuoDB executable, if starting externally')  # noqa
    def start_database(self, db_name=None, te_server_ids=None,
                       archive_assignment=None, incremental=False,
                       nuodb_cmd=None):
        if not isinstance(archive_assignment, collections.Mapping):
            archive_assignment = CommandProcessor.dict_from_tokens(
                archive_assignment, key_type=int)
        startplan = self.conn.get_database_startplan(
            db_name, reusable=False, te_server_ids=te_server_ids,
            archive_assignment=archive_assignment)
        AdminCommands._check_incremental(
            db_name, incremental, startplan.get('incremental', False))
        processes = map(nuodb_mgmt.StartProcessRequest, startplan['processes'])
        for proc in processes:
            try:
                self._start_process_iter(proc, nuodb_cmd=nuodb_cmd)
            except Exception as e:
                self._raise_on_failed_process(db_name,
                                              proc.expected_incarnation_major,
                                              str(e))
        return processes

    @staticmethod
    def _check_incremental(db_name, expected, actual):
        if expected and not actual:
            raise RuntimeError(
                'Database ' + db_name +
                ' is not running and --incremental was specified')
        elif not expected and actual:
            raise RuntimeError(
                'Database ' + db_name +
                ' is running and --incremental was not specified')

    @Subcommand('enforce', 'database', help='start a database')
    @Argument('--capture-file', required=True,
              help='the path to the capture file to enforce')
    @Argument('--incremental', action='store_true',
              help='start the database incrementally based on running state')
    @Argument('--nuodb-cmd', required=False,
              help='the command to invoke the NuoDB executable, if starting externally')  # noqa
    def enforce_database(self, capture_file=None, incremental=False,
                         nuodb_cmd=None):
        db_name, processes = read_capture_file(capture_file)
        # make sure archives in capture file match provisioned archives
        archive_ids = set(proc['archiveId'] for proc in processes
                          if proc.get('archiveId') is not None)
        expected_archive_ids = set(archive.id for archive in
                                   self.conn.get_archives(db_name))
        if archive_ids != expected_archive_ids:
            unexpected = archive_ids.difference(expected_archive_ids)
            missing = expected_archive_ids.difference(archive_ids)
            messages = []
            if len(unexpected) != 0:
                messages.append(
                    'Unexpected archives found in capture file: {}'
                    .format(list(unexpected)))
            if len(missing) != 0:
                messages.append(
                    'Expected archives not found in capture file: {}'
                    .format(list(missing)))
            raise ValueError(
                'Archives in capture file do not match provisioned archives: '
                + '; '.join(messages))
        # get the expected incarnation after starting database
        expected_incarnation = self.conn.get_database(db_name).incarnation
        if not incremental:
            expected_incarnation = (expected_incarnation[0] + 1, 0)

        # capture running processes
        _, running = read_capture_data(
            self.conn.capture_database(db_name, check_state=False))
        AdminCommands._check_incremental(
            db_name, incremental, len(running) != 0)

        # keep track of remaining TEs for each server
        num_remaining = {}
        for proc in processes:
            if proc.engine_type != 'TE':
                continue
            if proc.server_id not in num_remaining:
                num_remaining[proc.server_id] = 0
            num_remaining[proc.server_id] += 1

        running_archives = []
        for proc in running:
            if proc.engine_type != 'TE':
                running_archives.append(proc.archive_id)
            else:
                if proc.server_id in num_remaining:
                    num_remaining[proc.server_id] -= 1

        for proc in processes:
            if proc in running:
                # exact match; remove corresponding element from running list
                running.remove(proc)
                self._print('SKIPPING: {}: already running', proc)
            elif proc.archive_id in running_archives:
                # archive is running, but with different options
                self._print('SKIPPING: {}: archive ID {} is already running',
                            proc, proc.archive_id)
            elif (proc.engine_type == 'TE' and
                  num_remaining[proc.server_id] <= 0):  # noqa
                # not an exact match, but TE count on server reached
                self._print('SKIPPING: {}: engine count on {} reached',
                            proc, proc.server_id)
            else:
                if proc.engine_type == 'TE':
                    num_remaining[proc.server_id] -= 1
                try:
                    proc._dict['expectedIncarnation'] = dict(
                        major=expected_incarnation[0],
                        minor=expected_incarnation[1])
                    self._start_process_iter(proc, nuodb_cmd=nuodb_cmd)
                except Exception as e:
                    self._raise_on_failed_process(db_name,
                                                  expected_incarnation[0],
                                                  str(e))

    def _start_process_iter(self, proc, nuodb_cmd=None):
        """
        :param nuodb_mgmt.StartProcessRequest proc: specification of process
        :param str nuodb_cmd: if starting externally, the command to invoke the
                              NuoDB executable

        :returns bool: whether there is a TE running
        """

        self._print('STARTING: {}', proc)
        self._start_process(
            proc.db_name, proc.server_id,
            proc.engine_type,
            archive_id=proc.archive_id,
            incarnation_major=proc.expected_incarnation_major,
            incarnation_minor=proc.expected_incarnation_minor,
            nuodb_cmd=nuodb_cmd,
            is_cmd=False,
            labels=proc.labels,
            **proc.options)

    @Subcommand('shutdown', 'database',
                help='shutdown all database processes for a database')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database to shutdown')
    def shutdown_database(self, db_name):
        self.conn.shutdown_database(db_name)

    @Subcommand('connect', 'database',
                help='establish a SQL connection with a database')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database to connect to')
    @MutuallyExclusive(
        Argument('--server-id',
                 completer=CommandProcessor.get_server_ids,
                 help='the ID of the server to use to obtain SQL connection'),
        Argument('--this-server', action='store_true',
                 help='whether to obtain SQL connection through API server'),
        required=True)
    @Argument('--dba-user', required=True, default=EnvironmentalDefault(),
              help='the database administrator user')
    @Argument('--dba-password', required=True, default=EnvironmentalDefault(),
              help='the database administrator password')
    @Argument('--nuosql-cmd', required=True,
              default=EnvironmentalDefault(from_nuodb_home('bin', 'nuosql')),
              help='the command to invoke the NuoSQL executable')
    @Argument('--connection-properties', required=False, nargs='*',
              default=EnvironmentalDefault(),
              help='connection properties for connection request')
    def connect_database(self, db_name, server_id, dba_user, dba_password,
                         nuosql_cmd, this_server=False,
                         connection_properties=None):
        server_id, config = self._get_server_id(server_id, this_server)
        if config is None:
            config = self.conn.get_admin_config(server_id)
        port = config.get_nested('properties', 'agentPort')
        server = self.conn.get_server(server_id)
        address = server.address.split(':')[0]
        args = ['{}@{}:{}'.format(db_name, address, port),
                '--user', dba_user,
                '--password', dba_password]
        # add connection properties
        if not isinstance(connection_properties, collections.Mapping):
            connection_properties = CommandProcessor.dict_from_tokens(
                connection_properties)
        for k, v in connection_properties.items():
            args.append('--connection-property')
            args.append('{}={}'.format(k, v))
        # invoke nuosql and exit with its exit value
        ret = subprocess.call(nuosql_cmd.split() + args)
        sys.exit(ret)

    def _get_server_id_from_host_entry(self, servers, address, stable_id=None,
                                       server_mapping=None):
        if stable_id is not None and server_mapping:
            # server mapping was defined and stable ID is in capture file
            server_id = server_mapping.get(stable_id)
            if server_id is None:
                raise RuntimeError(
                    'No entry in --server-mapping for stable ID ' + stable_id)
            return server_id
        # server mapping not defined or stable ID is not in capture file; find
        # server with matching address
        server_ids = [server.id for server in servers
                      if server.address.split(':')[0] == address]
        if len(server_ids) == 0:
            raise RuntimeError('No servers found with address ' + address)
        if len(server_ids) != 1:
            raise RuntimeError('Multiple servers found with address {}: {}'
                               .format(address, ', '.join(server_ids)))
        return server_ids[0]

    def _check_one_to_one(self, server_map):
        inverse_multimap = {}
        for host_num, server_id in server_map.items():
            inverse_multimap[server_id] = inverse_multimap.get(server_id, [])
            inverse_multimap[server_id].append(host_num)
        errors = []
        for server_id, host_nums in sorted(inverse_multimap.items()):
            if len(host_nums) != 1:
                errors.append('Multiple hosts mapped to {}: {}\n'
                              .format(server_id, ', '.join(sorted(host_nums))))
        if len(errors) != 0:
            raise RuntimeError(
                'Unable to map hosts in capture file to nuoadmin servers:' +
                ''.join('\n  ' + error for error in errors))

    def _with_prefix(self, name):
        return name if name.startswith('--') else ('--' + name)

    def _without_prefix(self, name):
        return name[2:] if name.startswith('--') else name

    def _get_options(self, proc_spec,
                     ignored_options=('jvm-lib', 'nuodb-home-dir')):
        """
        Get options from a process entry in a nuoagent capture file. Each
        option entry has the form `<Option Name="...">...</Option>`, where the
        inner text is the value, unless the option is a switch, in which case
        there is no inner text.

        :param xml.etree.ElementTree proc_spec:
        """

        options = {}
        for option_entry in proc_spec.findall('Option'):
            name = self._without_prefix(option_entry.attrib['Name'])
            if name in ignored_options:
                continue
            value = option_entry.text
            if not value:
                value = 'true'
            options[name] = value
        return options

    def _is_legal_db_option(self, name, option_types):
        return option_types.get(
            self._with_prefix(name)) in ['SIMPLE', 'DATABASE_ONLY']

    def _normalize_options(self, proc_options_list, option_types):
        """
        Return the dictionary containing all common options among
        `proc_options_list` that can be specified as database options and
        normalize all options in `proc_options_list` so that they are disjoint
        with the database options. Also remove any restricted options or
        database options that are specified inconsistently.

        :param list[dict[str, str]] proc_options_list:
        """

        if len(proc_options_list) == 0:
            return {}
        # copy all database-legal options from some arbitrary process
        db_options = dict(
            (name, value) for name, value in proc_options_list[0].items()
            if self._is_legal_db_option(name, option_types))
        # eliminate any options we encounter that are not specified identically
        # for all other processes
        for name, value in list(db_options.items()):
            for proc_options in proc_options_list[1:]:
                if name in db_options and proc_options.get(name) != value:
                    del db_options[name]
        # normalize process options by removing any options we've factored out
        # into `db_options` and removing any illegal options; also emit warning
        # messages about any illegal options
        restricted_options = set()
        illegal_db_options = set()
        for proc_options in proc_options_list:
            # remove all database options
            for name in db_options.keys():
                if name in proc_options:
                    del proc_options[name]
            # remove any illegal options; which are options that are either
            # RESTRICTED or DATABASE_ONLY; any DATABASE_ONLY option should have
            # been specified identically for all processes and should be in
            # `db_options`
            for name, type in option_types.items():
                name = self._without_prefix(name)
                if name in proc_options and type in ['DATABASE_ONLY', 'RESTRICTED']:  # noqa
                    del proc_options[name]
                    if type == 'DATABASE_ONLY':
                        illegal_db_options.add(name)
                    else:
                        restricted_options.add(name)
        if len(restricted_options) != 0:
            self._print(
                'WARNING: Restricted options appearing in capture file: {}',
                ', '.join(restricted_options))
        if len(illegal_db_options) != 0:
            self._print(
                'WARNING: Database options specified inconsistently in capture file: {}',  # noqa
                ', '.join(illegal_db_options))
        return db_options

    @Subcommand('prepare', 'database',
                help='display commands to create a nuoadmin database from a nuoagent capture file')  # noqa
    @Argument('--capture-file', required=True,
              help='capture file describing a nuoagent database')
    @Argument('--server-mapping', nargs='*',
              completer=CommandProcessor.get_server_mapping_token,
              help='mapping of stable ID in nuoagent to corresponding server ID in nuoadmin')  # noqa
    def prepare_database(self, capture_file, server_mapping=None):
        if not isinstance(server_mapping, collections.Mapping):
            server_mapping = CommandProcessor.dict_from_tokens(server_mapping)
        db_spec = ElementTree.parse(capture_file)
        db_name = db_spec.getroot().attrib['Name']
        # host entries have the format `<Host Id="..." Address="..."
        # StableId="..." />`, where `Id` is referenced in `HostId` attribute of
        # process entries
        host_specs = []
        for host_spec in db_spec.findall('./Hosts/Host'):
            host_specs.append((host_spec.attrib['Id'],
                               host_spec.attrib['Address'],
                               host_spec.attrib.get('StableId')))
        # using either explicit mapping of stable ID to server ID or by using
        # addresses, map every host entry to an admin server
        servers = self.conn.get_servers()
        server_map = dict(
            (host_num, self._get_server_id_from_host_entry(
                servers, address, stable_id, server_mapping))
            for host_num, address, stable_id in host_specs)
        self._check_one_to_one(server_map)
        # process all archives/SMs in capture file; for each archive/SM, we
        # need to generate a create-archive command with the associated server
        # ID and path; SM entries have the form `<StorageManager
        # ArchivePath="..." HostId="..."/>`
        archive_specs = []
        sm_options = []
        for sm_spec in db_spec.findall('./StorageManagers/StorageManager'):
            server_id = server_map[sm_spec.attrib['HostId']]
            archive_path = sm_spec.attrib['ArchivePath']
            options = self._get_options(sm_spec)
            # get journal directory from options; default journal directory is
            # `<archive>/journal`; only set the journal path if it is set to a
            # non-default location
            journal_path = options.pop('journal-dir', None)
            if journal_path == os.path.join(archive_path, 'journal'):
                journal_path = None
            archive_specs.append((server_id, archive_path, journal_path))
            sm_options.append(options)
        # process all TEs in capture file
        te_server_ids = []
        te_options = []
        for te_spec in db_spec.findall('./TransactionEngines/TransactionEngine'):  # noqa
            host_num = te_spec.attrib['HostId']
            te_server_ids.append(server_map[host_num])
            te_options.append(self._get_options(te_spec))
        # normalize the process options; factor out all common options as
        # database-level options (specified on create-database)
        option_types = self.conn._get_data(
            'processes', 'availableOptions')['options']
        db_options = self._normalize_options(sm_options + te_options,
                                             option_types)
        # prepare commands to create archives and database in nuoadmin
        commands = []
        commands.append('  export NUOCMD_DBA_USER=theDbaUser          # ATTENTION: replace with your actual DBA username')  # noqa
        commands.append('  export NUOCMD_DBA_PASSWORD=theDbaPassword  # ATTENTION: replace with your actual DBA password')  # noqa
        for server_id, archive_path, journal_path in archive_specs:
            if journal_path is None:
                commands.append(
                    '  nuocmd create archive --db-name {} --server-id {} --archive-path {} --restored'  # noqa
                    .format(db_name, server_id, archive_path))
            else:
                commands.append(
                    '  nuocmd create archive --db-name {} --server-id {} --archive-path {} --journal-path {} --restored'  # noqa
                    .format(db_name, server_id, archive_path, journal_path))
        options_str = ''
        for name, value in sorted(db_options.items()):
            options_str += ' \\\n      {} {}'.format(name, value)
        commands.append(
            '  nuocmd create database --db-name {} --te-server-ids {} --default-options{}'  # noqa
            .format(db_name, ' '.join(te_server_ids), options_str))
        # output commands
        self._print('To start database using nuoadmin, execute the following commands:')  # noqa
        for command in commands:
            self._print(command)
        return commands

    def _get_server_id(self, server_id, this_server):
        """
        Check that `server_id` and `this_server` are not both specified, and if
        necessary get the server ID of the API server. Returns a tuple of the
        server ID and the API server configuration, if the API server
        configuration was obtained.

        :param str server_id:
        :param bool this_server:

        :returns tuple(str, nuodb_mgmt.AdminServerConfig):
        """

        if server_id is not None and this_server:
            raise ValueError('Server ID specified with this_server flag')
        elif server_id is None and not this_server:
            raise ValueError('Server ID not specified without this_server flag')  # noqa

        if server_id is not None:
            return server_id, None

        config = self.conn.get_admin_config()
        server_id = config.get_nested('properties', 'ThisServerId')
        return server_id, config

    # default formatting for 'show' subcommands
    SERVER_FMT = '[{id}] {address} [last_ack = {last_ack:.2f:NEVER}] [member = {peer_state}] [raft_state = {raft_state}] ({role}, Leader={leader}, log={log_term::?}/{commit_index::?}/{log_index::?}) {connected_state}'  # noqa
    DATABASE_FMT = '{name} [state = {state}]'
    COMMON_PROCESS_FMT = '[{engine_type}] {address::<UNKNOWN ADDRESS>} [start_id = {start_id}] [server_id = {server_id}] [pid = {pid::}] [node_id = {node_id::}]'  # noqa
    PROCESS_FMT = COMMON_PROCESS_FMT + ' [last_ack = {last_ack:5.2f:>60}] {durable_state}:{engine_state}'  # noqa
    # add 'process.' to every field in `COMMON_PROCESS_FMT`
    EXITED_PROCESS_FMT = re.sub(r'\{([^}]*)\}', r'{process.\1}', COMMON_PROCESS_FMT) + ' EXITED({process.durable_state}:{process.engine_state}):{reason} ({exit_code::?})'  # noqa
    COMMON_ARCHIVE_FMT = '[{id}] {server_id} : {archive_path} @ {db_name} [journal_path = {journal_path::}] [snapshot_archive_path = {snapshot_archive_path::}]'  # noqa
    ARCHIVE_FMT = COMMON_ARCHIVE_FMT + ' {state}'
    REMOVED_ARCHIVE_FMT = COMMON_ARCHIVE_FMT + ' REMOVED({state})'
    REGION_FMT = '[region = {name}]'
    SHORT_PROCESS_FMT = '[{engine_type}] {address} [start_id = {start_id}] [pid = {pid::}] [node_id = {node_id::}] {durable_state}:{engine_state}'  # noqa

    @Subcommand('get', 'archives', help='show database archives')
    @Argument('--db-name', required=False, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names_from_archives,
              help='the name of the database to list archives for')
    @Argument('--removed', action='store_true', help='show removed archives')
    def get_archives(self, db_name=None, removed=False):
        archives = self.conn.get_archives(db_name=db_name, removed=removed)
        for archive in archives:
            self._show(archive)
        return archives

    @Subcommand('show', 'archives', help='show database archives')
    @Argument('--db-name', required=False, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names_from_archives,
              help='the name of the database to list archives for')
    @Argument('--removed', action='store_true', help='show removed archives')
    @Argument('--archive-format', default=EnvironmentalDefault(ARCHIVE_FMT),
              help='format string for archives')
    @Argument('--removed-archive-format',
              default=EnvironmentalDefault(REMOVED_ARCHIVE_FMT),
              help='format string for removed archives')
    @Argument('--process-format', default=EnvironmentalDefault(PROCESS_FMT),
              help='format string for processes')
    @Argument('--exited-process-format',
              default=EnvironmentalDefault(EXITED_PROCESS_FMT),
              help='format string for exited processes')
    def show_archives(self, db_name=None, removed=False,
                      archive_format=ARCHIVE_FMT,
                      removed_archive_format=REMOVED_ARCHIVE_FMT,
                      process_format=PROCESS_FMT,
                      exited_process_format=EXITED_PROCESS_FMT):
        archives = self.conn.get_archives(db_name=db_name, removed=removed)
        running_processes = self.conn.get_processes(db_name=db_name, type='SM')
        exited_processes = self.conn.get_exited_processes(
            db_name=db_name, **{'process.type': 'SM'})
        for archive in archives:
            self._print(get_formatted(removed_archive_format
                                      if removed else archive_format, archive))
            # if there is a running process on this archive, display it
            running = [p for p in running_processes
                       if p.archive_id == archive.id]
            if len(running) != 0:
                self._print('  ' + get_formatted(process_format,
                                                 running[0]))
            else:
                # if there are exited processes on this archive, display the
                # last one
                exited = [tombstone for tombstone in exited_processes
                          if tombstone.process.archive_id == archive.id]
                exited.sort(key=lambda e: e.db_incarnation)
                if len(exited) != 0:
                    self._print('  ' + get_formatted(exited_process_format,
                                                     exited[-1]))

    CORE_FILE_OUTPUT_FMT = 'core.nuodb.{db_name}.{hostname::}.{start_id}.gz'

    @Subcommand('get', 'core-file',
                help='download the core file for a running database process')
    @Argument('--start-id', required=True,
              help='the start ID of the process to get core file for')
    @Argument('--output', default=EnvironmentalDefault(CORE_FILE_OUTPUT_FMT),
              help='the output file or format for output file')
    @Argument('--output-dir', required=False,
              help='the directory to store core file in; the actual file path will be resolved relative to this directory')  # noqa
    @Argument('--socket-read-timeout', default=None, type=float,
              help="The maximum time (in seconds) that we will block waiting for data from an engine")
    def get_core_file(self, start_id, output=CORE_FILE_OUTPUT_FMT,
                      output_dir=None, socket_read_timeout=None):
        process = self.conn.get_process(start_id)
        stream = self.conn.stream_core_file(start_id, read_timeout=socket_read_timeout)
        filename = get_formatted(output, process)
        if output_dir is not None:
            filename = os.path.join(output_dir, filename)
        self._download_stream(stream, filename)

    def _download_stream(self, stream, filename):
        with open(filename, 'wb') as f:
            for msg in stream:
                f.write(msg)

    def _supports_query_request(self, process):
        """
        Predicate to determine if a process can service query requests, which
        are requests of the form `<Request Service="Query"/>`. The message
        dispatching was changed with 4.0 to support servicing of these
        requests.
        """

        version = process.get('version')
        if version is None:
            return False
        match = re.match('([0-9]+).*', version)
        if not match:
            return False
        return int(match.group(1)) >= 4

    def _send_query_request(self, db_name, request_type, child_msg=None):
        """
        Send a query request to some database process.
        """

        processes = self.conn.get_processes(db_name)
        request_processes = filter(self._supports_query_request, processes)
        if len(request_processes) == 0:
            raise RuntimeError(
                'Database {} has no processes able to service request'
                .format(db_name))

        for process in request_processes:
            try:
                return processes, self.conn.send_query_request(
                    process.start_id, request_type, child_msg)
            except Exception as e:
                self._print(
                    'WARNING: Unable to send request to start ID {}: {}',
                    process.start_id, e)

        raise RuntimeError('Unable to send request to any process')

    @Subcommand('upgrade', 'database-version',
                help='upgrade the database version')
    @Argument('--db-name', required=True,
              completer=CommandProcessor.get_db_names,
              help='the database upgrade')
    @MutuallyExclusive(
        Argument('--version', help='the version to upgrade to'),
        Argument('--max-version', action='store_true',
                 help='upgrade to maximum available version'),
        required=True)
    def upgrade_database_version(self, db_name, version=None,
                                 max_version=False):
        if max_version:
            version = 'MAX_VERSION'
        _, response = self._send_query_request(
            db_name, 'Upgrade', '<Args version="{}"/>'.format(version))
        succeeded = response.attrib.get('succeeded')
        if succeeded != '1':
            raise RuntimeError('Unable to upgrade database: ' +
                               str(response.attrib.get('message')))

    @Subcommand('show', 'database-versions',
                help='show the database version for all processes in the database')  # noqa
    @Argument('--db-name', required=True,
              completer=CommandProcessor.get_db_names,
              help='the database to show database versions for')
    @Argument('--process-format', default=EnvironmentalDefault(PROCESS_FMT),
              help='format string for processes')
    def show_database_versions(self, db_name, process_format=PROCESS_FMT):
        processes, response = self._send_query_request(db_name, 'DbVersion')
        available_versions = []
        for version in response.findall('Versions/Version'):
            available_versions.append(
                (version.attrib['id'], version.attrib['name']))

        versions = {}
        process_versions = {}
        for process_version in response.findall('Nodes/Node'):
            node_id = process_version.attrib['id']
            version_id = process_version.attrib['versionId']
            version = process_version.attrib['version']
            release = process_version.attrib['release']
            versions[version_id] = (version, release)
            if version_id not in process_versions:
                process_versions[version_id] = []
            for process in processes:
                if process.node_id == int(node_id):
                    process_versions[version_id].append(process)

        effective_version_id = response.attrib['EffectiveVersion']
        effective_version = response.attrib['Version']
        max_version_id = response.attrib['MaxVersion']
        self._print(
            'effective version ID: {}, effective version: {}, max version ID: {}',  # noqa
            effective_version_id, effective_version, max_version_id)

        self._print('Available versions:')
        for version_id, version in available_versions:
            self._print('  version ID: {}, version: {}', version_id, version)

        self._print('Process versions:')
        for version_id, (version, release) in sorted(versions.items()):
            self._print('  version ID: {}, version: {}, release: {}',
                        version_id, version, release)
            for process in sorted(process_versions[version_id],
                                  key=lambda p: p.start_id):
                self._print('    ' + get_formatted(process_format, process))

    @Subcommand('get', 'database-connectivity',
                help='get the connectivity graph for a database')
    @Argument('--db-name', required=True,
              completer=CommandProcessor.get_db_names,
              help='the database to get connectivity information for')
    @Argument('--with-node-ids', action='store_true',
              help='whether to return connectivity graph with node IDs as keys instead of start IDs')  # noqa
    @Argument('--suppress-errors', action='store_true',
              help='whether to suppress errors messages when collecting connectivity information')  # noqa
    def get_database_connectivity(self, db_name, with_node_ids=False,
                                  suppress_errors=False):
        db_connectivity, errors = self.conn.get_database_connectivity(
            db_name, with_node_ids=with_node_ids)
        self._show(db_connectivity)
        if not suppress_errors and len(errors) != 0:
            self._show(errors)

    @Subcommand('show', 'database-connectivity',
                help='show the connectivity graph for a database')
    @Argument('--db-name', required=True,
              completer=CommandProcessor.get_db_names,
              help='the database to show connectivity graph for')
    @Argument('--with-node-ids', action='store_true',
              help='whether to show connectivity graph with node IDs as keys instead of start IDs')  # noqa
    @Argument('--last-ack-threshold', default='5', type=int,
              help='the threshold in seconds to display time since last ack')
    def show_database_connectivity(self, db_name, with_node_ids=False,
                                   last_ack_threshold=5):
        db_connectivity, errors = self.conn.get_database_connectivity(
            db_name, with_node_ids=with_node_ids)
        # define constants to signal error conditions
        unreachable_by_engine = 'X'
        unreachable_by_admin = '?'
        unexpected_message_format = '!'
        keys = sorted(db_connectivity.keys() + errors.keys())
        normalized = {}
        for i, j in ((i, j) for i in keys for j in keys):
            if i not in db_connectivity:
                # no row for this process means the admin was not able to query
                # it for connectivity information
                normalized[(i, j)] = unreachable_by_admin
            elif i == j:
                # node does not connect to itself; leave cell blank
                normalized[(i, j)] = ''
            elif j not in db_connectivity[i]:
                # no column for this node in this row means node i does not
                # have node j in its node list
                normalized[(i, j)] = unreachable_by_engine
            elif 'lastAckDeltaInMilliSeconds' not in db_connectivity[i][j]:
                # node j is in node i's node list, but we do not have last ack
                # information for some reason
                normalized[(i, j)] = unexpected_message_format
            else:
                # add last ack to table if it is larger than threshold
                time_ms = db_connectivity[i][j]['lastAckDeltaInMilliSeconds']
                if time_ms / 1000.0 >= last_ack_threshold:
                    normalized[(i, j)] = AdminCommands._get_best_time_unit(time_ms)  # noqa
                else:
                    normalized[(i, j)] = ''
        # get cell width and output header
        max_len = max(map(len, map(str, keys) + normalized.values()))
        cell_width = max_len + 2
        self.out.write(cell_width * ' ')
        for key in keys:
            self.out.write(str(key).center(cell_width))
        self.out.write('\n')
        # output each row of connectivity table
        for i in keys:
            self.out.write(str(i).center(cell_width))
            for j in keys:
                self.out.write(normalized[(i, j)].center(cell_width))
            self.out.write('\n')
        # output legend describing what each symbol means
        self.out.writelines([
            '\n',
            'Legend:\n',
            '  {}: node at this row does not consider node at this column a peer\n'.format(unreachable_by_engine),  # noqa
            '  {}: node at this row could not be queried for connectivity information\n'.format(unreachable_by_admin),  # noqa
            '  {}: node at this row does not have expected metadata for node at this column\n'.format(unexpected_message_format),  # noqa
            '  [0-9]+[hms]: time since node at this row last heard from node at this column\n'])  # noqa

    @staticmethod
    def _get_best_time_unit(time_ms):
        millisecond = 1
        second = 1000 * millisecond
        minute = 60 * second
        hour = 60 * minute
        day = 24 * hour
        units = [('d', day),
                 ('h', hour),
                 ('m', minute),
                 ('s', second),
                 ('ms', millisecond)]
        for suffix, unit in units:
            if time_ms >= unit:
                break
        return str(time_ms / unit) + suffix

    LOG_FMT = '{msg[Time]}: ' + SHORT_PROCESS_FMT + ' =>[{msg[Options]}] {msg[LogMessage]}'  # noqa

    @Subcommand('show', 'log-messages',
                help='show log messages from running database processes')
    @Argument('--log-options', required=True, nargs='+',
              default=EnvironmentalDefault(),
              help='the log levels and categories to enable')
    @MutuallyExclusive(
        Argument('--db-name', help='the database to log messages for'),
        Argument('--start-id', help='the running process to log messages for'),
        required=False)
    @Argument('--log-format', default=EnvironmentalDefault(LOG_FMT),
              help='format string for process log messages')
    def show_log_messages(self, log_options, db_name=None, start_id=None,
                          log_format=LOG_FMT):
        for process_msg in self._get_messages(log_options, db_name, start_id,
                                              include_process=True):
            # remove trailing newline from log message
            process_msg['msg']['LogMessage'] = process_msg['msg'].get(
                'LogMessage', '').rstrip()
            self._print(get_formatted(log_format, process_msg))

    @Subcommand('get', 'log-messages',
                help='get log messages from running database processes')
    @Argument('--log-options', required=True, nargs='+',
              default=EnvironmentalDefault(),
              help='the log levels and categories to enable')
    @MutuallyExclusive(
        Argument('--db-name', help='the database to log messages for'),
        Argument('--start-id', help='the running process to log messages for'),
        required=False)
    def get_log_messages(self, log_options, db_name=None, start_id=None):
        for process_msg in self._get_messages(log_options, db_name, start_id):
            self._show(process_msg)

    @Subcommand('get', 'stats',
                help='get stats from running database processes')
    @MutuallyExclusive(
        Argument('--db-name', help='the database to get stats for'),
        Argument('--start-id', help='the running process to get stats for'),
        required=False)
    def get_stats(self, db_name=None, start_id=None):
        for process_msg in self._get_messages(None, db_name, start_id):
            self._show(process_msg)

    def _get_messages(self, log_options, db_name, start_id,
                      include_process=False):
        # message generator is for a single process if `start_id` is specified;
        # otherwise, it is aggregated
        if start_id is not None:
            msg_stream = self.conn.monitor_process(start_id, log_options)
        else:
            msg_stream = self.conn.monitor_database(
                db_name, log_options, keep_open=True, err=self.err)
        # filter messages by name based on whether we are streaming stats or
        # log messages
        message_name = 'Status' if log_options is None else 'LogMessage'
        for process, message in msg_stream:
            json_msg = nuodb_mgmt.xml_to_json(message, message_name)
            if len(json_msg) != 0:
                # add timestamp to message attributes; TODO: in the future, we
                # may want to include timestamp on the sending side
                if 'Time' not in json_msg:
                    json_msg['Time'] = self._get_timestamp()
                # combine process and message; if `include_process`, return all
                # process attributes; otherwise just return start ID
                if include_process:
                    process._dict['msg'] = json_msg
                    yield process
                else:
                    yield dict(startId=process.start_id, msg=json_msg)

    @Subcommand('create', 'archive', help='create a database archive')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database for the archive')
    @MutuallyExclusive(
        Argument('--server-id', default=None,
                 completer=CommandProcessor.get_server_ids,
                 help='the ID of the server for the archive'),
        Argument('--is-external', action='store_true',
                 help='whether this archive will be externally started'),
        required=True)
    @Argument('--archive-path', required=True,
              help='the path of the archive directory')
    @Argument('--journal-path', required=False,
              help='the path of the journal directory')
    @Argument('--snapshot-archive-path', required=False,
              help='the path of the snapshot archive directory')
    @Argument('--restored', action='store_true',
              help='whether the archive being restored from existing data')
    @Argument('--archive-id', required=False,
              help='if specified, the archive ID of the removed archive')
    def create_archive(self, db_name, server_id, archive_path,
                       journal_path=None, snapshot_archive_path=None,
                       restored=False, archive_id=None, is_external=False):
        # this is a sanity check; argparse should prevent this from happening
        if is_external and server_id is not None:
            raise ValueError('Server ID specified with is_external flag')
        elif not is_external and server_id is None:
            raise ValueError('Server ID unspecified without is_external flag')

        archive = self.conn.create_archive(
            db_name, server_id, archive_path, journal_path,
            snapshot_archive_path, restored, archive_id)
        self._show(archive)
        return archive

    @Subcommand('delete', 'archive',
                help='delete a non-running database archive')
    @Argument('--archive-id', required=True,
              completer=CommandProcessor.get_non_running_archive_ids,
              help='the ID of the archive to delete')
    @Argument('--purge', action='store_true',
              help='whether to remove the archive permanently')
    def delete_archive(self, archive_id, purge=False):
        self.conn.delete_archive(archive_id, purge)

    @Subcommand('get', 'storage-groups',
                help='get storage groups for a database')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database to list storage groups for')
    def get_storage_groups(self, db_name):
        storage_groups = self.conn.get_storage_groups(db_name)
        for sg in storage_groups:
            self._show(sg)
        return storage_groups

    # TODO: add completion for storage groups

    @Subcommand('add', 'storage-group',
                help='add a storage group to a set of archives')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database')
    @Argument('--sg-name', required=True,
              help='the name of the storage group to add')
    @Argument('--archive-ids', nargs='+', required=True,
              completer=CommandProcessor.get_archive_ids,
              help='the IDs of the archives to add storage group to')
    def add_storage_group(self, db_name, sg_name, archive_ids):
        for archive_id in archive_ids:
            self.conn.add_storage_group(db_name, sg_name, archive_id)

    @Subcommand('remove', 'storage-group',
                help='remove a storage group from a set of archives')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database')
    @Argument('--sg-name', required=True,
              help='the name of the storage group to remove')
    @Argument('--archive-ids', nargs='+', required=True,
              completer=CommandProcessor.get_archive_ids,
              help='the IDs of the archives to remove storage group from')
    def remove_storage_group(self, db_name, sg_name, archive_ids):
        for archive_id in archive_ids:
            self.conn.remove_storage_group(db_name, sg_name, archive_id)

    @Subcommand('get', 'servers', help='get admin servers')
    def get_servers(self):
        servers = self.conn.get_servers()
        for server in servers:
            self._show(server)
        return servers

    @Subcommand('delete', 'server',
                help='remove a server from the raft membership remove all process and archive state for a server')  # noqa
    @Argument('--server-id', required=True,
              completer=CommandProcessor.get_server_ids,
              help='the ID of the server to remove from the membership')
    def delete_server(self, server_id):
        self.conn.delete_server(server_id)

    @Subcommand('delete', 'server-state',
                help='remove all process and archive state for a server')
    @Argument('--server-id', required=True,
              completer=CommandProcessor.get_server_ids,
              help='the ID of the server to remove from domain state')
    def delete_server_state(self, server_id):
        self.conn.delete_server_state(server_id)

    @Subcommand('shutdown', 'server', help='shutdown a server')
    @MutuallyExclusive(
        Argument('--server-id',
                 completer=CommandProcessor.get_server_ids,
                 help='the ID of the server to shut down'),
        Argument('--this-server', action='store_true',
                 help='shutdown the server hosting this API server'),
        required=True)
    @Argument('--evict-local', action='store_true', required=False,
              help='evict processes local to the server being shutdown')
    def shutdown_server(self, server_id, this_server=False, evict_local=False):
        server_id, config = self._get_server_id(server_id, this_server)
        self.conn.shutdown_server(server_id, evict_local=evict_local)

    @staticmethod
    def _get_timestamp(time_sec=None, precision='ms'):
        """
        :param int time_sec: the time to generate timestamp for; if not
                             specified, use the current time
        :param str precision: one of 's', 'ms', 'us'

        :returns str:
        """

        if time_sec is None:
            time_sec = time.time()
        dt = datetime.datetime.fromtimestamp(time_sec)
        ret = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')
        if precision == 'us':
            # timestamp is already in microseconds precision
            return ret
        ts_sec, frac = ret.rsplit('.', 1)
        if precision == 's':
            # return timestamp not including fractions of a second
            return ts_sec
        else:
            # include three decimal places for millisecond precision
            return '.'.join([ts_sec, frac[:3]])

    @Subcommand('show', 'domain', help='show summary of domain state')
    @Argument('--server-format', default=EnvironmentalDefault(SERVER_FMT),
              help='format string for servers')
    @Argument('--db-format', default=EnvironmentalDefault(DATABASE_FMT),
              help='format string for databases')
    @Argument('--process-format', default=EnvironmentalDefault(PROCESS_FMT),
              help='format string for processes')
    @Argument('--client-token', required=False,
              help='message to display in admin log')
    def show_domain(self, server_format=SERVER_FMT,
                    db_format=DATABASE_FMT,
                    process_format=PROCESS_FMT, client_token=None):
        # print the support version info
        if client_token is None:
            client_token = hashlib.sha1(str(time.time())).hexdigest()
        info = self.conn.log_message(client_token)
        timestamp = self._get_timestamp(info['serverTimeMillis'] / 1000.0)
        self._print('server version: {}, server license: {}',
                    info['serverVersion'], info.get('licenseType', 'None'))
        self._print('server time: {}, client token: {}',
                    timestamp, client_token)
        # print real summary
        self._print('Servers:')
        for server in self.conn.get_servers():
            fmt = server_format
            if server.is_local:
                fmt += ' *'
            self._print('  ' + get_formatted(fmt, server))

        self._print('Databases:')
        for database in self.conn.get_databases():
            self._print('  ' + get_formatted(db_format, database))
            self._print_database_processes(database, process_format)

    @Subcommand('show', 'database', help='show database state')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the database name')
    @MutuallyExclusive(
        Argument('--num-incarnations', type=int, default=1,
                 help='the number of incarnations to show starting from current'),  # noqa
        Argument('--all-incarnations', action='store_true',
                 help='show all incarnations'),
        Argument('--skip-exited', action='store_true',
                 help='skip exited processes'),
        required=False)
    @Argument('--db-format', default=EnvironmentalDefault(DATABASE_FMT),
              help='format string for databases')
    @Argument('--process-format', default=EnvironmentalDefault(PROCESS_FMT),
              help='format string for processes')
    @Argument('--exited-process-format',
              default=EnvironmentalDefault(EXITED_PROCESS_FMT),
              help='format string for exited processes')
    def show_database(self, db_name, num_incarnations=1,
                      all_incarnations=False, skip_exited=False,
                      db_format=DATABASE_FMT, process_format=PROCESS_FMT,
                      exited_process_format=EXITED_PROCESS_FMT):
        database = self.conn.get_database(db_name)
        self._show(database)
        self._print('  ' + get_formatted(db_format, database))
        self._print_database_processes(database, process_format)
        if skip_exited is False:
            low_incarnation = (
                max(database.incarnation[0] - num_incarnations + 1, 1)
                if not all_incarnations else 1)
            self._print_exited_database_processes(
                db_name, low_incarnation, database.incarnation[0],
                exited_process_format)

    def _raise_on_failed_process(self, db_name, low_incarnation, msg):
        # replace output stream with string stream so that we can capture
        # output and raise an exception with it as in the message
        out = self.out
        self.out = StringIO.StringIO()
        try:
            # show database incarnations starting from low_incarnation
            database = self.conn.get_database(db_name)
            self._show(database)
            self._print('  ' + get_formatted(AdminCommands.DATABASE_FMT,
                                             database))
            self._print_database_processes(database, AdminCommands.PROCESS_FMT)
            self._print_exited_database_processes(
                db_name, low_incarnation, database.incarnation[0],
                AdminCommands.EXITED_PROCESS_FMT)
            raise RuntimeError('{}\n\n{}'.format(msg, self.out.getvalue()))
        finally:
            self.out.close()
            self.out = out

    @Subcommand('get', 'server-config',
                help='get the NuoAdmin service server configuration')
    @MutuallyExclusive(
        Argument('--server-id',
                 completer=CommandProcessor.get_server_ids,
                 help='the ID of the NuoAdmin server'),
        Argument('--this-server', action='store_true',
                 help='get the configuration of the API server'),
        required=True)
    @Argument('--property-key', required=False,
              help='get only a specific property')
    def get_server_config(self, server_id, property_key=None,
                          this_server=False):
        server_id, config = self._get_server_id(server_id, this_server)
        if config is None:
            config = self.conn.get_admin_config(server_id)

        if property_key is None and self.show_json:
            self._show(config._dict)
            return config

        prefix = '   '
        prefix2 = 2 * prefix
        sep = ' = '
        if property_key is not None:
            if property_key in config.properties.keys():
                v = config.properties[property_key]
                self._print('{}{}{}', property_key, sep, v)
            else:
                self._print('Property key [{}] does not exist',
                            property_key)
            return

        self._print('properties:')
        self._print_map(config.properties, prefix, sep)

        self._print('\ninitialMembership:')
        d = config.initial_membership
        for key in d:
            self._print(prefix + key)
            self._print_map(d[key], prefix2, sep)

        self._print('\notherServices:')
        for key in config.other_services:
            self._print(prefix + key)

        self._print('\nstatsPlugins:')
        d = config.stats_plugins
        for key in d:
            self._print(prefix + key)
            for d2 in d[key]:
                self._print_map(d2, prefix2, sep)

        self._print('\nloadBalancers:')
        d = config.load_balancers
        for key in d:
            self._print(prefix + key)
            d2 = d[key]
            self._print_map(d2, prefix2, sep)
        return config

    def _print_map(self, d, prefix, sep='='):
        for key in sorted(d):
            self._print('{}{}{}{}', prefix, key, sep, d[key])

    @Subcommand('get', 'server-logs',
                help='download the server logs for the API server')
    @Argument('--output', required=False,
              help='the output file or directory to save the ZIP file containing server logs to')  # noqa
    @Argument('--dump-threads', action='store_true',
              help='whether to include a thread dump of the admin process in the logs ZIP file')  # noqa
    @Argument('--unpack', action='store_true',
              help='whether to unpack the downloaded ZIP file')
    def get_server_logs(self, output=None, dump_threads=False, unpack=False):
        self._download_logs(self.conn, dump_threads, output=output,
                            logger=self.out, unpack=unpack)

    @Subcommand('add', 'trusted-certificate',
                help='add a trusted certificate to all admin servers and engine processes')  # noqa
    @Argument('--alias', required=True,
              help='the alias of the certificate; this is a name used to refer to the certificate')  # noqa
    @Argument('--cert', required=True,
              help='the certificate to add to truststore as a PEM-encoded file')  # noqa
    @MutuallyExclusive(
        Argument('--timeout', type=int,
                 help='the number of seconds to wait for the certificate to be propagated to all admin servers and engine processes'),  # noqa
        Argument('--no-wait', action='store_true',
                 help='do not wait for certificate to be propagated'),
        required=True)
    def add_trusted_certificate(self, alias, cert, timeout=None,
                                no_wait=False):
        with open(cert) as f:
            if no_wait:
                timeout = 0
            self.conn.add_trusted_certificate(alias, f.read(), timeout)

    @Subcommand('remove', 'trusted-certificate',
                help='remove a trusted certificate from all admin servers and engine processes')  # noqa
    @Argument('--alias', required=True,
              help='the alias of the trusted certificate to remove')
    def remove_trusted_certificate(self, alias):
        self.conn.remove_trusted_certificate(alias)

    @Subcommand('get', 'certificate-info',
                help='get certificate data for the entire domain, including all admin server certificates, all database process certificates, and trusted certificates for all admin servers and database processes')  # noqa
    def get_certificate_info(self):
        cert_info = self.conn.get_certificate_info()
        self._show(cert_info)
        return cert_info

    def _download_logs(self, conn, dump_threads, output=None, logger=None,
                       unpack=False):
        """
        :param nuodb_mgmt.AdminConnection conn: the client object to use
        :param str output: output file or directory
        :param file logger: the file-like object to log messages to
        :param bool unpack: whether to unpack the ZIP file
        """

        downloader = conn.get_admin_logs(dump_threads)
        if output is not None and os.path.isdir(output):
            downloader.set_output_dir(output)
        else:
            downloader.set_output_file(output)
        downloader.download(logger=logger)
        # if --unpack was specified, unpack ZIP file and delete it
        if unpack:
            self._print('Unpacking {} ...', downloader.output_file)
            with zipfile.ZipFile(downloader.output_file) as zf:
                zf.extractall(os.path.dirname(downloader.output_file))
            os.remove(downloader.output_file)

    @Subcommand('get', 'diagnose-info',
                help='download server logs for all reachable admin processes and cores for all reachable engine processes')  # noqa
    @Argument('--output-dir', default=os.getcwd(),
              help='the directory to store diagnose info in')
    @Argument('--no-pack', action='store_true',
              help='if specified, do not pack all diagnose info into a single ZIP file')  # noqa
    @Argument('--include-cores', action='store_true',
              help='whether to include cores from engine processes')
    @Argument('--socket-read-timeout', default=None, type=float,
              help="The maximum time (in seconds) that we will block waiting for data from an engine")  # noqa
    # TODO: re-enable collecting of metadata once DB-23096 is fixed
    # @Argument('--include-metadata', action='store_true',
    #           help='whether to include metadata from engine processes')
    # @Argument('--include-all', action='store_true',
    #           help='whether to include metadata and cores from engine processes; this is shorthand for "--include-metadata --include-cores"')  # noqa
    def get_diagnose_info(self, output_dir=os.getcwd(), no_pack=False,
                          include_metadata=False, include_cores=False,
                          include_all=False, socket_read_timeout=None):
        timestamp = self._get_timestamp(precision='s').replace(':', '-')
        base = os.path.join(output_dir, 'diagnose-' + timestamp)
        admin_dir = os.path.join(base, 'admin')
        engine_dir = os.path.join(base, 'engine')
        os.makedirs(admin_dir)
        os.makedirs(engine_dir)
        threads = []

        # create threads to download all admin logs
        for server in self.conn.get_servers():
            thread = threading.Thread(
                name=server.id,
                target=self._get_admin_diagnose_info,
                args=(server, admin_dir))
            thread.start()
            threads.append(thread)
        # create threads to download all engine cores; only MONITORED engine
        # processes can service management requests
        for process in self.conn.get_processes(order_by='dbName',
                                               durableState='MONITORED'):
            # diagnose info for engine will be stored in directory
            # '<DB name>_<hostname>_<start ID>'
            hostname = process.get('hostname', process.get('address'))
            descriptor = '{}_{}_{}'.format(
                process.db_name,
                hostname,
                process.start_id)
            thread = threading.Thread(
                name=descriptor,
                target=self._get_engine_diagnose_info,
                args=(process, engine_dir, descriptor,
                      include_metadata or include_all,
                      include_cores or include_all, 
                      socket_read_timeout))
            thread.start()
            threads.append(thread)
        # wait for all threads to finish
        self._wait_for_threads(threads)
        # unless --no-pack was specified, pack all files into a single ZIP file
        # and delete directory containing intermediate files
        if not no_pack:
            with zipfile.ZipFile(base + '.zip', 'w', allowZip64=True) as zf:
                self._print('Packing all files into {} ...', base + '.zip')
                for dirname, _, filenames in os.walk(base):
                    for filename in filenames:
                        absfile = os.path.join(dirname, filename)
                        relfile = os.path.relpath(absfile, output_dir)
                        zf.write(absfile, relfile)
            shutil.rmtree(base)
        self._print('Diagnose complete: {}',
                    base if no_pack else base + '.zip')

    @exceptional_fn
    def _get_admin_diagnose_info(self, server, admin_dir):
        directory = os.path.join(admin_dir, server.id)
        os.makedirs(directory)
        # save config and check that server is configured with REST service
        config = self.conn.get_admin_config(server.id)
        with open(os.path.join(directory, 'nuoadmin.conf'), 'w') as f:
            json.dump(config._dict, f, indent=4)
        if 'rest' not in (s.lower() for s in config.other_services):
            raise RuntimeError('{} is not configured with REST service'
                               .format(server.id))
        address = server.address.split(':')[0]
        # assume that all servers are configured with the same protocol and
        # port, and replace hostname from --api-server with server's address
        url_base = re.sub(
            r'(https?://)[^:/]*(.*)', r'\g<1>{}\g<2>'.format(address),
            self.conn.url_base)
        conn = nuodb_mgmt.AdminConnection(
            url_base, self.conn.client_key, self.conn.verify)
        self._print('Downloading logs for {} ...', server.id)
        # logs should be extracted into directory since all files are prefixed
        # with '<server ID>/'
        self._download_logs(conn, True, output=admin_dir, unpack=True)
        # save 'show domain' output
        with open(os.path.join(directory, 'show-domain.txt'), 'w') as f:
            AdminCommands(conn, out=f, err=f).show_domain()
        # save 'show database' output for all databases
        with open(os.path.join(directory, 'show-databases.txt'), 'w') as f:
            for db in conn.get_databases():
                command = ('$ show database {} --all-incarnations'
                           .format(db.name))
                header = format('{}\n{}\n').format('*' * len(command), command)
                f.write(header)
                AdminCommands(conn, out=f, err=f).show_database(
                    db.name, all_incarnations=True)
                f.write('\n')

    @exceptional_fn
    def _get_engine_diagnose_info(self, process, engine_dir, descriptor,
                                  include_metadata, include_cores, socket_read_timeout):
        directory = os.path.join(engine_dir, descriptor)
        os.makedirs(directory)
        # save version
        with open(os.path.join(directory, 'version.txt'), 'w') as f:
            f.write(process.get('version', 'UNKNOWN'))
        if include_metadata:
            # download metadata
            try:
                self._print('Downloading metadata for {} ... ', descriptor)
                with open(os.path.join(directory, 'metadata.xml'), 'w') as f:
                    session = self.conn.get_authorized_session(
                        process.start_id, 'Query')
                    session.send(
                        '<Request Service="Query" Type="Instrumentation"/>')
                    f.write(session.recv())
                    session.close()
            except:
                self._print('Unable to download metadata for {}', descriptor)
                self._print_exc()
        if include_cores:
            # download core file
            try:
                stream = self.conn.stream_core_file(process.start_id, read_timeout=socket_read_timeout)
                self._print('Downloading core file for {} ...', descriptor)
                self._download_stream(stream, os.path.join(directory, 'core.gz'))
            except Exception as e:
                self._print(
                    'Unable to download core file for {}: {}',
                    descriptor,
                    str(e))
                raise
            try:
                stream = self.conn.stream_system_dependencies(process.start_id, read_timeout=socket_read_timeout)
                self._print(
                    'Downloading system dependencies and binary for {} ...',
                    descriptor)
                self._download_stream(
                    stream, os.path.join(directory, 'sysdepends.tgz'))
            except Exception:
                # Don't fail if we can't get system dependencies
                self._print(
                    'Unable to download system dependencies and binary for {}',
                    descriptor)
                self._print_exc()

    def _wait_for_threads(self, threads, timeout=None):
        """
        :param list[threading.Thread] threads:
        """

        start_time = time.time()
        while len(threads) > 0:
            if timeout is not None and timeout < time.time() - start_time:
                raise RuntimeError(
                    'Timed out downloading diagnose info for ' +
                    ', '.join(t.name for t in threads))
            # remove first thread and wait short amount of time for it to
            # complete
            thread = threads.pop(0)
            thread.join(0.1)
            if thread.is_alive():
                # thread is still running; append to thread list
                threads.append(thread)
            elif not hasattr(thread, 'exc'):
                self._print('Downloaded diagnose info for {}', thread.name)
            else:
                # thread exited with an exception; print stacktrace
                self._print('Unable to download diagnose info for {}',
                            thread.name)
                self._print_exc(getattr(thread, 'exc'))

    def _print_exc(self, exc=None):
        if exc is None:
            exc = sys.exc_info()
        for line in traceback.format_exception(*exc):
            self.out.write(line)
        self.out.write('\n')

    @Subcommand('get', 'value',
                help='get the value for a key in the key-value store')
    @Argument('--key', required=True, help='the key to get the value of')
    def get_value(self, key):
        value = self.conn.get_value(key)
        if value is not None:
            self._print(value)
        return value

    @Subcommand('set', 'value',
                help='associate a key with a value in the key-value store')
    @Argument('--key', required=True, help='the key to set a value for')
    @Argument('--value', required=True,
              help='the new value to associate with key')
    @MutuallyExclusive(
        Argument('--expected-value', help='expected current value for key'),
        Argument('--unconditional', action='store_true',
                 help='set value unconditionally'),
        required=False)
    def set_value(self, key, value, expected_value=None, unconditional=False):
        self.conn.set_value(key, value, expected_value, not unconditional)

    @Subcommand('get', 'effective-license',
                help='get the current effective license for the server or domain')  # noqa
    def get_effective_license(self):
        effective_license = self.conn.get_effective_license()
        self._show(effective_license)
        return effective_license

    @Subcommand('check', 'license',
                help='check supplied license')
    @Argument('--license-file', required=True, help='the license file to check')  # noqa
    def check_license(self, license_file):
        with open(license_file) as f:
            license_info = self.conn.check_license(f.read())
            self._show(license_info)
            return license_info

    @Subcommand('set', 'license',
                help='set the license for the domain')
    @Argument('--license-file', required=True, help='the license file to install')  # noqa
    @Argument('--allow-downgrade', action='store_true',
              help='whether to install the license regardless of whether it is a downgrade from the current license')  # noqa
    def set_license(self, license_file, allow_downgrade=False):
        with open(license_file) as f:
            return self.conn.set_license(f.read(), allow_downgrade)

    @Subcommand('hotcopy', 'database',
                help='issue a hot-copy request on a database')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database to hot-copy')
    @Argument('--type', required=True,
              choices=['full', 'incremental', 'journal'],
              help='the type of hot-copy to perform')
    @Argument('--shared', action='store_true',
              help='whether the backup location specified by --default-backup-dir is on shared storage')  # noqa
    @Argument('--default-backup-dir', required=False,
              help='backup location to use for any archive that does not have a backup location associated with it by --backup-dirs')  # noqa
    @Argument('--backup-dirs', nargs='*',
              completer=CommandProcessor.get_backup_dirs_token,
              help='map of archive ID to backup location to use for that archive')  # noqa
    @Argument('--timeout', required=False,
              help='if specified, the time to wait in seconds for the hot-copy to complete; if not specified, the request is issued asynchronously')  # noqa
    def hotcopy_database(self, db_name, type, shared=False,
                         default_backup_dir=None, backup_dirs=None,
                         timeout=None):
        if not isinstance(backup_dirs, collections.Mapping):
            backup_dirs = CommandProcessor.dict_from_tokens(backup_dirs)
        hotcopy_response = self.conn.hotcopy_database(
            db_name, type, shared=shared,
            default_backup_dir=default_backup_dir, backup_dirs=backup_dirs,
            timeout_sec=timeout)
        self._show(hotcopy_response)
        return hotcopy_response

    @Subcommand('get', 'hotcopy-status',
                help='get the status of a hot-copy request')
    @Argument('--coordinator-start-id', required=True,
              help='the start ID of the SM coordinating the hot-copy')
    @Argument('--hotcopy-id', required=True,
              help='the ID of the hot-copy request')
    @Argument('--timeout', required=False,
              help='if specified, the time to wait in seconds for the hot-copy to complete; if not specified, the status is polled without waiting')  # noqa
    def get_hotcopy_status(self, coordinator_start_id, hotcopy_id,
                           timeout=None):
        hotcopy_response = self.conn.get_hotcopy_status(
            coordinator_start_id, hotcopy_id, timeout_sec=timeout)
        self._show(hotcopy_response)
        return hotcopy_response

    @Subcommand('get', 'sql-connection',
                help='get TE to service a SQL connection')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database to get a SQL connection for')
    @Argument('--connection-properties', required=False, nargs='*',
              default=EnvironmentalDefault(),
              help='connection properties for connection request')
    def get_sql_connection(self, db_name, connection_properties=None):
        connection_properties = CommandProcessor.dict_from_tokens(
            connection_properties)
        te = self.conn.get_sql_connection(db_name, **connection_properties)
        if te is not None:
            self._show(te)
            return te

    @Subcommand('set', 'load-balancer-config',
                help='set a load-balancing configuration')
    @MutuallyExclusive(
        Argument('--db-name',
                 help='the name to register default for'),
        Argument('--is-global', action='store_true',
                 help='whether to register global default'),
        required=True)
    @MutuallyExclusive(
        Argument('--default',
                 help='the default load-balancer register'),
        Argument('--unregister-default', action='store_true',
                 help='whether to unregister current default'))
    @MutuallyExclusive(
        Argument('--prefilter',
                 help='the prefilter to register'),
        Argument('--unregister-prefilter', action='store_true',
                 help='whether to unregister the current prefilter'))
    def set_load_balancer_config(self, db_name=None, is_global=False,
                                 default=None, unregister_default=False,
                                 prefilter=None, unregister_prefilter=False):
        self.conn.set_load_balancer_config(
            db_name=db_name, is_global=is_global,
            default=default, unregister_default=unregister_default,
            prefilter=prefilter, unregister_prefilter=unregister_prefilter)

    @Subcommand('get', 'load-balancer-config',
                help='get load-balancer configuration for all databases')
    def get_load_balancer_config(self):
        lb_configs = self.conn.get_load_balancer_configs()
        for config in lb_configs:
            self._show(config)
        return lb_configs

    @Subcommand('set', 'load-balancer',
                help='set a load-balancing policy')
    @Argument('--policy-name', required=True,
              help='the name of the load-balancer policy to set')
    @Argument('--lb-query', required=True,
              help='the load-balancer query to set')
    def set_load_balancer_policy(self, policy_name, lb_query):
        self.conn.set_load_balancer_policy(policy_name, lb_query)

    @Subcommand('delete', 'load-balancer',
                help='remove a load-balancer policy')
    @Argument('--policy-name', required=True,
              completer=CommandProcessor.get_db_names,
              help='the name of the load-balancer policy to delete')
    def delete_load_balancer_policy(self, policy_name):
        self.conn.remove_load_balancer_policy(policy_name)

    @Subcommand('get', 'load-balancers',
                help='get all load-balancing policies')
    def get_load_balancer_policies(self):
        lb_policies = self.conn.get_load_balancer_policies()
        for policy in lb_policies:
            self._show(policy)
        return lb_policies

    HOSTNAME = nuodb_mgmt.resolve_hostname()
    DEFAULT_DNAME = 'CN=' + HOSTNAME
    STORE_TYPES = dict(jks='JKS', p12='PKCS12')

    def _get_type_and_alias(self, keystore, store_type, alias):
        if store_type is None:
            ext = keystore.split(os.path.extsep)[-1]
            store_type = self.STORE_TYPES.get(ext, 'JKS')
        if alias is None:
            basename = os.path.basename(keystore)
            alias = os.path.splitext(basename)[0]
        return (store_type, alias)

    def _get_san_args(self, sub_altnames, resolve_san):
        if sub_altnames is None:
            sub_altnames = []
        if resolve_san:
            sub_altnames.append('dns:' + self.HOSTNAME)
        return (['-ext', 'san=' + ','.join(sub_altnames)]
                if len(sub_altnames) != 0 else
                [])

    @Subcommand('create', 'keypair',
                help='create a key-pair')
    @Argument('--keystore', required=True,
              help='the keystore to store the generated key-pair into, which will be created if it does not exist')  # noqa
    @Argument('--store-type', required=False, choices=['JKS', 'PKCS12'],
              help='the type of the keystore; is derived from --keystore value if not specified')  # noqa
    @Argument('--alias', required=False,
              help='the alias to store the key-pair as; is derived from --keystore value if not specified')  # noqa
    @Argument('--store-password', required=True,
              help='the password for the keystore')
    @Argument('--key-password', required=False,
              help='the password for the key-pair; defaults to --store-password value if not specified')  # noqa
    @Argument('--dname', default=DEFAULT_DNAME,
              help='the distinguished name of the certificate')
    @Argument('--sub-altnames', nargs='*',
              help='list of subjectAltNames for the certificate; must be prefixed by type, e.g. dns:hostname')  # noqa
    @Argument('--resolve-san', action='store_true',
              help='whether to resolve subjectAltName using DNS, e.g. dns:hostname')  # noqa
    @Argument('--algorithm', default='RSA', choices=['RSA', 'DSA', 'EC'],
              help='the key algorithm')
    @Argument('--validity', default=365, type=int,
              help='the validity in days of the certificate')
    @Argument('--start-date', required=False,
              help='start date of the certificate')
    @Argument('--ca', action='store_true',
              help='whether the generated certificate should be used as CA')
    def create_keypair(self, keystore, store_password, key_password=None,
                       store_type=None, alias=None, dname=DEFAULT_DNAME,
                       sub_altnames=None, resolve_san=False, algorithm='RSA',
                       validity=365, ca=False, start_date=None):
        store_type, alias = self._get_type_and_alias(
            keystore, store_type, alias)
        if key_password is None:
            key_password = store_password
        args = ['keytool', '-genkeypair', '-keystore', keystore,
                '-storetype', store_type, '-alias', alias,
                '-storepass', store_password, '-keypass', key_password,
                '-dname', dname, '-keyalg', algorithm,
                '-validity', str(validity)]
        args += self._get_san_args(sub_altnames, resolve_san)
        if ca:
            args += ['-ext', 'bc:c']
        if start_date:
            args += ['-startdate', start_date.replace('\\', '')]

        ret = subprocess.call(args)
        sys.exit(ret)

    def _get_cert(self, nuokey_cmd, keystore, store_password,
                  key_password=None, store_type=None, alias=None,
                  cert_only=False):
        store_type, alias = self._get_type_and_alias(
            keystore, store_type, alias)
        if key_password is None:
            key_password = store_password
        args = [nuokey_cmd, 'export', '--keystore', keystore,
                '--storetype', store_type, '--alias', alias,
                '--storepass', store_password, '--keypass', key_password]
        if cert_only:
            args += ['--cert-only']
        return subprocess.check_output(args)

    def _get_csr(self, keystore, store_password, store_type=None, alias=None):
        store_type, alias = self._get_type_and_alias(
            keystore, store_type, alias)
        args = ['keytool', '-certreq', '-keystore', keystore,
                '-storetype', store_type, '-alias', alias,
                '-storepass', store_password]
        return subprocess.check_output(args)

    def _get_signed_cert(self, csr, ca_keystore, ca_store_password,
                         ca_store_type=None, ca_alias=None, validity=365,
                         ca=False, start_date=None, sub_altnames=None,
                         resolve_san=False):
        ca_store_type, ca_alias = self._get_type_and_alias(
            ca_keystore, ca_store_type, ca_alias)
        args = ['keytool', '-gencert', '-keystore', ca_keystore,
                '-storetype', ca_store_type, '-alias', ca_alias,
                '-storepass', ca_store_password, '-rfc',
                '-validity', str(validity)]
        args += self._get_san_args(sub_altnames, resolve_san)
        if ca:
            args += ['-ext', 'bc:c']
        if start_date:
            args += ['-startdate', start_date.replace('\\', '')]
        # fix keytool output, which prints base64 with Windows line-endings
        # (CRLF) for some reason
        return self._check_output(args, csr).replace('\r\n', '\n')

    def _import_cert(self, keystore, store_password, store_type=None,
                     alias=None, cert=None, cert_file=None, interactive=False):
        store_type, alias = self._get_type_and_alias(
            keystore, store_type, alias)
        if cert_file is None:
            cert_file = tempfile.mktemp()
            with open(cert_file, 'w') as f:
                f.write(cert)
        args = ['keytool', '-import', '-keystore', keystore,
                '-storetype', store_type, '-alias', alias,
                '-storepass', store_password, '-file', cert_file,
                '-trustcacerts']
        # if non-interactive, add -noprompt option and suppress output
        if not interactive:
            return self._check_output(args, 'y')
        subprocess.call(args)

    @Subcommand('show', 'certificate',
                help='output key-pair or certificate from a keystore as a base64-encoded string according to RFC-7468')  # noqa
    @Argument('--keystore', required=True,
              help='the keystore to extract key-pair or certificate from')  # noqa
    @Argument('--store-type', required=False, choices=['JKS', 'PKCS12'],
              help='the type of the keystore; is derived from --keystore value if not specified')  # noqa
    @Argument('--alias', required=False,
              help='the alias of the key-pair or certificate; is derived from --keystore value if not specified')  # noqa
    @Argument('--store-password', required=True,
              help='the password for the keystore')
    @Argument('--key-password', required=False,
              help='the password for the key-pair; defaults to --store-password value if not specified')  # noqa
    @Argument('--cert-only', action='store_true',
              help='whether to only export the certificate')
    @Argument('--nuokey-cmd', required=True,
              default=EnvironmentalDefault(from_nuodb_home('etc', 'nuokeymgr')), # noqa
              help='the path to the nuokeymgr executable')
    def show_certificate(self, nuokey_cmd, keystore, store_password,
                         key_password=None, store_type=None, alias=None,
                         cert_only=False):
        self.out.write(self._get_cert(
            nuokey_cmd, keystore, store_password, key_password=key_password,
            store_type=store_type, alias=alias, cert_only=cert_only))

    @Subcommand('sign', 'certificate',
                help='sign a certificate in a keystore with a CA certificate')  # noqa
    @Argument('--keystore', required=True,
              help='the keystore containing the certificate to sign')
    @Argument('--store-type', required=False, choices=['JKS', 'PKCS12'],
              help='the type of the keystore; is derived from --keystore value if not specified')  # noqa
    @Argument('--alias', required=False,
              help='the alias of the certificate; is derived from --keystore value if not specified')  # noqa
    @Argument('--store-password', required=True,
              help='the password for the keystore')
    @Argument('--ca-keystore', required=True,
              help='the keystore containing the CA certificate')
    @Argument('--ca-store-type', required=False, choices=['JKS', 'PKCS12'],
              help='the type of the CA keystore; is derived from --ca-keystore value if not specified')  # noqa
    @Argument('--ca-alias', required=False,
              help='the alias of the CA certificate; is derived from --ca-keystore value if not specified')  # noqa
    @Argument('--ca-store-password', required=True,
              help='the password for the CA keystore')
    @Argument('--update', action='store_true',
              help='whether to update the keystore with the signed certificate; if not specified, the certificate chain is written to standard output')  # noqa
    @Argument('--sub-altnames', nargs='*',
              help='list of subjectAltNames for the certificate; must be prefixed by type, e.g. dns:hostname')  # noqa
    @Argument('--resolve-san', action='store_true',
              help='whether to resolve subjectAltName using DNS, e.g. dns:hostname')  # noqa
    @Argument('--validity', default=365, type=int,
              help='the validity in days of the certificate')
    @Argument('--start-date', required=False,
              help='start date of the certificate')
    @Argument('--ca', action='store_true',
              help='whether the generated certificate should be used as CA')
    @Argument('--nuokey-cmd', required=True,
              default=EnvironmentalDefault(from_nuodb_home('etc', 'nuokeymgr')), # noqa
              help='the path to the nuokeymgr executable')
    def sign_certificate(self, nuokey_cmd, keystore, store_password,
                         ca_keystore, ca_store_password, store_type=None,
                         alias=None, ca_store_type=None, ca_alias=None,
                         update=False, validity=365, ca=False,
                         start_date=None, sub_altnames=None,
                         resolve_san=False):
        # generate a certificate signing request
        csr = self._get_csr(keystore, store_password, store_type, alias)
        # sign certificate using CA certificate
        cert = self._get_signed_cert(csr, ca_keystore, ca_store_password,
                                     ca_store_type, ca_alias, validity, ca,
                                     start_date, sub_altnames, resolve_san)
        # add CA certificate to client certificate
        ca_cert = self._get_cert(
            nuokey_cmd, ca_keystore, ca_store_password,
            store_type=ca_store_type, alias=ca_alias, cert_only=True)
        cert_chain = '{}\n{}\n'.format(cert.strip(), ca_cert.strip())
        if update:
            # update certificate in keystore
            self._import_cert(keystore, store_password, store_type, alias,
                              cert=cert_chain)
        else:
            self.out.write(cert_chain)

    @Subcommand('import', 'certificate',
                help='import a certificate into a truststore')
    @Argument('--keystore', required=True,
              help='the keystore containing the certificate')
    @Argument('--store-type', required=False, choices=['JKS', 'PKCS12'],
              help='the type of the keystore; is derived from --keystore value if not specified')  # noqa
    @Argument('--alias', required=False,
              help='the alias of the certificate; is derived from --keystore value if not specified')  # noqa
    @Argument('--store-password', required=True,
              help='the password for the keystore')
    @Argument('--truststore', required=True,
              help='the keystore containing trusted certificates')
    @Argument('--truststore-type', required=False, choices=['JKS', 'PKCS12'],
              help='the type of the truststore; is derived from --truststore value if not specified')  # noqa
    @Argument('--truststore-password', required=True,
              help='the password for the truststore')
    @Argument('--for-recovery', action='store_true',
              help='store the certificate so that it is protected from truststore updates made using `nuocmd add/remove trusted-certificates`')  # noqa
    @Argument('--nuokey-cmd', required=True,
              default=EnvironmentalDefault(from_nuodb_home('etc', 'nuokeymgr')), # noqa
              help='the path to the nuokeymgr executable')
    def import_certificate(self, nuokey_cmd, keystore, store_password,
                           truststore, truststore_password, store_type=None,
                           alias=None, truststore_type=None,
                           for_recovery=False):
        store_type, alias = self._get_type_and_alias(
            keystore, store_type, alias)
        # get certificate chain
        cert = self._get_cert(nuokey_cmd, keystore, store_password,
                              store_type=store_type, alias=alias,
                              cert_only=True)
        # if `--for-recovery` was specified, add prefix to alias that protects
        # it from changes made using REST API
        if for_recovery:
            alias = '__recovery__' + alias
        # update certificate in keystore
        self._import_cert(truststore, truststore_password, truststore_type,
                          alias, cert=cert)

    def _check_output(self, args, stdin=None):
        p = subprocess.Popen(args, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        out, err = p.communicate(stdin)
        ret = p.poll()
        if ret != 0:
            self.out.write(out)
            sys.exit(ret)
        return out

    @Subcommand('create', 'region', help='create a region')
    @Argument('--name', required=True, help='the name of the region')
    def create_region(self, name):
        region = self.conn.create_region(name)
        self._show(region)
        return region

    @Subcommand('delete', 'region', help='delete a region')
    @Argument('--region-id', required=True,
              completer=CommandProcessor.get_region_ids,
              help='the ID of the region to delete')
    def delete_region(self, region_id):
        self.conn.delete_region(region_id)

    @Subcommand('get', 'regions', help='get regions')
    def get_regions(self):
        regions = self.conn.get_regions()
        for region in regions:
            self._show(region)
        return regions

    @Subcommand('show', 'regions', help='show regions')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the database to show regions for')
    @Argument('--region-format', default=EnvironmentalDefault(REGION_FMT),
              help='format string for regions')
    @Argument('--process-format',
              default=EnvironmentalDefault(SHORT_PROCESS_FMT),
              help='format string for processes')
    def show_regions(self, db_name, region_format=REGION_FMT,
                     process_format=SHORT_PROCESS_FMT):
        database = self.conn.get_database(db_name)
        # invert map of server ID to region ID
        region_map = {}
        for server_id, region_id in database.server_assignments.items():
            if region_id not in region_map:
                region_map[region_id] = [server_id]
            else:
                region_map[region_id].append(server_id)
        # also build map of server ID to process
        server_map = {}
        for process in self.conn.get_processes(db_name):
            if process.server_id not in server_map:
                server_map[process.server_id] = [process]
            else:
                server_map[process.server_id].append(process)

        # add unassigned servers to default region
        region_map[database.default_region_id] = [
            server_id for server_id in server_map.keys()
            if server_id not in database.server_assignments]
        # for each region, show all servers assigned to it and all running
        # processes on those servers
        for region in self.conn.get_regions():
            self._print(get_formatted(region_format, region))
            server_ids = region_map.get(region.id, [])
            server_ids.sort()
            for server_id in server_ids:
                self._print('  [server_id = {}]', server_id)
                for process in server_map.get(server_id, []):
                    self._print('    ' + get_formatted(process_format,
                                                       process))

    @Subcommand('add', 'region-assignment', help='add servers to a region')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database to add the region mapping for')
    @MutuallyExclusive(
        Argument('--region-name',
                 completer=CommandProcessor.get_region_names,
                 help='the name of the region to add servers to'),
        Argument('--region-id',
                 completer=CommandProcessor.get_region_ids,
                 help='the ID of the region to add servers to'),
        required=True)
    @Argument('--server-ids', nargs='+', required=True,
              completer=CommandProcessor.get_server_ids,
              help='the IDs of the servers to add to region')
    def add_region_assignment(self, db_name, server_ids, region_id=None,
                              region_name=None):
        if region_id is None:
            # get the region ID if specified by name
            if region_name is None:
                # this can only happen if we invoke this method directly
                raise ValueError(
                    'One of region_id, region_name must be specified')
            region_id = self._get_region_id(region_name)
        for server_id in server_ids:
            self.conn.add_server_assignment(db_name, region_id, server_id)

    def _get_region_id(self, region_name, regions_by_name=None):
        if regions_by_name is None:
            regions_by_name = self._get_regions_by_name()
        if region_name not in regions_by_name:
            # make sure region exists
            raise ValueError('No region named \'{}\''.format(region_name))
        return regions_by_name[region_name]

    def _get_regions_by_name(self):
        regions = self.conn.get_regions()
        return dict((region.name, region.id) for region in regions)

    @Subcommand('remove', 'region-assignment',
                help='remove servers from their current region')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='the name of the database to remove the region mapping for')
    @Argument('--server-ids', nargs='+', required=True,
              completer=CommandProcessor.get_server_ids,
              help='the IDs of the servers to remove from region')
    def remove_region_assignment(self, db_name, server_ids):
        for server_id in server_ids:
            self.conn.remove_server_assignment(db_name, server_id)

    @Subcommand('check', 'process',
                help='Check the status of a process')
    @Argument('--start-id', required=True,
              help='the Start ID of the process to check')
    @MutuallyExclusive(
        Argument('--check-running', action='store_true', default=False,
                 help='Check that the process is in the RUNNING state'),
        Argument('--check-exited', action='store_true', default=False,
                 help='Check that the process has exited'))
    @Argument('--check-liveness', default=None, type=float,
              help='Check that the process has responded within the specified number of seconds')  # noqa
    @MutuallyExclusive(
        Argument('--timeout', default=None, type=float,
                 help="How long (in seconds) to wait for process check to pass"),  # noqa
        Argument('--wait-forever', action='store_true', default=False,
                 help='Wait forever for process check to pass'))
    def check_process(self, start_id, check_running=False, check_exited=False,
                      check_liveness=None, timeout=None, wait_forever=False):
        if check_exited and check_liveness is not None:
            raise RuntimeError('argument --check-exited not allowed with argument --check-liveness')  # noqa
        if timeout is None and wait_forever:
            timeout = CommandProcessor.FOREVER
        proc = None
        if timeout is not None:
            proc = self._await(lambda: self.conn.get_process(start_id),
                               timeout)
        if not check_exited and type(proc) is nuodb_mgmt.ExitedProcess:
            raise RuntimeError(
                'Process with Start ID {} has already exited: \'{}\''
                .format(start_id, proc.reason))
        if timeout is not None:
            return self._await(
                lambda: self._check_process(
                    start_id, check_running, check_exited, check_liveness),
                timeout)
        return self._check_process(start_id, check_running, check_exited,
                                   check_liveness)

    def _check_process(self, start_id, check_running, check_exited,
                       check_liveness=None):
        proc = self.conn.get_process(start_id)
        if not check_exited and type(proc) is nuodb_mgmt.ExitedProcess:
            raise RuntimeError(
                'Process with Start ID {} has already exited: \'{}\''
                .format(start_id, proc.reason))
        if check_exited and type(proc) is not nuodb_mgmt.ExitedProcess:
            raise RuntimeError(
                'Process with Start ID {} has not exited. Has state \'{}\''
                .format(start_id, proc.engine_state))
        if check_running:
            if proc.engine_state != 'RUNNING':
                raise RuntimeError(
                    'Process with Start ID {} not in \'RUNNING\' state. Has state \'{}\''  # noqa
                    .format(start_id, proc.engine_state))
        if check_liveness is not None:
            if proc.last_ack is None:
                raise RuntimeError(
                    'Process with Start ID {} unresponsive for longer than 60 seconds'  # noqa
                    .format(start_id))
            if proc.last_ack > check_liveness:
                raise RuntimeError(
                    'Process with Start ID {} unresponsive for the last {} seconds'  # noqa
                    .format(start_id, proc.last_ack))
        return proc

    @Subcommand('check', 'servers',
                help='Check the status of admin servers')
    @MutuallyExclusive(
        Argument('--timeout', default=None, type=float,
                 help='How long (in seconds) to wait for server check to pass'),  # noqa
        Argument('--wait-forever', action='store_true', default=False,
                 help='Wait forever for server check to pass'))
    @Argument('--check-active', action='store_true', default=False,
              help='Check that all servers are ACTIVE')
    @Argument('--check-connected', action='store_true', default=False,
              help='Check that all servers are CONNECTED to the server performing check')  # noqa
    @Argument('--check-leader', action='store_true', default=False,
              help='Check that all servers agree on a leader')
    @Argument('--num-servers', default=None,
              help='Check that membership size equals specified number')
    def check_servers(self, check_active=False, check_connected=False,
                      check_leader=False, num_servers=None, timeout=None,
                      wait_forever=False):
        if timeout is None and wait_forever:
            timeout = CommandProcessor.FOREVER
        if timeout is not None:
            return self._await(
                lambda: self._check_servers(
                    check_active, check_connected, check_leader, num_servers),
                timeout)
        else:
            return self._check_servers(
                check_active, check_connected, check_leader, num_servers)

    def _check_servers(self, check_active=False, check_connected=False,
                       check_leader=False, num_servers=None):
        servers = self.conn.get_servers()
        api_server = None
        inactive = set()
        disconnected = set()
        leader_terms = {}
        leaderless = set()
        for server in servers:
            if server.is_local:
                api_server = server
            if server.raft_state != 'ACTIVE':
                inactive.add(server.id)
            if server.connected_state != 'Connected':
                disconnected.add(server.id)
            key = (server.leader, server.log_term)
            leader_terms[key] = leader_terms.get(key, set())
            leader_terms[key].add(server.id)
            if server.leader is None:
                leaderless.add(server.id)

        msg = ''
        # if `check_active`, check that all server are ACTIVE; otherwise
        # only check server performing health-check
        if check_active and len(inactive) != 0:
            msg += 'Servers not ACTIVE: {}\n'.format(
                ', '.join(sorted(inactive)))
        elif api_server.id in inactive:
            msg += '{} is not ACTIVE\n'.format(api_server.id)
        # if `check_connected`, check that all servers are CONNECTED to the
        # server performing health-check
        if check_connected and len(disconnected) != 0:
            msg += 'Servers not CONNECTED to {}: {}\n'.format(
                api_server.id, ', '.join(sorted(disconnected)))
        # if `check_leader`, check that all servers agree on leader and
        # term; otherwise, only check that the server performing
        # health-check recognizes some server as leader
        if check_leader and len(leader_terms) != 1:
            msg += 'Non-unique LEADER:\n'
            for (leader, term), server_ids in leader_terms.items():
                msg += '  ({},{})->[{}]\n'.format(
                    leader, term, ','.join(sorted(server_ids)))
        elif check_leader and len(leaderless) != 0:
            msg += 'Servers without LEADER: {}\n'.format(
                ', '.join(sorted(leaderless)))
        # if `num_servers` was specified, check membership size
        if num_servers is not None and int(num_servers) != len(servers):
            msg += ('Unexpected number of servers: expected={}, actual={}'
                    .format(num_servers, len(servers)))

        if msg != '':
            raise RuntimeError('Health-check failed:\n' + msg)

        return servers

    @Subcommand('check', 'database',
                help='Check the status of a database')
    @Argument('--db-name', required=True, default=EnvironmentalDefault(),
              completer=CommandProcessor.get_db_names,
              help='The name of the database to check')
    @MutuallyExclusive(
        Argument('--timeout', default=None, type=float,
                 help='How long (in seconds) to wait for database check to pass'),  # noqa
        Argument('--wait-forever', action='store_true', default=False,
                 help='Wait forever for database check to pass'))
    @Argument('--check-running', action='store_true', default=False,
              help='Check that the database is in the RUNNING state')
    @Argument('--num-processes', default=None,
              help='Check that the database contains the specified number of processes')  # noqa
    @Argument('--check-liveness', default=None, type=float,
              help='Check that all processes have responded within the specified number of seconds')  # noqa
    def check_database(self, db_name, check_running=False, num_processes=None,
                       check_liveness=None, timeout=None, wait_forever=False):
        if timeout is None and wait_forever:
            timeout = CommandProcessor.FOREVER
        if timeout is not None:
            return self._await(
                lambda: self._check_database(
                    db_name, check_running, num_processes, check_liveness),
                timeout)
        return self._check_database(
            db_name, check_running, num_processes, check_liveness)

    def _check_database(self, db_name, check_running=False, num_processes=None,
                        check_liveness=None):
        database = self.conn.get_database(db_name)
        if check_running and database.state != 'RUNNING':
            raise RuntimeError('Database {} is not RUNNING: {}'.format(
                db_name, database))
        if num_processes is not None:
            # check that all processes have expected state
            processes = self.conn.get_processes(db_name)
            non_running = [str(p) for p in processes
                           if p.durable_state != 'MONITORED'
                           or p.engine_state != 'RUNNING']
            if len(non_running) != 0:
                raise RuntimeError(
                    'Database {} has non-running processes: \n{}'.format(
                        db_name, '\n'.join(non_running)))
            # check that there are no unresponsive process if `check_liveness`
            # was specified; `check_liveness` should be the maximum number of
            # seconds since the last message from a process
            if check_liveness is None:
                unresponsive = []
            else:
                check_liveness = int(check_liveness)
                unresponsive = [str(p) for p in processes
                                if p.last_ack is None
                                or p.last_ack > check_liveness]
            if len(unresponsive) != 0:
                raise RuntimeError(
                    'Database {} has unresponsive processes: \n{}'.format(
                        db_name, '\n'.join(unresponsive)))
            # check number of processes
            num_processes = int(num_processes)
            if num_processes != len(processes):
                raise RuntimeError(
                    'Unexpected number of processes: expected={}, actual={}'
                    .format(num_processes, len(processes)))
        if database.state == 'TOMBSTONE':
            raise RuntimeError('Database {} in TOMBSTONE state: {}'.format(
                db_name, database))
        return database

    def _print_database_processes(self, database, process_format):
        for process in self.conn.get_processes(database.name):
            if process.last_ack is None or process.last_ack > 20:
                process._dict['state'] = 'UNREACHABLE({})'.format(
                    process.engine_state)
            self._print('    ' + get_formatted(process_format, process))

    def _print_exited_database_processes(self, db_name, low_incarnation,
                                         db_incarnation,
                                         exited_process_format):
        current_incarnation = db_incarnation
        exited_processes = self.conn.get_exited_processes(db_name)
        # sort processes by (incarnation, start ID) in descending order of
        # incarnation
        exited_processes.sort(key=lambda exited: (-exited.db_incarnation[0],
                                                  -exited.db_incarnation[1],
                                                  exited.process.start_id))
        for exited in exited_processes:
            if exited.db_incarnation[0] < low_incarnation:
                continue

            if current_incarnation != exited.db_incarnation[0]:
                current_incarnation = exited.db_incarnation[0]
                self._print('  [incarnation = {}]', current_incarnation)
            self._print('    ' + get_formatted(exited_process_format, exited))

    def _show(self, obj):
        if isinstance(obj, nuodb_mgmt.Entity):
            obj.show(self.show_json, self.out)
        elif isinstance(obj, collections.Mapping):
            self._print(json.dumps(obj, indent=2, sort_keys=True))
        else:
            self._print(obj)

    def _print(self, fmt, *args):
        if len(args) != 0:
            if not isinstance(fmt, basestring):
                raise ValueError('First argument should be a format string' +
                                 ' if multiple values are supplied')
            msg = fmt.format(*args)
        else:
            msg = str(fmt)

        self.out.write(msg)
        self.out.write('\n')

    @staticmethod
    def _await(check_fn, timeout, initial_delay=0.25):
        delay = initial_delay
        start_time = time.time()
        while True:
            try:
                return check_fn()
            except Exception:
                remaining = timeout - (time.time() - start_time)
                if remaining > 0:
                    time.sleep(max(initial_delay, min(remaining, delay)))
                    delay = min(10, delay*2)
                else:
                    raise


PROCESSOR = CommandProcessor()


def read_capture_file(capture_file):
    """
    Return database name and list of processes from capture file.

    :param str capture_file: path to capture file

    :returns str, list[nuodb_mgmt.StartProcessRequest]: database name and list
                                                        of processes
    """

    with open(capture_file) as f:
        return read_capture_data(json.loads(f.read()))


def read_capture_data(capture_data):
    """
    Return list of processes from capture file.

    :param dict capture_data: data from capture file

    :returns str, list[nuodb_mgmt.StartProcessRequest]: database name and list
                                                        of processes
    """

    if capture_data.get('incremental', False):
        raise ValueError('Cannot enforce database using incremental startplan')

    proc_specs = map(nuodb_mgmt.StartProcessRequest, capture_data['processes'])
    # order process specifications so that TEs appear last
    proc_specs.sort(lambda x, y: cmp(y.archive_id, x.archive_id))
    if len(proc_specs) == 0:
        return None, []

    # make sure that a unique database name appears in capture file
    db_name = set(spec.db_name for spec in proc_specs)
    if len(db_name) == 0:
        raise ValueError('Invalid capture file: ' + json.dumps(capture_data))
    if len(db_name) > 1:
        raise ValueError(
            'Inconsistent database names in capture file: {}\n{}'.format(
                db_name, capture_data))
    return db_name.pop(), proc_specs


class OptionalFormatter(string.Formatter):
    """
    Custom formatter that leaves out unspecified keys and allows defaults to be
    specified using the syntax '{<key>::<default>}'.
    """

    def get_value(self, key, args, kwargs):
        if isinstance(key, basestring):
            return kwargs.get(key)
        return super(OptionalFormatter, self).get_value(key, args, kwargs)

    def format_field(self, value, spec):
        if ':' in spec:
            # conversion specifiers are already denoted using ':', e.g.
            # {number:.2f}, so any ':' inside of it is denoting the default
            # value using our custom syntax, e.g. {number:.2f:0.00}; so we need
            # to strip away the ':<default>' part from it so that the
            # superclass receives the real specifier
            spec, default = spec.rsplit(':', 1)
        else:
            default = '<NO VALUE>'

        if value is None:
            # value is None, so return default
            return default
        # value was found, so use do normal conversion with real specifier
        return super(OptionalFormatter, self).format_field(value, spec)


def get_formatted(fmt, entity):
    """
    Format an entity.

    :param str fmt: format string
    :param nuodb_mgmt.Entity entity: entity to format

    :returns str: formatted entity
    """

    if isinstance(entity, nuodb_mgmt.Entity):
        params = dict(entity._dict)
        params.update(entity.get_declared())
    elif isinstance(entity, collections.Mapping):
        params = entity
    else:
        raise ValueError('Cannot format object of type {}'
                         .format(type(entity)))
    return OptionalFormatter().format(fmt, **params)


def subcommand(func, processor=PROCESSOR):
    """
    Create a subcommand on the supplied CommandProcessor by inspecting the
    function signature to determine the subcommand name and arguments. This is
    a simpler but less flexible approach than using
    `@CommandProcessor.subcommand()` and `@Argument` directly.

    Example:

    ```
    #!/usr/bin/env python
    # ~ cmd.py ~
    import nuodb_cli

    class CustomSubcommands(nuodb_cli.AdminCommands):

        @nuodb_cli.subcommand
        def do_custom_thing(self, required, optional=None, switch=False):
            ...

    if __name__ == '__main__':
        nuodb_cli.execute()
    ```

    This creates a subcommand that is invoked as follows:

        ./cmd.py do custom-thing --required value --switch

    :param CommandProcessor processor: the CommandProcessor object
    :param function func: the function to create a subcommand from, which is
                          assumed to be an AdminCommands method or an ordinary
                          function that takes an AdminCommands object as the
                          first argument
    """

    # get action and entity from function name; action is the first word
    # (delimited by '_') and entity is all remaining words (with '_' replaced
    # by '-')
    action, entity = func.func_name.split('_', 1)
    entity = entity.replace('_', '-')

    # get all argument names and default values
    argspec = inspect.getargspec(func)
    if len(argspec.args) == 0:
        raise ValueError('Subcommand method must take at least one argument of type AdminCommands')  # noqa
    if argspec.keywords is not None or argspec.varargs is not None:
        raise ValueError('Subcommand method cannot take varargs or kwargs')
    # create kwargs for each call to Argument decorator;
    # argspec.defaults contains defaults corresponding to suffix of
    # argspec.args; if there are no defaults in function signature,
    # argspec.defaults is None
    defaults = argspec.defaults
    if defaults is None:
        defaults = ()
    kwargs_list = [dict(required=True)] * (len(argspec.args) - len(defaults))
    for default in defaults:
        kwargs = dict(default=default)
        # if default is False, make argument a switch
        if default is False:
            kwargs['action'] = 'store_true'
        kwargs_list.append(kwargs)

    # manually apply Argument decorator to function for every argument except
    # the first (which should be an AdminCommands object)
    for argname, kwargs in zip(argspec.args, kwargs_list)[1:]:
        Argument('--' + argname.replace('_', '-'), **kwargs)(func)

    # finally, apply the Subcommand decorator to function
    Subcommand(action, entity)(func)
    Subcommand.add_subcommand(processor, func)
    return func


def execute(command_handler=None):
    check_version()
    check_dependencies()
    PROCESSOR.execute(command_handler=command_handler)


if __name__ == '__main__':
    execute()
