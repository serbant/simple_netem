"""
.. _simple_netem_control:

python wrapper for linux commands that provide basic WAN emulation

:module:     simple_netem_control

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

Simple Netem Control
====================

This module contains python classes that expose network (WAN) emulation control
functions on linux hosts

The linux commands exposed by this module are the **tc** command and the **ip**
command.
See
`<http://www.linuxfoundation.org/collaborate/workgroups/networking/netem#Emulating_wide_area_network_delays>`_
for details

Supported WAN Emulations
------------------------

This module can provide any combination of the WAN conditions (emulation)
listed below but only on a per network interface basis. It does not support
per flow emulation.

* packet delay

* packet loss

* packet duplication

* packet corruption

* packet re-ordering

* traffic rate


:Note:

    The code in this file is inherently not portable and can only be executed
    on a Linux host

"""
from __future__ import (
    unicode_literals, print_function, division, absolute_import)


import sys
import warnings
import subprocess
import shlex
import logging

from weakref import WeakSet

import netem_exceptions
import emulation

__version__ = '0.0.1'

DEBUG = 1
if DEBUG:
    LOG_LEVEL = logging.DEBUG
else:
    LOG_LEVEL = logging.WARN


netem_add = 'sudo tc qdisc add dev'


class Command(object):
    '''
    build and expose all the os command strings as static methods

    '''

    @staticmethod
    def add_emulation(device=None, emulation=None):
        '''
        :returns: the os command to add an emulation to a network device
        :rtype: str

        :arg str device: the network device name

        :arg str emulation: the netem emulation(s)
        '''
        cmd = 'sudo tc qdisc add dev'
        if not device or not emulation:
            raise netem_exceptions.CommandError('device', 'emulation')
        return r'{cmd} {device} root netem {emulation}'.format(
            cmd=cmd, device=device, emulation=emulation)

    @staticmethod
    def remove_emulation(device, emulation):
        '''
        :returns: the os command to remove an emulation from a network device
        :rtype: str

        :arg str device: the network device name

        :arg str emulation: the netem emulation(s)

        '''
        cmd = 'sudo tc qdisc del dev'
        if not device or not emulation:
            raise netem_exceptions.CommandError('device', 'emulation')
        return r'{cmd} {device} root netem {emulation}'.format(
            cmd=cmd, device=device, emulation=emulation)

    @staticmethod
    def remove_all_emulations(device):
        '''
        :returns: the command to remove all emulation from a network device

        :arg str device:
        '''
        cmd = r'sudo tc qdisc del dev'
        if not device:
            raise netem_exceptions.CommandError('device')
        return r'{cmd} {device} root netem'.format(cmd=cmd, device=device)

    @staticmethod
    def show_emulations(device):
        '''
        :returns: the os command to show the emulation runing on a device

        :arg str device:
        '''
        cmd = 'tc -s qdisc show dev'
        if not device:
            raise netem_exceptions.CommandError('device')
        return r'{cmd} {device}'.format(cmd=cmd, device=device)

    @staticmethod
    def ifup(device):
        '''
        set a network device in the UP state

        :arg str device:
        '''
        cmd = 'sudo ip link set dev'
        if not device:
            raise netem_exceptions.CommandError('device')
        return r'{cmd} {device} up'.format(cmd=cmd, device=device)

    @staticmethod
    def ifdown(device):
        '''
        set a network device in the DOWN state

        :arg str device:
        '''
        cmd = 'sudo ip link set dev'
        if not device:
            raise netem_exceptions.CommandError('device')
        return r'{cmd} {device} down'.format(cmd=cmd, device=device)

    @staticmethod
    def ifshow(device):
        '''
        show the info for a network device

        :arg str device:
        '''
        cmd = 'ip link show dev'
        if not device:
            raise netem_exceptions.CommandError('device')
        return r'{cmd} {device}'.format(cmd=cmd, device=device)

    @staticmethod
    def iflist():
        '''
        list the network devices on the host
        '''
        cmd = 'ip link show'
        return r'{cmd}'.format(cmd=cmd)


def get_logger():
    """
    get a logging objects
    """
    logger = logging.getLogger(__name__)
    console = logging.StreamHandler()
    console.setFormatter('%(asctime)s %(name)s %(levelname)-6s: %(message)s')
    console.setLevel(LOG_LEVEL)
    logger.addHandler(console)
    return logger


def execute(cmd):
    """
    execute a system command

    :param cmd:
        the command to execute as a string
    :returns:
        a tuple in the format (returncode, stdout, stderr)
    """
    if 'linux' not in sys.platform:
        return (1,
                'cannot execute {}'.format(cmd),
                'not supported on {}'.format(sys.platform))

    try:
        proc = subprocess.Popen(
            shlex.split(cmd), bufsize=-1, stdout=subprocess.PIPE,
            stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = proc.communicate()
    except OSError as err:
        return (1, 'cannot execute {}'.format(cmd), err)
    except ValueError as err:
        return (1, 'invalid command {}'.format(cmd), err)
    except Exception as err:  # pylint:disable=W0703
        return (1, 'unexpected error on command {}'.format(cmd), err)

    return (proc.returncode, output.decode(), error.decode())


class NetemInterface(object):
    """
    class wrapper for the network interface to be controlled

    each interface used for network emulation is exposed via an
    instance of this class

    public members
    ---------------

    *   **state:** the state of the application that will be returned via the
        heartbeat() : starting|emulating|waiting|blocking|degraded.

        *   starting: the interface object is initializing

        *   emulating: there is an active netem policy on the interface

        *   waiting: the interface is up and running the default policy
            (pfifo_fast)

        *   blocking: the interface is down but not out

        *   degraded: the interface cannot be used. this is the error state.
            the application is running but it cannot be used

    """
    class State(object):
        # pylint:disable=R0903
        '''
        keep the possible states in their own class
        '''

        ready = dict(ready='UP, no emulation')
        emulating = dict(emulating='UP, running an emulation')
        blocking = dict(blocking='DOWN, blocking all traffic')

    @staticmethod
    def get_interfaces(xclude_wlan=True, xclude_loopback=True):
        """
        get a list of network interface names from the system

        see `<https://github.com/systemd/systemd/blob/master/src/udev/udev-builtin-net_id.c#L20>`_
        for predictable interface names

        :param xclude_wlan:
            exclude the wireless interfaces, default True
        :param xclude_loopback:
            exclude the loopback (lo) interfaces
            (yes, there can be more than one), default True
        :returns:
            a dictionary keyed on the network interface system name,
            each entry contains the info between the <> following the interface
            name
        :raises:
            NetemNotSupportedException
            NetemInsufficientInterfaces
        """
        interfaces = dict()
        returncode, output, error = execute(Command.iflist())

        if returncode:
            if 'supported' in error:
                raise netem_exceptions.NetemNotSupportedError(
                    output, error)
            else:
                raise netem_exceptions.NetemUnexpectedError(error)

        for etherface in output.split('\n'):
            if xclude_wlan and 'wl' in etherface:
                continue
            if xclude_loopback and 'lo' in etherface:
                continue
            if not etherface:
                continue

            interfaces[''.join(etherface.split(': ')[1:2])] = ''.join(
                etherface.split(': ')[2:3]
            )

        # there may be a '' key, pop it
        interfaces.pop('', None)

        return interfaces

    def __init__(self,  interface=None, side=None, logger=None):
        """
        :param side:
            the position of the interface controlled by this instance relative
            to the network

            the value of this parameter is arbritrary but from logical
            perspective it maps to either a 'host side' or (one or more)
            'client sides'

        :param interface:
            the system name associated with the interface controlled from this
            instance by the operating system

            this is more or less the 'eth0', 'eth1', etc parameter. it is
            configurable because the 'eth0', 'eth1' approach is just a
            convention (current fedora or centos distros do not use this
            convention anymore).

            if interface is not specified, the constructor will assume that:

            *    the **netem node** has only 2 netem capable interfaces

            *    the interfaces are named using the eth0, eth1, eth2 convention

            *    the host side interface is eth0

            *    the client side interface is eth1

            *    the value of the :param side: contains the string 'host' for
                 the host side instance, and the string 'client' for the client
                 side instance

        :raises:
            NetemInsufficientInterfaces exception,
            NetemInvalidInterfaceException exception

        :warnings:
            raises a warning if one tries to run more instances than the
            number of available interfaces or if each available interface is
            already controlled by an instance of this class
        """
        if not interface:
            raise netem_exceptions.NetemUnexpectedError(
                err='must specify a network device')

        self.interface = interface
        self.side = side or self.interface
        self.logger = logger or get_logger()

        interfaces = self.get_interfaces()

        # not a multi-homed host, can't run netem
        if len(interfaces.keys()) < 2:
            raise netem_exceptions.NetemInsufficientInterfaces(
                interfaces=dict(interfaces))

        # bad interface name
        if self.interface not in interfaces.keys():
            raise netem_exceptions.NetemInvalidInterface(
                self.interface, interfaces.keys())

        # and we're good to go
        # but let's make sure there's no qdisc already running on this thing
        self.remove_emulations()
        self.set_interface_up()

        self.state = self.State.ready

        self.logger.info(
            'netem control server running for %s on %s' % (self.side,
                                                           self.interface))

    def __new__(cls, interface, side=None, *args, **kwargs):
        """
        there are some restrictions on how instances of the
        :classL`<NetemInterface>` are constructed, namely:

        *    the interface argument value cannot be reused. had that been
             allowed, it would be possible to have multiple (and multiple
             remote) instances controlling the same network device.

             an extreme case of such a situation would be one instance setting
             the device in the UP state, and another instance setting the
             device in the DOWN state which is really not a good idea.

             it is possible to keep track of the device states and prevent
             such conflicts but it is much simpler (KISS) to just not allow
             more than one instance per network device.

             this also makes it easier to identify the instance(s) for
             remote access by enforcing a logical "unique" identifier for
             each instance

        *    the side member is intended to provide an easier way to describe
             which instance controls which network device. it is sometimes
             easier to just say 'i want to delay traffic on the host side'
             instead of remembering that the network device controlling
             traffic on the host side is enp2s0.

             when not specified, the side member is initialized with the value
             of the interface argument and the restraint at the previous
             bullet point will handle this restraint. but otherwise one must
             make sure that the side member respects the same unique
             constraint as the interface member

        this method updates a class variable each time a new object is
        initialized. it will raise an exception if either the interface arg or
        the side argument are present in previously defined instances.

        :arg str interface: the name of the network device

        :arg str side:
            the side (symbolic) name by which one identifies the new instance

        :raises:

            :exceptions:`<netem_exceptions.NetemInterfaceBusyError>` when the
            interface constraint kick in

            :exceptions:`<netem_exceptions.NetemSideAlreadyDefinedError>` when
            the side constraint kicks in

        """
        instance = object.__new__(cls, *args, **kwargs)

        # first make sure the class variable exists
        if 'instances' not in cls.__dict__:
            cls.instances = WeakSet()

        # look for instances that are already using the interface and/or side
        # args but only if this is not the first instance
        if len(cls.instances):
            if interface in [instance.interface for instance in cls.instances]:
                raise netem_exceptions.NetemInterfaceBusyError(interface)
            if side in [instance.side for instance in cls.instances]:
                raise netem_exceptions.NetemSideAlreadyDefinedError(side)

        cls.instances.add(instance)
        return instance

    @property
    def info(self):
        '''
        :returns: a `dict` with the full information available for this
            netem control instance
        '''
        return dict(side=self.side,
                    device=self.interface,
                    server_state=self.state,
                    device_state=self.interface_info,
                    active_emulations=self.emulation_info)

    @property
    def interface_info(self):
        """
        :returns:
            the output from::

                ip link show dev $device_name
        """
        return self.__execute__(Command.ifshow(self.interface))

    def __execute__(self, cmd):
        """
        execute the command prepared by the calling method, log teh results
        smooch the returns

        :param cmd:
            the command

        :returns:
            the output of the command as returned by the operating system

        :raises:
            :exception:`<netem_exceptions.NetemCommandError>`
        """
        self.logger.debug('executing %s' % cmd)
        ret, out, error = execute(cmd)
        if ret:
            self.logger.error('returned error %s' % error)
            raise netem_exceptions.NetemCommandError(cmd, error)

        self.logger.debug('ok, returned %s' % out)
        return out

    @property
    def emulation_info(self):
        """
        get the netem stats


        :returns:
            the output from executing::

                tc -s qdisc show dev $interface_name

        """
        return self.__execute__(Command.show_emulations(self.interface))

    @property
    def is_interface_up(self):
        """
        is the network interface up?
        """
        if 'state UP' in self.interface_info:
            return True

        return False

    def set_interface_up(self):
        """
        bring up the interface
        """
        if not self.is_interface_up:
            self.__execute__(Command.ifup(self.interface))

        self.logger.info('interface state: %s' % self.interface_info)

    def set_interface_down(self):
        """
        bring down the interface
        """
        if self.is_interface_up:
            self.__execute__(Command.ifdown(self.interface))

        self.state = self.State.blocking
        self.logger.info('interface state: %s' % self.interface_info)

    @property
    def is_emulating(self):
        """
        is there an active netem discipline applied
        """
        if 'netem' in self.emulation_info:
            return True

        return False

    def add_emulations(self, *emulations):
        '''
        apply one or more netem disciplines (emulation) to the network
        device controlled by this instance

        :arg *default_emulations:
            use the specified emulation with the default arguments present
            in the emulation classes

        :arg **custom_emulations:
            use emulation with fully (or partially) defined arguments

        obviously, a syntax error is raised if there are conflicts between
        *default_emulations and **emulation
        '''
        if not emulations:
            self.logger.warning(
                'no emulation arguments present, aborting command')

        # *args is a tuple, we want a list because it's meaner
        emulations = list(emulations)

        for emulation_ in emulations:
            if not isinstance(emulation_, emulation.Emulation):
                raise TypeError()
            if 'emulation' in type(emulation_).__name__.lower():
                raise TypeError('must not use emulation.Emulation directly')

        emulation.Emulation.has_no_duplicates(emulations=emulations)

        if emulation.Emulation.reorder_without_delay(emulations):
            emulations.append(emulation.Delay())

    # pylint R0912: too many branches
    # pylint:disable=R0912

    def add_qdisc_netem(self, limit='', delay='', reorder='', corrupt='',
                        duplicate='', rate='', loss_random='', loss_state='',
                        loss_gemodel=''):
        """
        apply a netem configuration to the qdisc discipline on this interface

        all the parameters follow these rules:

        *    if it's not a dictionary, don't use this param
        *    if it's an empty dictionary, use the defaults from the matching
             Netem*() classes
        *    if it's a non-empty dictionary, use it as documented

        :param limit:
            limit netem emulation(s) to $packets, type dictionary;
            the number of packets in flight that are subject to the netem
            configuration

            this parameter is irelevant on its own: without any other netem
            directives what is it that you are limiting the number of packets
            to?

            this parameter will be applied by the tc qdisc netem command by
            default as 'limit 1000'; the parameter should be used if the 1000
            value is undesirable

            format: {'limit': positive_integer_value}

        :param delay:
            netem delay emulation, type dictionary

            format: {'delay': numeric_positive, # delay
                     'delay_units': 'msec|msecs|usec|usecs|sec|secs', # time units
                     'jitter': numeric_positive, # jitter
                     'correlation': numeric_positive_0_100, # correlation percent
                     'distribution': 'normal|pareto|paretonormal|uniform',}

        :param reorder:
            netem reorder ermulation, type dictionary

            this parameter cannot be applied without applying a delay as well
            if a delay parameter is not already present, a
            delay={delay:10,delay_units='msec'} is automatically applied

            format: {'percent': numeric_positive_0_100,
                     'correlation': numeric_positive_0_100,
                     'gap': positive_integer}

        :param corrupt:
            netem corrupt emulation

            format: {'percent': numeric_positive_0_100,
                     'correlation': numeric_positive_0_100,}

        :param duplicate:
            netem duplicate emulation

            format: {'percent': numeric_positive_0_100,
                     'correlation': numeric_positive_0_100,}

        :param rate:
            netem rate control emulation

            note that we are not supporting PACKETOVERHEAD, CELLSIZE, and
            CELLOVERHEAD

            format: {'rate': positive_numeric,
                     'units': 'bit|bps|kbit|kbps|mbit|mbps|gbit|gbps'}

        :param loss_random:
            netem random loss emulation

            this parameter will pre-empt any other loss emulation
            the correlation attribute is deprecated and its use will raise a
            warning

            format: {'percent': numeric_positive_0_100,
                     'correlation': numeric_positive_0_100,}

        :param loss_gemodel:
            netem loss emulation using the Gilbert-Elliot model

            this parameter will pre-empt loss state based emulation; this
            parameter is pre-empted by loss random
            this parameter is not properly supported by some iproute2 versions

            format: {'p': numeric_positive_0_100,
                     'r': numeric_positive_0_100,
                     'one_h': numeric_positive_0_100,
                     'one_k': numeric_positive_0_100,}

        :param loss_state:
            netem loss emulation using a 4 state Markhov model

            this parameter will pre-empted by both random loss emulation and
            Gilbert-Elliot model loss emulation

            format: {'p13': numeric_positive_0_100,
                     'p31': numeric_positive_0_100,
                     'p32': numeric_positive_0_100,
                     'p23': numeric_positive_0_100,
                     'p14': numeric_positive_0_100,}

        :returns:
            a tuple (0|1, status_message)

            0: emulation applied succesfully, status_message: stdout from the
            tc command execution if any

            1: emulation command failed, status_message: stderr from the tc
            command execution if any

        :raises:
            NetemConfig Exception

        """

        # first, remove any previous netem configuration
        self.remove_emulations()

        self.logger.debug('''preparing add netem comand''')
        cmd_root = '{} {} root netem'.format(netem_add, self.interface)
        cmd = cmd_root
        self.logger.debug(cmd)

        if isinstance(delay, dict):
            cmd = '{} {}'.format(cmd, emulation.Delay(**delay).emulation)
            self.logger.debug(cmd)
        else:
            if delay:
                raise netem_exceptions.NetemConfigException(
                    bad_parm='delay',
                    bad_val=delay,
                    accepts='must be a dictionary'
                )

        if isinstance(reorder, dict):
            # reorder also needs delay
            if 'delay' not in cmd:
                cmd = '{} {}'.format(cmd, emulation.Delay(
                    delay=10).emulation)
            cmd = '{} {}'.format(
                cmd, emulation.Reorder(**reorder).emulation)
            self.logger.debug(cmd)
        else:
            if reorder:
                raise netem_exceptions.NetemConfigException(
                    bad_parm='reorder',
                    bad_val=reorder,
                    accepts='must be a dictionary'
                )

        if isinstance(corrupt, dict):
            cmd = '{} {}'.format(
                cmd, emulation.Corrupt(**corrupt).emulation)
            self.logger.debug(cmd)
        else:
            if corrupt:
                raise netem_exceptions.NetemConfigException(
                    bad_parm='corrupt',
                    bad_val=corrupt,
                    accepts='must be a dictionary'
                )

        if isinstance(duplicate, dict):
            cmd = '{} {}'.format(
                cmd, emulation.Duplicate(**duplicate).emulation)
            self.logger.debug(cmd)
        else:
            if duplicate:
                raise netem_exceptions.NetemConfigException(
                    bad_parm='duplicate',
                    bad_val=duplicate,
                    accepts='must be a dictionary'
                )

        if isinstance(rate, dict):
            cmd = '{} {}'.format(cmd, emulation.Rate(**rate).emulation)
            self.logger.debug(cmd)
        else:
            if rate:
                raise netem_exceptions.NetemConfigException(
                    bad_parm='rate',
                    bad_val=rate,
                    accepts='must be a dictionary'
                )

        # random loss takes priority over loss state and loss gemodel
        if isinstance(loss_random, dict):
            loss_gemodel = ''
            loss_state = ''
            cmd = '{} {}'.format(
                cmd, emulation.LossRandom(**loss_random).emulation
            )
            self.logger.debug(cmd)
        else:
            if loss_random:
                raise netem_exceptions.NetemConfigException(
                    bad_parm='loss_random',
                    bad_val=loss_random,
                    accepts='must be a dictionary'
                )

        # loss gemodel takes precedence over loss state
        if isinstance(loss_gemodel, dict):
            loss_state = ''
            cmd = '{} {}'.format(
                cmd, emulation.LossGemodel(**loss_gemodel).emulation
            )
            self.logger.debug(cmd)
        else:
            if loss_gemodel:
                raise netem_exceptions.NetemConfigException(
                    bad_parm='loss_gemodel',
                    bad_val=loss_gemodel,
                    accepts='must be a dictionary'
                )

        if isinstance(loss_state, dict):
            cmd = '{} {}'.format(
                cmd, emulation.LossState(**loss_state).emulation)
        else:
            if loss_state:
                raise netem_exceptions.NetemConfigException(
                    bad_parm='loss_state',
                    bad_val=loss_state,
                    accepts='must be a dictionary'
                )

        if isinstance(limit, dict):
            # limit only makes sense if other emulation are applied
            if len(cmd) > len(cmd_root):
                cmd = '{} {}'.format(cmd, emulation.Limit(**limit).emulation)
                self.logger.debug(cmd)
            else:
                msg = 'bare limit=%s emulation, ignoring' % limit
                warnings.warn(msg)
                self.logger.warning(msg)
                return 1, msg
        else:
            if limit:
                raise netem_exceptions.NetemConfigException(
                    bad_parm='limit',
                    bad_val=limit,
                    accepts='must be a dictionary'
                )

        ret, out = self.__execute__(cmd)
        if not ret:
            self.state = 'emulating'

        self.iface_stats = dict(iface_stat=self.interface_info(),
                                netem_stat=self.emulation_info())
        return ret, out

    def remove_emulations(self):
        """
        we always assume that qdisc is applied on the device root,
        no fancy handles
        do a::
            sudo tc qdisc del dev self.iface root
        """
        if self.is_emulating:
            self.__execute__(Command.remove_all_emulations(self.interface))

        self.state = self.State.ready
        self.logger.info('no emulation for %s on %s' % (self.side,
                                                        self.interface))

    def remove_emulation(self):
        '''
        remove a single emulation

        :raises: :exception:`<NotImplementedError>`
        '''
        raise NotImplementedError(
            'please use self.remove_all_emulations() and then re-apply'
            ' any desired emulation')
