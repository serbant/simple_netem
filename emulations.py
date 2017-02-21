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

import six
import warnings

import simple_netem_exceptions

__version__ = '0.0.1'


class EmulationArgTypeError(TypeError):

    def __init__(self, emulation, arg, message):
        self.message = 'type error in (): {} {}'.format(
            arg, emulation, message)
        super(EmulationArgTypeError, self).__init__(message)


class _Emulation(object):
    emulation = None

    def is_valid(self, is_percent=False, *args):
        '''
        are the arguments valid percentage values?

        a valid percentage must be a positive number between 0.00 and 100.00
        (exclusive).
        granting that 0.00% and anything greater than or equal to 100.00% are
        mathematically valid, it does not make sense to accept 0 or 100 and
        greater as valid for our purposes:

        *    0 will mean that the emulation does not apply to any packets

        *    100 and greater will mean that all packets (or more than all
             which does not make sense)) are subject to the emulation
        '''
        for arg in args:
            if arg is None:
                # nothing we can do here
                continue

            if not isinstance(arg, (six.integer_types, float)):
                raise EmulationArgTypeError(
                    emulation=self.emulation, arg=arg,
                    message='must be numeric')
            elif arg <= 0:
                raise EmulationArgTypeError(
                    emulation=self.emulation, arg=arg,
                    message='must be a positive real number')
            elif is_percent and arg > 100:
                raise EmulationArgTypeError(
                    emulation=self.emulation, arg=arg,
                    message='must be a positive real number between 0 and 100'
                    ' (a percent)')
            else:
                continue


class LossRandom(_Emulation):
    """
    class wrapper for netem packet loss in random mode

    extract from the netem man page
    ---------------------------------

    LOSS := loss { **random PERCENT [ CORRELATION ]**  |
                      state p13 [ p31 [ p32 [ p23 [ p14]]]] |
                      gemodel p [ r [ 1-h [ 1-k ]]] }  [ ecn ]

    loss random
       adds an independent loss probability to the packets outgoing from the
       chosen  network  interface.  It  is also possible to add a correlation,
       but this option is now deprecated due to the noticed bad behavior.

    ecn
       can  be used optionally to mark packets instead of dropping them.
       A loss model has to be used for this to be enabled.

    """

    def __init__(self, percent=1, correlation=None):
        """
        :param percent:
            precentage of packets to lose, default=1 (%), must be integer
        :param correlation:
            chances (approximate) that a packet lost will cause the next packet
            in the sequence to be lost

            it doesn't require % format but it is a percentage style value

        :raises: 

            :exception:`<EmulationArgTypeError>` if passed invalid parameters

            :warnings:`<DeprecationWarning>` if correlation is present
        """
        self.emulation = 'loss random'

        self.is_valid(True, percent, correlation)

        self.emulation = '{} {}%'.format(self.emulation, str(percent))

        if correlation:
            warnings.warn('using correlation for random loss is deprecated',
                          DeprecationWarning)
            self.emulation = '{} {}'.format(self.emulation, str(correlation))


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
