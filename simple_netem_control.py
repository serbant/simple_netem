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
import collections

from weakref import WeakSet

import simple_netem_exceptions

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
            raise simple_netem_exceptions.NetemNotSupportedException(output, error)
        else:
            raise simple_netem_exceptions.NetemGeneralException(output, error)

    for etherface in output.split('\n'):
        if xclude_wlan and 'wlan' in etherface:
            continue
        if xclude_loopback and 'lo' in etherface:
            continue
        if not etherface:
            continue

        etherfaces[''.join(etherface.split(': ')[1:2])] = ''.join(
                                                    etherface.split(': ')[2:3]
                                                    )

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
    _defaults = collections.namedtuple('_defaults', ['IP', 'PORT', 'SIDE'])
    DEFAULTS = _defaults(IP='127.0.0.1',PORT='44666',SIDE='client')
        
    def __init__(self, side=DEFAULTS.SIDE, ctrl_fqdn=DEFAULTS.IP, 
                 ctrl_port=DEFAULTS.PORT, iface=None, logger=None):
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

        self.side = side
        #TODO: the validation here needs to make sure that there are no
        # duplicates across instances. add this check under __new__()

        self.ctrl_fqdn = ctrl_fqdn

        self.ctrl_port = ctrl_port
        #TODO: this should be checked to see if it casts to a valid port:
        # must be an int, must be gt 1024 (privileged ports), must be less than
        # 65535

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
        
        #TODO: this needs to go away. it is so out of date it hurts
        """
        if not iface:
            if 'host' in side:
                iface = 'eth0'
            if 'client' in side:
                iface = 'eth1'

        return iface

    def  __new__(cls, *args, **kwargs):
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
        ret, out, error = do_this(cmd)

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
            cmd = '{} {}'.format(cmd, NetemDelay(**delay).delay)
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
                cmd = '{} {}'.format(cmd, NetemDelay(
                                        delay=10, delay_units='msec'
                                        ).delay)
            cmd = '{} {}'.format(cmd, NetemReorder(**reorder).reorder)
            self.logger.debug(cmd)
        else:
            if reorder:
                raise simple_netem_exceptions.NetemConfigException(
                                            bad_parm='reorder',
                                            bad_val=reorder,
                                            accepts='must be a dictionary'
                                            )

        if isinstance(corrupt, dict):
            cmd = '{} {}'.format(cmd, NetemCorrupt(**corrupt).corrupt)
            self.logger.debug(cmd)
        else:
            if corrupt:
                raise simple_netem_exceptions.NetemConfigException(
                                            bad_parm='corrupt',
                                            bad_val=corrupt,
                                            accepts='must be a dictionary'
                                            )

        if isinstance(duplicate, dict):
            cmd = '{} {}'.format(cmd, NetemDuplicate(**duplicate).duplicate)
            self.logger.debug(cmd)
        else:
            if duplicate:
                raise simple_netem_exceptions.NetemConfigException(
                                            bad_parm='duplicate',
                                            bad_val=duplicate,
                                            accepts='must be a dictionary'
                                            )

        if isinstance(rate, dict):
            cmd = '{} {}'.format(cmd, NetemRate(**rate).rate)
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
                                cmd, NetemLossRandom(**loss_random).loss_random
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
                            cmd, NetemLossGemodel(**loss_gemodel).loss_gemodel
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
            cmd = '{} {}'.format(cmd, NetemLossState(**loss_state).loss_state)
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
                cmd = '{} {}'.format(cmd, NetemLimit(**limit).limit)
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

# pylint:enable=R0923
# pylint:enable=R0902

# pylint R0903 too few public methods
# pylint:disable=R0903
class NetemLossRandom(object):
    """
    class wrapper for netem packet loss in random mode

    extract from the netem man page
    ---------------------------------

    LOSS := loss { **random PERCENT [ CORRELATION ]**  |
                      state p13 [ p31 [ p32 [ p23 [ p14]]]] |
                      gemodel p [ r [ 1-h [ 1-k ]]] }  [ ecn ]

    loss random
       adds an independent loss probability to the packets outgoing from the chosen  network  interface.  It  is
       also possible to add a correlation, but this option is now deprecated due to the noticed bad behavior.

    ecn
       can  be used optionally to mark packets instead of dropping them. A loss model has to be used for this to
       be enabled.

    """
    def __init__(self, percent=1, correlation=0):
        """
        :param percent:
            precentage of packets to lose, default=1 (%), must be integer
        :param correlation:
            chances (approximate) that a packet lost will cause the next packet
            in the sequence to be lost
        :raises:
            NetemConfigException if passed invalid parameters
            DeprecationWarning if correlation is present
        """
        if correlation:
            warnings.warn('using correlation for random loss is deprecated',
                          DeprecationWarning)

        for v in ['percent', 'correlation', ]:
            if eval(v) and not isinstance(eval(v), (int, long, float)) or \
                not 0 <= eval(v) <= 100:
                raise simple_netem_exceptions.NetemConfigException(
                            bad_parm=v,
                            bad_val=eval(v),
                            accepts='must be numeric and between 0 and 100'
                            )

        if correlation:
            correlation = ' {}%'.format(str(correlation))
        else:
            correlation = ''
        self.loss_random = 'loss random {}%{}'.format(str(percent),
                                                                 correlation)


class NetemLossState(object):
    """
    class wrapper for netem packet loss using a 4-state Markov model

    extract from the netem man page
    ---------------------------------

    LOSS := loss {  random PERCENT [ CORRELATION ]  |
                    **state p13 [ p31 [ p32 [ p23 [ p14]]]]** |
                    gemodel p [ r [ 1-h [ 1-k ]]] }  [ ecn ]

    loss state
       adds  packet  losses  according to the 4-state Markov using the
       transition probabilities as input parameters. The parameter p13 is
       mandatory and if used alone corresponds to the Bernoulli model.  The
       optional parameters allows to extend the model to 2-state (p31),
       3-state (p23 and p32) and 4-state (p14).  State 1 corresponds to good
       reception, State 4 to independent losses, State 3 to burst losses and
       State 2 to good reception within a burst.

    ecn
       can  be used optionally to mark packets instead of dropping them. A loss
       model has to be used for this to be enabled.

    model details
    --------------

    the 4-state markvoh model has (duh) 4 possible states:

    *    'good reception' is a 0% loss state that can transition to 'burst loss'
         or to 'single loss'

    *    'burst loss" is a 100% loss state that can transition to either 'good
         reception' or 'good burst reception'. specific and important is that
         in this state, there are no single packet losses

    *    'good burst reception' is a 0% loss state that can only transition to
         'burst loss' and back

    *    'independent loss' is a 100% loss state that can only have 1 event
         (1 lost packet). this state can only transition to the 'good reception'
         state

    defaults
    ---------

    **as implemented by this class**

    *    p13: 10%; chance of getting from 'good' to '100% burst loss'

    *    p31: 70%; chance of getting from '100% burst loss' to 'good'

    *    p23: 10%; chance of getting from 'good burst' to '100% burst loss'

    *    p32: 10%; chance of getting from '100% burst loss' to 'good burst'

    *    p41: 1%; chance of isolated packet drops while in 'good'

    notes:
    -------

    see the discussion about updating iproute2 to correct the problems listed
    below.

    as of 3.13.0-35-generic #62-Ubuntu SMP, this netem discipline is
    reported as a netem loss gemodel discipline.
    when all 5 p parms are fed into netem, there will be an exception related to
    an l parm.
    the tc -s command will report netem loss state as netem loss gemodel,
    however when using the same values for the first 4 parms, the stats are
    different between loss state and loss gemodel.

    as a general rule of thumb:

    *    p13 is mandatory, signifies the probability of the system
         transitioning from the 'good reception' state to a 'burst loss' state
         (all the packets are lost), and puts the system in this configuration
         if used alone::

            autolab@netem-z97proto:~$ sudo tc qdisc add dev eth1 root netem loss state 10
            autolab@netem-z97proto:~$ tc -s qdisc show dev eth1
            qdisc netem 801c: root refcnt 2 limit 1000 loss state p13 10% p31 90% p32 0% p23 100% p14 0%
             Sent 0 bytes 0 pkt (dropped 0, overlimits 0 requeues 0)
             backlog 0b 0p requeues 0
            autolab@netem-z97proto:~$

         note that formally this doesn't match the documentation; the system
         shows 2 states instead of a single state with independent losses.
         this configuration states:
         **there is a 10% chance of the system transitioning in a 'loss'
         state and a 90% chance of the system transitioning back to a 'good
         reception' state.
         while in the 'loss' state, there is 100% chance of packet loss.
         while in the 'good' state, there is 0% chance of packet loss**
         which is a 2-state model with fully dependent losses in the 'loss'
         state, not a 1-state model with independent losses

    *    p31 is the probability transitioning from a 'burst loss' state to a
         'good reception' state

    *    p23 and p32 describe a second 2-state Markhov chain with a 'good
         reception in burst" state and a 'loss in burst' state. there is no
         difference between the 'loss' state and the 'loss in burst' state.
         the difference between 'good reception' and 'good reception in burst'
         is that 'good reception' can be interrupted by both burst losses and
         isolated losses (see p14), while 'good reception burst' can only be
         interrupted by burst losses

    *    p14 is the probability of single packet losses while in in 'good
         reception' state. in other words there 100% chance that a lost packet
         is followed by a received packet (a transmission)

    """
    def __init__(self, p_13=10, p_31=70, p_23=10, p_32=10, p_14=1):
        """
        :param p13:
            is mandatory, numeric between 0 and 100, default 10

        :param p31:
            numeruc between 0 and 100, default 70

        :param p23:
            numeruc between 0 and 100, default 10

        :param p32:
             numeruc between 0 and 100, default 10

        :param p14:
            numeruc between 0 and 100, default 1

        :raises:
            NetemConfigException
        """
        if not p_13:
            # cannot be 0
            raise simple_netem_exceptions.NetemConfigException(
                                    bad_parm='p_13',
                                    bad_val=p_13,
                                    accepts='is mandatory'
                                    )

        for v in ['p_13', 'p_31', 'p_23', 'p_32', 'p_14', ]:
            if eval(v) and not \
               isinstance(eval(v), (int, long, float)) or \
               not 0 <= eval(v) <= 100:
                raise simple_netem_exceptions.NetemConfigException(
                            bad_parm=v,
                            bad_val=eval(v),
                            accepts='must be numeric and between 0 and 100'
                            )

        p_31 = ' {}%'.format(str(p_31)) or None
        p_23 = ' {}%'.format(str(p_23)) or None
        p_32 = ' {}%'.format(str(p_32)) or None
        p_14 = ' {}%'.format(str(p_14)) or None
        self.loss_state = 'loss state {}%{}{}{}{}'.format(str(p_13), p_31,
                                                          p_23, p_32, p_14)


class NetemLossGemodel(object):
    """
    class wrapper for netem packet loss using a Gilbert-Elliot loss model

    extract from the netem man page
    ---------------------------------

    LOSS := loss {  random PERCENT [ CORRELATION ]  |
                    state p13 [ p31 [ p32 [ p23 [ p14]]]] |
                    **gemodel p [ r [ 1-h [ 1-k ]]]** }  [ ecn ]

    loss gemodel
       adds  packet  losses  according  to  the  Gilbert-Elliot loss model or
       its special cases (Gilbert, Simple Gilbert and Bernoulli). To use the
       Bernoulli model, the only needed parameter is p while the others  will
       be  set  to the default values r=1-p, 1-h=1 and 1-k=0. The parameters
       needed for the Simple Gilbert model are two (p and r), while three
       parameters (p, r, 1-h) are needed for the Gilbert model and  four
       (p,  r, 1-h  and 1-k) are needed for the Gilbert-Elliot model.
       As known, p and r are the transition probabilities between the bad and
       the good states, 1-h is the loss probability in the bad state and
       1-k  is  the  loss probability in the good state.


    ecn
       can  be used optionally to mark packets instead of dropping them. A loss
       model has to be used for this to be enabled.

    defaults
    ----------

    **as implemented by this class**

    *    p=10 (percent)

    *    r=90 (percent)

    *    1-h=50 (percent)

    *    1-k=1 (percent)

    as a general rule of thumb
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    *    **p** is the probability of transitioning from the 'good reception'
         state to the 'bad/burst reception' state

    *    **r** is the probability of transitioning from the 'bad reception'
         state tothe 'good reception' state

    *    **1-h** is the loss probability in the 'bad/burst reception' state

    *    **1-k** is the loss probability in the 'good reception' state

    to implement the loss models described in the documentation:

    *    Bernoulli model or independent loss model: p=0 (there is no chance of
         transitioning in a burst state), r=100 (there is a 100% chance of
         transitioning to the good state), 1-h=0, 1-k=$desired_loss_percent

    *    Simple Gilbert model: p=$desired_probability_of_bad_percent,
         r=$desired_probability_of_good_percent, 1-h=1(00)% meaning all the
         bad packets are lost, 1-k=0 meaning no loss when the system is in the
         good state

    *    Gilbert model: p=$desired_probability_of_bad_percent,
         r=$desired_probability_of_good_percent,
         1-h=$desired_lost_packets_percent_bad_state, 1-k=0 meaning no loss
         when the system is in the good state

    *    Gilbert-Elliot model: p=$desired_probability_of_bad_percent,
         r=$desired_probability_of_good_percent,
         1-h=$desired_lost_packets_percent_bad_state,
         1-k=$desired_lost_packets_percent_good_state
    """
    # pylint:disable=C0103
    def __init__(self, p=10, r=90, one_h=50, one_k=1):
        """
        :param p:
            probability of transitioning from good to bad in percentage points,
            must be numeric and positive
        :param r:
            probability of transitioning from bad to good in percentage points,
            must be numeric and positive
        :param one_h:
            probability of a packet being lost when in bad/burst state in
            percentage points, must be numeric and positive
        :param one_k:
            probability of a packet being lost when in good state
        :raises:
            NetemConfigException if passed invalid parameters
        """
        if not p:
            raise simple_netem_exceptions.NetemConfigException(
                                    bad_parm='p',
                                    bad_val=p,
                                    accepts='is mandatory'
                                    )

        for v in ['p', 'r', 'one_h', 'one_k', ]:
            if eval(v) and not \
               isinstance(eval(v), (int, long, float)) or \
               not 0 <= eval(v) <= 100:
                raise simple_netem_exceptions.NetemConfigException(
                            bad_parm=v,
                            bad_val=eval(v),
                            accepts='must be numeric and between 0 and 100'
                            )

        one_k = ' {}%'.format(str(one_k)) or None
        one_h = ' {}%'.format(str(one_h)) or None
        r = ' {}%'.format(str(r)) or None
        self.loss_gemodel = 'loss gemodel {}%{}{}{}'.format(str(p), r,
                                                            one_h, one_k)
    # pylint:enable=C0103


class NetemRate(object):
    """
    class wrapper for netem packet rate control

    extract from the netem man page
    ---------------------------------

    RATE := rate RATE [ PACKETOVERHEAD [ CELLSIZE [ CELLOVERHEAD ]]]]

    rate

        delay packets based on packet size and is a replacement for TBF.  Rate
        can be specified in  common  units (e.g.  100kbit).
        Optional PACKETOVERHEAD (in bytes) specify an per packet overhead and
        can be negative. A positive value can be used to simulate additional
        link layer headers. A negative value  can  be  used  to artificial
        strip the Ethernet header (e.g. -14) and/or simulate a link layer header
        compression scheme.
        The third parameter - an unsigned value - specify the cellsize.
        Cellsize can be  used  to  simulate  link layer  schemes.
        ATM  for  example  has  an payload cellsize of 48 bytes and 5 byte per
        cell header. If a packet is 50 byte then ATM must use two cells:
        2 * 48 bytes payload including 2 *  5  byte  header,  thus consume 106
        byte on the wire.
        The last optional value CELLOVERHEAD can be used to specify per cell
        overhead - for our ATM example 5.  CELLOVERHEAD can be negative, but
        use negative values with caution.

        Note that rate throttling is limited by several factors: the kernel
        clock  granularity  avoid  a  perfect shaping  at  a  specific  level.
        This will show up in an artificial packet compression (bursts). Another
        influence factor are network adapter buffers which can also add
        artificial delay.

    rate can be specified in mbit, kbit, gbit, ot bit (bps) (default for the tc
    netem command)

    this class will actually use mbit as the default rate unit

    this class does not provide access to the optional parameters

    """
    valid_units = ['bit', 'bps', 'kbit', 'kbps', 'mbit', 'mbps', 'gbit',
                   'gbps', ]

    def __init__(self, rate=1, units='mbit'):
        """
        :param rate:
        :param units:
        :raises:
            NetemConfigException if passed invalid parameters
        """
        if not isinstance(rate, (int, long, float)):
            raise simple_netem_exceptions.NetemConfigException(
                                    bad_parm='rate',
                                    bad_val=rate,
                                    accepts='must be numeric'
                                    )

        if rate <= 0:
            raise simple_netem_exceptions.NetemConfigException(
                                    bad_parm='rate',
                                    bad_val=rate,
                                    accepts='must be greater than 0'
                                    )

        if units not in self.valid_units:
            raise simple_netem_exceptions.NetemConfigException(
                                    bad_parm='units',
                                    bad_val=units,
                                    accepts=self.valid_units
                                    )

        self.rate = 'rate {}{}'.format(str(rate), units)


class NetemReorder(object):
    """
    class wrapper for netem packet reordering

    extract from the netem man page
    ---------------------------------

    REORDERING := reorder PERCENT [ CORRELATION ] [ gap DISTANCE ]

    reorder::

       to use reordering, a delay option must be specified. There are two ways  to  use  this  option  (assuming
       'delay 10ms' in the options list).

       reorder 25% 50% gap 5
       in  this first example, the first 4 (gap - 1) packets are delayed by 10ms and subsequent packets are sent
       immediately with a probability of 0.25 (with correlation of 50% ) or delayed with a probability of  0.75.
       After  a  packet  is  reordered,  the process restarts i.e. the next 4 packets are delayed and subsequent
       packets are sent immediately or delayed based on reordering probability. To cause  a  repeatable  pattern
       where every 5th packet is reordered reliably, a reorder probability of 100% can be used.

       reorder 25% 50%
       in this second example 25% of packets are sent immediately (with correlation of 50%) while the others are
       delayed by 10 ms.


    """
    def __init__(self, percent=1, correlation=10, gap=0):
        """
        :param percent:
            percentage of packets to reorder, optional, default 1 (in %), must
            be an integer
        :param correlation:
            more or less that chance that 2 packets in a row will be reordered,
            optional, default 10 (in %), must be an integer
        :param gap:
            the distance between packet sequences subject to reordering,
            optional, default None
            (the entire sequence is subject to reordering), must be an integer
        :raises:
            NetemConfigException if passed invalid parameters
        """
        if not percent:
            raise simple_netem_exceptions.NetemConfigException(
                                                bad_parm='reorder percent',
                                                bad_val=percent,
                                                accepted='must be specified'
                                                )

        for v in ['percent', 'correlation', ]:
            if eval(v) and not isinstance(eval(v), (int, long, float)) or \
               not 0 <= eval(v) <= 100:
                raise simple_netem_exceptions.NetemConfigException(
                                    bad_parm=v,
                                    bad_val=eval(v),
                                    accepts='must be numeric and between 0 and 100'
                                    )

        if gap and not isinstance(gap, (int, long)) or gap < 0:
            raise simple_netem_exceptions.NetemConfigException(
                                    bad_parm='gap',
                                    bad_val=gap,
                                    accepts='must be a positive integer'
                                    )

        gap = ' gap {}'.format(str(gap)) or None
        correlation = ' {}%'.format(str(correlation)) or None
        self.reorder = 'reorder {}%{}{}'.format(str(percent), correlation, gap)


class NetemDuplicate(object):
    """
    class wrapper for netem packet duplication

    DUPLICATION
    ~~~~~~~~~~~~
    ::

        DUPLICATION := duplicate PERCENT [ CORRELATION ]]

        duplicate
           using this option the chosen percent of packets is duplicated before
           queuing them. It is also possible to add a correlation through the
           proper parameter.

    there is a bug in the output of duplicate: tc -s does not return the
    correlation
    """
    def __init__(self, percent=1, correlation=0):
        """
        :param percent:
            duplicate percent of packets, must be an integer, optional,
            default 1
        :param correlation:
            duplication correlation, must be an integer, optional, default 10
        :raises:
            NetemConfigException if passed invalid parameters
        """
        for v in ['percent', 'correlation', ]:
            if eval(v) and not isinstance(eval(v), (int, long, float)) or \
               not 0 <= eval(v) <= 100:
                raise simple_netem_exceptions.NetemConfigException(
                                    bad_parm=v,
                                    bad_val=eval(v),
                                    accepts='must be numeric and between 0 and 100'
                                    )

        correlation = ' {}%'.format(str(correlation)) or None
        self.duplicate = 'duplicate {}%{}'.format(str(percent), correlation)


class NetemCorrupt(object):
    """
    class wrapper for netem corrupt params



    """
    def __init__(self, percent=0.1, correlation=0):
        for v in ['percent', 'correlation', ]:
            if eval(v) and not isinstance(eval(v), (int, long, float)) or \
               not 0 <= eval(v) <= 100:
                raise simple_netem_exceptions.NetemConfigException(
                                    bad_parm=v,
                                    bad_val=eval(v),
                                    accepts='must be numeric and between 0 and 100'
                                    )

        correlation = ' {}%'.format(str(correlation)) or None

        self.corrupt = 'corrupt {}% {}'.format(str(percent), correlation)



class NetemLimit(object):
    """
    class wrapper for netem limit packets param

    ** it seems that when limit is not specified, netem will apply a limit of
    1000 packets by default **

    LIMIT
    ~~~~~~~
    ::

        LIMIT := limit packets

        limit packets
           limits the effect of selected options to the indicated number of
           next packets.

    """
    def __init__(self, limit=None):
        """
        :param limit:
            must be an integer, default None
        :raises:
            NetemConfigException if passed invalid parameters
        """
        if limit and not isinstance(limit, (int, long)) or \
            limit < 0:
            raise simple_netem_exceptions.NetemConfigException(
                                        bad_parm='limit',
                                        bad_val=limit,
                                        accepts='must be a positive integer'
                                        )
        if limit:
            self.limit = 'limit {}'.format(str(limit))
        else:
            self.limit = ''


class NetemDelay(object):
    """
    class wrapper for netem delay parameters

    DELAY
    ~~~~~~~
    ::

        DELAY := delay TIME [ JITTER [ CORRELATION ]]]
              [ distribution { uniform | normal | pareto |  paretonormal } ]

        delay
           adds the chosen delay to the packets outgoing to chosen network
           interface. The optional parameters allows to introduce a delay
           variation and a correlation.  Delay and jitter values are expressed
           in ms while correlation is percentage.

        distribution
           allow the user to choose the delay distribution. If not specified,
           the default  distribution  is  Normal. Additional  parameters  allow
           to  consider  situations in which network has variable delays
           depending on traffic flows concurring on the same path, that causes
           several delay peaks and a tail.

    practical limits
    ~~~~~~~~~~~~~~~~~~

    the limits on the netem delay parameters are introduced by the clock
    resolution of the Linux kernel. for practical purposes we should not try to
    introduce delays smaller than 1ms (10^^-3 seconds)

    typical delay values
    ~~~~~~~~~~~~~~~~~~~~~~

    * typical delay values:

        delay on a theoretical network is a function of the speed of the
        packets through the transmission medium and the length of the medium.
        light speed is an excellent approximation for copper wired networks and
        wireless networks and a perfect one for fiber networks.

        empirical suggestions for delay values:

        * sub 100ms: continental delays in north america

        * 150ms: intercontinental trans-atlantic

        * 300ms: intercontinental trans-pacific

        * 240ms: perfect satellite link

        * 600ms: multihop satellite link

        jitter and correlation are dependent on the hardware and the
        network congestion and therefore very unpredictable
    """
    valid_delay_units = ['s', 'sec', 'secs', 'ms', 'msec', 'msecs', 'us',
                         'usec', 'usecs', ]
    valid_distros = ['uniform', 'normal', 'pareto', 'paretonormal', ]

    def __init__(self, delay=100, jitter=10,
                 delay_units='', correlation=25, distribution='normal'):
        """
        :param delay:
            must be numeric and positive, optional, default 100
            delay to apply to packets, measured in time units
        :param jitter:
            must be numeric and positive, optional, default 10
            jitter, the equivalent of specifying +/- for delay,
            measured in time units
        :param delay_units:
            optional string, any of valid_delay_units, default None
            time units, if None (bare number), use microseconds (usec)
        :param correlation:
            the apprcximate statistical dependency between packet delay
            variation expressed in %, default 25, between 0 and 100
        :param distribution:
            uniform|normal|pareto|paretonormal, default normal
            the delay variation follows a pre-defined statistical distribution
            curve. the first 3 distribution tables are defined in the kernel. it
            is possible to specify custom distribution curves if they are
            configured in the kernel
        :raises:
            NetemConfigException if passed invalid parameters
        """
        if not delay:
            raise simple_netem_exceptions.NetemConfigException(
                                                bad_parm='delay',
                                                bad_val=delay
                                                )

        for v in ['delay', 'jitter', 'correlation', ]:
            if eval(v) and not isinstance(eval(v), (int, long, float)):
                raise simple_netem_exceptions.NetemConfigException(
                                    bad_parm=v,
                                    bad_val=eval(v),
                                    accepts='must be numeric'
                                    )
            if eval(v) < 0:
                raise simple_netem_exceptions.NetemConfigException(
                                    bad_parm=v,
                                    bad_val=eval(v),
                                    accepts='must be positive'
                                    )

            if 'correlation' in v and eval(v) > 100:
                raise simple_netem_exceptions.NetemConfigException(
                                bad_parm=v,
                                bad_val=eval(v),
                                accepts='must be less than or equal to 100'
                                )

        if delay_units and delay_units not in self.valid_delay_units:
            raise simple_netem_exceptions.NetemConfigException(
                                                bad_parm='delay_units',
                                                bad_val=delay_units,
                                                accepts=self.valid_delay_units
                                                )

        if distribution and distribution not in self.valid_distros:
            raise simple_netem_exceptions.NetemConfigException(
                                                bad_parm='distribution',
                                                bad_val=distribution,
                                                accepts=self.valid_distros
                                                )

        jitter = '{}{}'.format(str(jitter), delay_units) or None
        correlation = '{}%'.format(str(correlation)) or None
        distribution = 'distribution {}'.format(distribution) or None
        delay = 'delay {}{}'.format(str(delay), delay_units)

        self.delay = ' '.join([delay, jitter, correlation, distribution])


# pylint:enable=R0903

