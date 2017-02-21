"""
.. _simple_netem_control:

python wrapper for linux commands that provide basic WAN emulations

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

This module can provide any combination of the WAN conditions (emulations)
listed below but only on a per network interface basis. It does not support
per flow emulations.

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
import os
import warnings
import subprocess
import shlex
import logging

from weakref import WeakSet

import simple_netem_exceptions
import emulations

__version__ = '0.0.1'

DEBUG = 1
if DEBUG:
    loglevel = logging.DEBUG
else:
    loglevel = logging.WARN


# ip and tc command prefixes
netem_del = 'sudo tc qdisc del dev'
netem_add = 'sudo tc qdisc add dev'
netem_stat = 'tc -s qdisc show dev'
iface_ctrl = 'sudo ip link set dev'
iface_stat = 'ip link show dev'
iface_list = 'ip link show'


def get_logger():
    """
    get a logging objects
    """
    logger = logging.getLogger(__name__)
    console = logging.StreamHandler()
    console.setFormatter('%(asctime)s %(name)s %(levelname)-6s: %(message)s')
    console.setLevel(loglevel)
    logger.addHandler(console)
    return logger


def get_etherfaces(xclude_wlan=True, xclude_loopback=True):
    """
    get a list of network interface names from the system

    see `<https://github.com/systemd/systemd/blob/master/src/udev/udev-builtin-net_id.c#L20>`_
    for predicatble interface names

    :param xclude_wlan:
        exclude the wireless interfaces, default True
    :param xclude_loopback:
        exclude the loopback (lo) interfaces (yes, there can be more than one),
        default True
    :returns:
        a dictionary keyed on the etherface system name, each entry contains the
        entry between the <> following the interface name
    :raises:
        NetemNotSupportedException
        NetemInsufficientInterfaces
    """
    etherfaces = dict()
    returncode, output, error = do_this(iface_list)

    if returncode:
        if 'supported' in error:
            raise simple_netem_exceptions.NetemNotSupportedException(
                output, error)
        else:
            raise simple_netem_exceptions.NetemGeneralException(output, error)

    for etherface in output.split('\n'):
        if xclude_wlan and 'wl' in etherface:
            continue
        if xclude_loopback and 'lo' in etherface:
            continue
        if not etherface:
            continue

        etherfaces[''.join(etherface.split(': ')[1:2])] = ''.join(
            etherface.split(': ')[2:3]
        )

    # there may be a '' key, pop it
    etherfaces.pop('', None)

    return etherfaces


def do_this(cmd):
    """
    execute a system command

    :param cmd:
        the command to execute as a string
    :returns:
        a tuple in the format (returncode, stdout, stderr)
    """
    if not 'linux' in sys.platform:
        return (1,
                'cannot execute {}'.format(cmd),
                'not supported on {}'.format(sys.platform))

    do_it = shlex.split(cmd)

    try:
        p = subprocess.Popen(do_it, bufsize=-1, stdout=subprocess.PIPE,
                             stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        talk_back, choked = p.communicate()
    except OSError as err:
        return (1, 'cannot execute {}'.format(cmd), err)
    except ValueError as err:
        return (1, 'invalid command {}'.format(cmd), err)
    except Exception as err:
        return (1, 'unexpected error on command {}'.format(cmd), err)

    return (p.returncode, talk_back, choked)


# pylint:disable=R0923
# pylint:disable=R0902
class NetemInterface(object):
    """
    class wrapper for the network interface to be controlled

    each interface used for network emulation is exposed via an
    instance of this class

    public members
    ---------------

    *   **side:** the relative orientation of the netem interface wrapped in the
        instance. a combination of this and the fqdn associated with the
        control interface of the netem node will uniquely identify each netem
        server instance running.
        it is possible to run more than 2 instances of the netem ctrl module if
        the hardware supports it. the limit is the number of network ports
        (**not the number of ip addresses**) available on the netem node. when
        running more than 2 instances of the netem ctrl server, it is mandatory
        to specify the interface associated with each instance (see **iface**
        below)

    *   **iface:** the system interface name where the instance is running. by
        default (when this member is not specified in the instance constructor)
        the code assumes that:

        *   there are only 2 netem enabled interfaces on the node

        *   the host facing instance is running on eth0

        *   the client facing instance is running on eth1

        the user is warned to **not rely** on this mechanism. there is no
        guarantee that the number of interfaces is limited to 2, or that the
        interface names are valid (on fedora and related distros the interfaces
        are named using a p2p1 convention)

    *   **sudo_pwd:** the sudo password required to execute any active **ip**
        or **tc** commands. defaults to **auto%%lab**

    *   **ctrl_fqdn:** the network address on which the PyroApp is listening

    *   **ctrl_port:** the network port on which the PyroApp is listening

    *   **logger:** the logging object; it is a member because this way it can
        be named based on other class members

    *   **state:** the state of the application that will be returned via the
        heartbeat() : starting|emulating|waiting|blocking|degraded.

        *   starting: the interface object is initializing

        *   emulating: there is an active netem policy on the interface

        *   waiting: the interface is up and running the default policy
            (pfifo_fast)

        *   blocking: the interface is down but not out

        *   degraded: the interface cannot be used. this is the error state. the
            application is running but it cannot be used to emulate the link

    """

    def __init__(self, side, ctrl_fqdn=None, ctrl_port=None, iface=None,
                 logger=None):
        """
        :param side:
            the position of the interface controlled by this instance relative
            to the network

            the value of this parameter is arbritary but from logical
            perspective it maps to either a 'host side' or (one or more)
            'client sides'
        :param iface:
            the system name associated with the interface controlled from this
            instance by the operating system

            this is more or less the 'eth0', 'eth1', etc parameter. it is
            configurable because the 'eth0', 'eth1' approach is just a
            convention (current fedora or centos distros do not use this
            convention anymore).

            if iface is not specified, the constructor will assume that:

            *    the **netem node** has only 2 netem capable interfaces

            *    the interfaces are named using the eth0, eth1, eth2 convention

            *    the host side interface is eth0

            *    the client side interface is eth1

            *    the value of the :param side: contains the string 'host' for
                 the host side instance, and the string 'client' for the client
                 side instance

        :param ctrl_fqdn:
            the address component of the Pyro4 uri

            this paramater is mandatory and used strictly for logging
            purposes

        :param ctrl_port:
            the port component of the Pyro4 uri

            this paramater is mandatory and used strictly for logging
            purposes

        :raises:
            NetemInsufficientInterfaces exception,
            NetemInvalidInterfaceException exception

        :warnings:
            raises a warning if one tries to run more instances than the
            number of available interfaces or if each available interface is
            already controlled by an instance of this class
        """
        self.state = 'starting'
        self.iface_stats = ''
        self.last_error = ''

        if not side:
            raise simple_netem_exceptions.NetemSideException()
        self.side = side

        if not ctrl_fqdn:
            raise simple_netem_exceptions.NetemCtrlFqdnException()
        self.ctrl_fqdn = ctrl_fqdn

        if not ctrl_port:
            raise simple_netem_exceptions.NetemCtrlPortException()
        self.ctrl_port = ctrl_port

        self.iface = self.__iface__(side, iface)
        if logger is None:
            self.logger = get_logger()

        all_ifaces = get_etherfaces()

        # not a multi-homed host, can't run netem
        if len(all_ifaces) < 2:
            self.state = 'error'
            self.iface_stats = all_ifaces
            self.last_error = \
                '''netem node does not have enough interfaces, need at least 2 ethernet
interfaces'''
            raise simple_netem_exceptions.NetemInsufficientInterfaces()

        # bad interface name, do we need to raise or not?
        if self.iface not in all_ifaces.keys():
            self.state = 'error'
            self.iface_stats = all_ifaces
            self.last_error = '''invalid interface specification {}'''.format(
                self.iface
            )
            raise simple_netem_exceptions.NetemInvalidInterface(
                self.iface,
                all_ifaces.keys()
            )

        # we're out of interfaces, bail on this one but don't throw an error
        if len(NetemInterface.instances) > len(all_ifaces.keys()):
            self.state = 'degraded'
            self.iface_stats = all_ifaces
            self.last_error = '''cannot use interface {}, it's already
                                 busy'''.format(self.iface)
            self.logger.error(self.last_error)
            warnings.warn('''cannot use interface {}, it's already
                                 busy'''.format(self.iface))
            return

        # and we're good to go
        # but let's make sure there's no qdisc already running on this thing
        self.del_qdisc_netem()
        self.iface_up()

        self.state = 'waiting'
        self.iface_stats = dict(iface_stat=self.get_iface_state(),
                                netem_stat=self.get_qdisc_netem())
        self.logger.info('''netem control server running on interface {},
                            at {}:{}'''.format(self.iface,
                                               self.ctrl_fqdn,
                                               self.ctrl_port))
        self.logger.debug('''interface state: {}'''.format(
            self.iface_stats['iface_stat']
        ))
        self.logger.debug('''netem state: {}'''.format(
            self.iface_stats['netem_stat']
        ))

    def __iface__(self, side, iface):
        """
        guess the iface member based on the side member
        """
        if not iface:
            if 'host' in side:
                iface = 'eth0'
            if 'client' in side:
                iface = 'eth1'

        return iface

    def __new__(cls, *args, **kwargs):
        """
        keep track of class instances to check against the number of interfaces

        the point of this class is to control an ethernet port. it is possible
        in theory to run more instances of this class than the number of
        ethernet interfaces available on the node but it would create
        confusion as to which instance is currently controlling an interface.

        it is a good idea to only allow one instance per interface

        this method updates a class variable each time a new object is
        initialized. the constructor checks if we are trying to start
        more than one instance per interface by looking at the class variable

        """
        instance = object.__new__(cls, *args, **kwargs)
        if 'instances' not in cls.__dict__:
            cls.instances = WeakSet()
        cls.instances.add(instance)
        return instance

    def heartbeat(self):
        """
        tick-tock method

        :returns:
            the app state
        """
        return self.state

    def diagnose(self):
        """
        more detailed tick-tock method

        :returns:
            a tuple (app state, interface stats, last error on interface)
        """
        return (self.state, self.iface_stats, self.last_error)

    def get_side(self):
        """
        return the relative side of the interface where the instance is
        running

        the side can be arbritrary (it's an __init__() parm but one expects
        a little logic when contructing the instance.
        the is needed to provide distinction on the client side if one
        has a ntem node with more than one uri

        """
        return self.side

    def get_iface_state(self):
        """
        check the link

        this will be exposed via PyroApp and is the equivalent of calling::

            ip link show dev $interface_name

        :returns:
            a tuple with the return code from the subprocess command and either
            the output or the error from said command
        """
        cmd = '{} {}'.format(iface_stat, self.iface)
        return self.__call_do_this__(cmd)

    def __call_do_this__(self, cmd):
        """
        execute the command prepared by the calling method, log what's happening,
        smooch the returns

        :param cmd:
            the command

        :returns:
            a tuple with the system style return code of the command and its
            output

            0, 'this is my stdout' is specific of successful commands
            1, 'this is my stderr' is specific of failed commands
        """
        if self.state not in ['starting', 'emulating', 'waiting', 'blocking']:
            return (1, self.last_error)

        self.logger.debug('''executing {}'''.format(cmd))
        ret, out, error = do_this(cmd, self.sudo_pwd)

        if ret:
            self.logger.error('''command {} returned error {}'''.format(cmd,
                                                                        error))
            self.last_error = error
            return (ret, error)

        self.logger.debug('''returned {}'''.format(out))
        self.last_error = ''
        return (ret, out)

    def get_qdisc_netem(self):
        """
        get the netem stats

        is the equivalent of executing::

            tc -s qdisc show dev $interface_name

        :returns:
            a tuple with the return code from the subprocess command and either
            the output or the error from said command
        """
        cmd = '{} {}'.format(netem_stat, self.iface)
        ret, out = self.__call_do_this__(cmd)
        self.iface_stats = dict(iface_stat=self.get_iface_state(),
                                netem_stat=out)

        return ret, out

    def is_iface_up(self):
        """
        is the network interface up?
        """
        ret, out = self.get_iface_state()

        if 'state UP' in out:
            return True

        return False

    def iface_up(self):
        """
        bring up the interface
        """
        if not self.is_iface_up():
            cmd = '{} {} up'.format(iface_ctrl, self.iface)
            ret, out = self.__call_do_this__(cmd)
        else:
            ret, out = (0, '')

        if self.is_emulating():
            self.state = 'emulating'
        else:
            self.state = 'waiting'

        self.iface_stats = dict(iface_stat=self.get_iface_state(),
                                netem_stat=self.get_qdisc_netem())
        return ret, out

    def iface_down(self):
        """
        bring down the interface
        """
        if self.is_iface_up():
            cmd = '{} {} down'.format(iface_ctrl, self.iface)
            ret, out = self.__call_do_this__(cmd)
        else:
            ret, out = (0, '')

        self.state = 'blocking'
        self.iface_stats = dict(iface_stat=self.get_iface_state(),
                                netem_stat=self.get_qdisc_netem())
        return ret, out

    def is_emulating(self):
        """
        is there an active netem discipline applied
        """
        ret, out = self.get_qdisc_netem()

        if 'netem' in out:
            return True

        return False

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

            this parameter will pre-empt any other loss emulations
            the correlation attribute is deprecated and its use will raise a
            warning

            format: {'percent': numeric_positive_0_100,
                     'correlation': numeric_positive_0_100,}

        :param loss_gemodel:
            netem loss emulation using the Gilbert-Elliot model

            this parameter will pre-empt loss state based emulations; this
            parameter is pre-empted by loss random
            this parameter is not properly supported by some iproute2 versions

            format: {'p': numeric_positive_0_100,
                     'r': numeric_positive_0_100,
                     'one_h': numeric_positive_0_100,
                     'one_k': numeric_positive_0_100,}

        :param loss_state:
            netem loss emulation using a 4 state Markhov model

            this parameter will pre-empted by both random loss emulations and
            Gilbert-Elliot model loss emulations

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
        self.del_qdisc_netem()

        self.logger.debug('''preparing add netem comand''')
        cmd_root = '{} {} root netem'.format(netem_add, self.iface)
        cmd = cmd_root
        self.logger.debug(cmd)

        if isinstance(delay, dict):
            cmd = '{} {}'.format(cmd, emulations.NetemDelay(**delay).delay)
            self.logger.debug(cmd)
        else:
            if delay:
                raise simple_netem_exceptions.NetemConfigException(
                    bad_parm='delay',
                    bad_val=delay,
                    accepts='must be a dictionary'
                )

        if isinstance(reorder, dict):
            # reorder also needs delay
            if not 'delay' in cmd:
                cmd = '{} {}'.format(cmd, emulations.NetemDelay(
                    delay=10, delay_units='msec'
                ).delay)
            cmd = '{} {}'.format(
                cmd, emulations.NetemReorder(**reorder).reorder)
            self.logger.debug(cmd)
        else:
            if reorder:
                raise simple_netem_exceptions.NetemConfigException(
                    bad_parm='reorder',
                    bad_val=reorder,
                    accepts='must be a dictionary'
                )

        if isinstance(corrupt, dict):
            cmd = '{} {}'.format(
                cmd, emulations.NetemCorrupt(**corrupt).corrupt)
            self.logger.debug(cmd)
        else:
            if corrupt:
                raise simple_netem_exceptions.NetemConfigException(
                    bad_parm='corrupt',
                    bad_val=corrupt,
                    accepts='must be a dictionary'
                )

        if isinstance(duplicate, dict):
            cmd = '{} {}'.format(
                cmd, emulations.NetemDuplicate(**duplicate).duplicate)
            self.logger.debug(cmd)
        else:
            if duplicate:
                raise simple_netem_exceptions.NetemConfigException(
                    bad_parm='duplicate',
                    bad_val=duplicate,
                    accepts='must be a dictionary'
                )

        if isinstance(rate, dict):
            cmd = '{} {}'.format(cmd, emulations.NetemRate(**rate).rate)
            self.logger.debug(cmd)
        else:
            if rate:
                raise simple_netem_exceptions.NetemConfigException(
                    bad_parm='rate',
                    bad_val=rate,
                    accepts='must be a dictionary'
                )

        # random loss takes priority over loss state and loss gemodel
        if isinstance(loss_random, dict):
            loss_gemodel = ''
            loss_state = ''
            cmd = '{} {}'.format(
                cmd, emulations.LossRandom(**loss_random).emulation
            )
            self.logger.debug(cmd)
        else:
            if loss_random:
                raise simple_netem_exceptions.NetemConfigException(
                    bad_parm='loss_random',
                    bad_val=loss_random,
                    accepts='must be a dictionary'
                )

        # loss gemodel takes precedence over loss state
        if isinstance(loss_gemodel, dict):
            loss_state = ''
            cmd = '{} {}'.format(
                cmd, emulations.NetemLossGemodel(**loss_gemodel).loss_gemodel
            )
            self.logger.debug(cmd)
        else:
            if loss_gemodel:
                raise simple_netem_exceptions.NetemConfigException(
                    bad_parm='loss_gemodel',
                    bad_val=loss_gemodel,
                    accepts='must be a dictionary'
                )

        if isinstance(loss_state, dict):
            cmd = '{} {}'.format(
                cmd, emulations.NetemLossState(**loss_state).loss_state)
        else:
            if loss_state:
                raise simple_netem_exceptions.NetemConfigException(
                    bad_parm='loss_state',
                    bad_val=loss_state,
                    accepts='must be a dictionary'
                )

        if isinstance(limit, dict):
            # limit only makes sense if other emulations are applied
            if len(cmd) > len(cmd_root):
                cmd = '{} {}'.format(cmd, emulations.NetemLimit(**limit).limit)
                self.logger.debug(cmd)
            else:
                warnings.warn(
                    '''bare limit={} parameter for netem command {}, ignoring'''.format(
                        limit,
                        cmd
                    )
                )
                self.logger.warn(
                    '''bare limit={} parameter for netem command {}, ignoring'''.format(
                        limit,
                        cmd
                    )
                )
                ret, out = 1, \
                    '''bare limit={} parameter for netem command {}, ignoring'''.format(
                        limit,
                        cmd
                    )
                return ret, out
        else:
            if limit:
                raise simple_netem_exceptions.NetemConfigException(
                    bad_parm='limit',
                    bad_val=limit,
                    accepts='must be a dictionary'
                )

        ret, out = self.__call_do_this__(cmd)
        if not ret:
            self.state = 'emulating'

        self.iface_stats = dict(iface_stat=self.get_iface_state(),
                                netem_stat=self.get_qdisc_netem())
        return ret, out
    # pylint:enable=R0912

    def del_qdisc_netem(self):
        """
        we always assume that qdisc is applied on the device root,
        no fancy handles
        do a::
            sudo tc qdisc del dev self.iface root
        """
        if self.is_emulating():
            cmd = '{} {} root'.format(netem_del, self.iface)
            ret, out = self.__call_do_this__(cmd)
        else:
            ret, out = (0, '')

        if not ret:
            self.state = 'waiting'

        self.iface_stats = dict(iface_stat=self.get_iface_state(),
                                netem_stat=self.get_qdisc_netem())
        return ret, out
