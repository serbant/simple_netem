'''
.. _simple_netem_daemon:

serve_pyro4r module for the simple_netem package

:module:     daemon

:copyright:

    Copyright 2017 Serban Teodorescu

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

:contact:    serbant@gmail.com

exposes the functionality provided by the simple_netem package for remote
access. this script can be executed as a system service on a Linux host

'''
from __future__ import unicode_literals, absolute_import, division

import sys
import copy
import logging
import argparse
import Pyro4
import Pyro4.naming

import config

from control import NetemInterface


def main(argv=None):
    '''
    main

    '''
    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    _args = _get_args()
    serve_pyro4(p4_args=_args)


def configure_pyro4():
    '''
    the Pyro4 settings required by this program are not the defaults

    we must use a multiplexed server because we are accessing fixed, shared
    resources.

    we need to use a serializer that accepts Python class types so that we can
    pass emulation objects from the client side to the server side. Pyro4
    considers such serializers as not secure and will not expose them unless
    so configured. there are 2 such serializers available: dill and pickle.

    '''
    Pyro4.config.SERVERTYPE = config.P4_SERVERTYPE
    Pyro4.config.SERIALIZERS_ACCEPTED.add('pickle')


def _locate_pyro4_ns(p4_args):
    '''
    locate a Pyro4 naming server if so specified in the start-up arguments

    if there is a Pyro4 naming server running on this subnet, then return a
    proxy for it.

    note that this function as written and invoked in this module can only
    locate name servers that accept the serializer specified in the config
    module. by default the pyro4 name server (pyro4-ns) doesn't accept
    the insecure serializers required by this module.

    to start a stand-alone pyro4 nameserver that can be used by this module,
    execute:

        export PYRO_SERIALIZERS_ACCEPTED= export PYRO_SERIALIZERS_ACCEPTED=serpent,json,marshal,the_P4_PICKLE_config_value
        pyro4-ns -n host [-p port] -k the_P4_HMAC_config_value

    where host must be resolvable host name or IP address

    :arg p4_args: the arguments used to start the daemon
    :type p4_args: :class:`<_Args>`

    :returns: a pyro4 proxy for the name server or None
    :rtype: :class:`<Pyro4.core.Proxy>`

    #TODO: figure out a way to check the registration and handle problems
        with serializers. hmmm, quickie server with one of the emulation
        classes and try to register it and then list the methods?
    '''
    p4_args.logger.debug('looking for external name server')
    try:
        name_server = Pyro4.locateNS(hmac_key=config.P4_HMAC)
        p4_args.logger.debug('found name server %s' % name_server)
    except Pyro4.errors.NamingError as err:
        p4_args.logger.debug('...not found, error %s' % err)
        name_server = None

    return name_server


def serve_pyro4(p4_args):
    '''
    start a Pyro4 server that exposes a :class:`,NetemInterface>` instance
    for each interface definition present in the command line arguments

    need to convince Pyro4 to use pickle for serialization; otherwise we
    won't be able to pass emulation objects directly on the client side. yes,
    that is not secure but then this  entire package is not secure to begin
    with
    '''
    configure_pyro4()

    netem_interfaces = []
    if not isinstance(p4_args, _Args):
        raise TypeError('invalid arguments %s' % p4_args)

    p4_args.logger.info('starting simple_netem Pyro4 daemon...')

    if p4_args.name_server:
        name_server = _locate_pyro4_ns(p4_args)

    p4_netem_interface_class = Pyro4.expose(NetemInterface)

    for interface in p4_args.interfaces:
        netem_interfaces.append(
            p4_netem_interface_class(interface=interface[0],
                                     side=interface[1], logger=p4_args.logger))

    with Pyro4.Daemon(host=p4_args.server, port=p4_args.port) as p4_daemon:
        p4_daemon._pyroHmacKey = config.P4_HMAC  # pylint:disable=W0212
        for netem_interface in netem_interfaces:
            uri = p4_daemon.register(
                netem_interface, objectId=netem_interface.interface)
            p4_args.logger.info('Pyro4 URI for interface %s: %s' % (
                netem_interface.interface, uri))

            if name_server:
                p4_args.logger.debug('registering with name server')
                try:
                    name_server.register('bala', uri)
                except Exception as err:
                    p4_args.logger.error(err)

        p4_args.logger.info('simple_netem Pyro4 daemon running...')
        p4_daemon.requestLoop()


def _log_level_to_int(level):
    '''
    custom type casting: string to logging.log_level

    :returns: one of the `logging` log level `const`s
    :rtype: int

    :raises: :exception:`<argparse.ArgumentTypeError>` if input is invalid
    '''
    _level = level.upper()
    if _level not in config.LOG_LEVELS:
        raise argparse.ArgumentTypeError(
            'invalid choice {}, must be one of {}'.format(
                level, ', '.join(config.LOG_LEVELS)))

    return getattr(logging, _level)


class _Args(object):
    # pylint:disable=R0903
    '''
    adapter class creates `object` from `dict` for .attribute access

    each member is an argument for the function(s) called in
    :function:`main` after :function:`get_args` is invoked
    '''

    def __init__(self, args_as_dict):
        '''
        :arg dict args_as_dict: a dictionary
        '''
        # pylint:disable=no-member
        # no-member (pylint E1101): instance has no member. in this case it
        # does because we're messing with the __dict__ member
        self.__dict__ = dict(args_as_dict)
        if self.debug:
            self.log_level = logging.DEBUG

        self.logger = config.get_logger(
            'pyro4_netem',
            log_path=self.log_directory, log_level=self.log_level)


class _AppendTuple(argparse.Action):
    # pylint:disable=R0903
    '''
    custom class that provides an append tuple action

    same as action='append' but will append tuple objects instead of
    `str` objects.
    '''
    @staticmethod
    def ensure_value(namespace, name, value):
        '''
        make sure that the namespace object has a name

        straight from the lib/argparse.py and used in the class definition
        of _AppendAction(Action). not sure exactly why but i'm guessing
        that it is needed to actually append entries to the namespace
        instead of over-writing them
        '''
        if getattr(namespace, name, None) is None:
            setattr(namespace, name, value)
        return getattr(namespace, name)

    def __call__(self, parser, namespace, values, option_string=None):
        '''
        overload :method:`<ArgumentParser.Action.__call__>`

        will place a `tuple` in args.option_string.
        it is expected that the arg values are as follows:

        *    --interface eth0

             in this case, the tuple ('eth0: ``None``) is appended
             to the namespace.interface

        *    --interface eth0:

             this case will be resolved the same as above

        *    --interface eth0:inside

             in this case the tuple ('eth0': 'inside') is appended
             to the namespace.interface

        *    --interface eth0[:[symbolic name]] eth1[:[symbolic name]]

             is treated as a generalization of the above. both interfaces
             are cast to tuples as above and each tuple is
             appended to the namespace.interface

        :raises: :exception:`<argparse.ArgumentTypeError>` if more than one
            ':' is present in the input value
        '''
        items = copy.copy(self.ensure_value(namespace, self.dest, []))

        for value in values:
            value = value.split(':')
            if len(value) < 2:
                items.append((value[0], None))
            elif len(value) == 2:
                items.append((value[0], value[1]))
            else:
                raise argparse.ArgumentTypeError(
                    'invalid format for interface argument'
                    ' %s. can contain at most one : character' % value)

        setattr(namespace, self.dest, items)


def _get_args(description=config.DESCRIPTION, epilog=config.EPILOG):
    '''
    parse the command line arguments

    :arg str description: a description of this script, default ``None``

    :arg str: epilog:
        an epilogue to be appended to the USAGE message, default ``None``
    '''

    parser = argparse.ArgumentParser(
        description=description, epilog=epilog,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-v', '--version', action='version',
        version='simple_netem package {}'.format(config.__version__),
        help='show the version of %(prog)s')
    parser.add_argument(
        '-s', '--server', action='store', default=config.HOST,
        help='the network address of the netem node')
    parser.add_argument(
        '-p', '--port', action='store', type=int, default=config.PORT,
        help='the network port on which the netem server is listening')
    parser.add_argument(
        '-i', '--interface', dest='interfaces', nargs='+', action=_AppendTuple,
        required=True,
        help='a list of network interfaces that will be subject to netem'
        ' in a device_name[:symbolic_name][,device_name[:symbolic_name]]...'
        ' format. at least one device must be specified.'
        ' example: --interfaces=eth1:inside,eth2:outside')
    parser.add_argument(
        '-d', '--debug', action='store_true',
        help='show debug information on the console and in the log files')
    parser.add_argument(
        '-l', '--log-level', dest='log_level', metavar='LEVEL', action='store',
        type=_log_level_to_int, default=config.DEFAULT_LOG_LEVEL,
        help='set the log level to one of {} not case sensitive'.format(
            ', '.join(config.LOG_LEVELS)
        ))
    parser.add_argument(
        '-o', '--log-directory', dest='log_directory', action='store',
        default=config.LOGS, help='the directory to store log files')
    parser.add_argument(
        '-r', '--register-with-name-server', dest='name_server',
        action='store_true',
        help='register the Pyro4 URL(s) with a name server')
    parser.add_argument(
        '-n', '--start-name-server', dest='start_name_server',
        action='store_true',
        help='launch a Pyro4 name server if one cannot be found')

    args_as_dict = vars(parser.parse_args())
    return _Args(args_as_dict)


if __name__ == '__main__':
    main()
