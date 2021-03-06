"""
.. _simple_netem_emulations:

python wrapper for linux commands that provide basic WAN emulations

:module:     simple_netem.emulations

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
http://www.linuxfoundation.org/collaborate/workgroups/networking/netem#Emulating_wide_area_network_delays
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

import re
import warnings
import six

from collections import Counter


SCANF_MEASUREMENT = re.compile(
    r'''(                      # group match like scanf() token %e, %E, %f, %g
    [-+]?                      # +/- or nothing for positive
    (\d+(\.\d*)?|\.\d+)        # match numbers: 1, 1., 1.1, .1
    ([eE][-+]?\d+)?            # scientific notation: e(+/-)2 (*10^2)
    )
    (\s*)                      # separator: white space or nothing
    (                          # unit of measure: like GB
    \S*)''', re.VERBOSE)
'''
:var SCANF_MEASUREMENT:
    regular expression pattern (compiled) that will match a measurement

    **measurement** is the value of a quantity of something. most complicated
    example::

        -666.6e-100 units
'''


class EmulationTypeError(TypeError):
    '''
    custom exception class to be raised when an emulation is being fed an
    invalid argument
    '''

    def __init__(self, emulation=None, arg=None, msg=None):
        '''
        :arg string emulation:
            the value of the :class:`<Emulation>` emulation member

        :arg arg: the value of the argument that fails the validation

        :arg string msg: the exception message

        '''
        if msg is None:
            msg = 'argument error in {}: expecting {} {}'.format(
                arg or 'unspecified argument',
                emulation or 'unspecified emulation', msg)
        super(EmulationTypeError, self).__init__(msg)
        self.emulation = emulation
        self.arg = arg


class EmulationValueError(ValueError):
    '''
    raised when one tries to add duplicate emulations

    it is technically possible to call netem with the same command multiple
    times within the same tc command but that may lead to confusion
    '''

    def __init__(self, value, msg=None):
        '''
        :arg dict dupes:

        :arg str msg:
        '''
        if msg is None:
            msg = 'bad value: %s' % value
        super(EmulationValueError, self).__init__(msg)
        self.value = value


class Emulation(object):
    '''
    base class for netem emulations
    '''
    emulation = None

    @staticmethod
    def has_no_duplicates(emulations):
        '''
        it is a bad idea to issue netem commands that duplicate a specific
        emulation

        this method takes a list of emulation objects as instantiated by
        children of this class and complains if there is more than one
        instance for the same class

        it uses the collections.Counter() function to retrieve the number of
        times a specific emulation type shows up.
        it will then iterate through the resulting dictionary style object and
        retrieve all duplicates. if there are no duplicates, we're good

        :arg list emulations: list of :class:`<Emulation>` children

        :raises: :exception:`<EmulationValueError>`
        '''
        type_counter = Counter([type(emulation) for emulation in emulations])

        dupes_counter = dict()
        for key, val in type_counter.items():
            # look, a dupe; go get it, boy
            if val > 1:
                dupes_counter[key] = val

        if dupes_counter:
            value = ', '.join([key.__name__ for key in dupes_counter.keys()])
            msg = 'duplicate netem commands in one emulation: %s' % value
            raise EmulationValueError(value, msg)

        return True

    @staticmethod
    def has_reorder_without_delay(emulations):
        '''
        one cannot do reordering without delaying

        :returns:
            ``True`` if there is a :class:`<Redorder>` emulation instance in
            the list of emulation objects

            ``False`` if there is no :class:`<Redorder>` emulation instance in
            the list of emulation objects or if there is one that is already
            accompanied by a :class:`<Delay>` emulation instance
        '''
        reorder = [
            emulation for emulation in emulations if isinstance(emulation,
                                                                Reorder)]
        delay = [
            emulation for emulation in emulations if isinstance(emulation,
                                                                Delay)]

        if reorder and delay:
            return False
        elif not reorder:
            return False
        else:
            return True

    @staticmethod
    def has_no_multiple_loss_emulations(emulations):
        '''
        there are 3 kinds of packet loss emulations available:

        *    loss random
        *    loss state
        *    loss gemodel

        it doesn't make any sense to allow for more than one of them to be
        active at the same time

        this method will raise an exception if more than one loss emulation
        is present in the argument

        the method creates a list of booleans. if a loss emulation is present,
        the element is set to ``True``, otherwise the element is not set.
        the method then uses the :class:`<collections.Counter>` to count
        the occurrences of ``True``

        :arg emulations:
        '''
        loss_counter = Counter(
            [True for emulation in emulations if isinstance(
                emulation, (LossRandom, LossState, LossGemodel))]
        )

        if not loss_counter:
            # no loss emulations, go away
            return True

        if loss_counter.get(True) > 1:
            value = ', '.join([key.__name__ for key in loss_counter.keys()])
            msg = 'multiple netem loss commands in one emulation: %s' % value
            raise EmulationValueError(value, msg)

        return True

    @staticmethod
    def has_limit(emulations):
        '''
        netem will place a limit in any add netem command by default but
        that applies for only 1000 packets

        this method checks if there is a non-default netem limit command
        within a list of emulations
        '''
        if [emulation for emulation in emulations if isinstance(emulation,
                                                                Limit)]:
            return True
        return False

    def validate_and_add(self, *args, **kwargs):
        '''
        add each arg in *args to the emulation property but only if arg is
        valid

        each arg must be a string formatted as 'number[[sep]unit_of_measure]'
        where the number part can be in any numeric format that is accepted
        by the ``float()`` function, sep can be any combination of characters
        that evaluates to white space, and the unit_of_measure is a ``str``.

        this method will validate each arg in *args,
        remove the white space(s), and append it to the :member:`<emulation>`
        using a space as separator

        :raises:
            :exception:`<EmulationTypeError>` if any arg fails validation

        :param args:
            the emulation arguments to be validated and added to the emulation

        :param bool lt_100:
            (as part of **kwargs) must all these args be less than 100?
            default ``True`` because most of these args are either
            percentage of packets or chance that the emulation will kick in

            if this argument is not specified when invoking this method,
            any arg with a value greater then 100.00 will raise an exception

        :param bool positive:
            (as part of kwargs) must all these args be positive?
            default ``True``

        :param bool integer:
            (as part of kwargs) force the numeric part of each arg to ``int``?
            default ``False``

        :param default_unit:
            (as part of kwargs) the measurement unit that should be used
            for these args if not present as part of the arg itself.
            default is the '' (empty) ``str``; this is necessary because a
            ``None`` will actually evaluate to the `None` ``str`` when fed
            into ``format()``.

        :param units:
            (as part of kwargs) the measurement units that are to be
            considered acceptable for these args. default is the '' (empty)
            ``str``; this is necessary because a ``None`` will actually
            evaluate to the `None` ``str`` when fed into ``format()``.
            this parameter will also accept a ``list`` or ``tuple``

        :param bool can_be_bare:
            (as part of kwargs) are args with no measurement units acceptable?
            default is ``True``
        '''
        # handle the known kwargs key: value pairs
        lt_100 = kwargs.get('lt_100', True)
        positive = kwargs.get('positive', True)
        integer = kwargs.get('integer', False)
        default_unit = kwargs.get('default_unit', '')
        units = kwargs.pop('units', '')
        if not isinstance(units, (list, tuple)):
            units = [units]
        can_be_bare = kwargs.get('can_be_bare', True)
        # done with the default kwargs entries

        def get_arg_value(arg_match, arg):
            '''
            get the numeric part of the argument

            :arg arg_match: a re.match object

            :arg str arg: the string that was used to generate arg_match

            :returns: the numeric part of the arg

            :raises: :exception:`<EmulationTypeError>`
            '''
            try:
                arg_value = float(arg_match.groups()[0])
                if integer:
                    arg_value = int(arg_value)  # pylint:disable=R0204
            except ValueError:
                raise EmulationTypeError(
                    emulation=self.emulation, arg=arg,
                    msg='must start with a number')

            if positive and arg_value <= 0:
                raise EmulationTypeError(
                    emulation=self.emulation, arg=arg,
                    msg='must start with a positive number')

            if lt_100 and arg_value > 100:
                raise EmulationTypeError(
                    emulation=self.emulation, arg=arg,
                    msg='must start with a number smaller than 100')

            return str(arg_value)

        def get_arg_units(arg_match, arg):
            '''
            get the units part of the argument

            :arg arg_match: a re.match object

            :arg str arg: the string that was used to generate arg_match

            :returns: the numeric part of the arg

            :raises: :exception:`<EmulationTypeError>`
            '''
            arg_units = arg_match.groups()[5].lower()

            if not arg_units:
                if can_be_bare:
                    # no units is acceptable, just go away
                    return ''
                else:
                    arg_units = default_unit

            if arg_units not in units:
                raise EmulationTypeError(
                    emulation=self.emulation, arg=arg,
                    msg='invalid measurement unit. must be one of %s' %
                    ', '.join(units))

            return arg_units

        for arg in args:
            if arg is None:
                # nothing we can do here
                continue

            if not isinstance(arg, six.text_type):
                # not a string? cast it to a string
                # use six.text_type to force py2*3 compatibility
                arg = str(arg)

            # generate the re.macth object here so that we do it just once per
            # loop. we could do it within the get_arg_foo() functions
            # but then we would do it twice per loop
            arg_match = re.match(SCANF_MEASUREMENT, arg)
            if not arg_match:
                # hard to believe but maybe
                raise EmulationTypeError(
                    emulation=self.emulation, arg=arg,
                    msg='a measurement'
                    ' (a numeric value followed by an optional separator'
                    ' and an optional measurement unit)')

            self.emulation = '{} {}{}'.format(
                self.emulation,
                get_arg_value(arg_match, arg), get_arg_units(arg_match, arg))


class LossRandom(Emulation):
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
        :param int percent: packets to loose expressed in %, default 1

        :param correlation:
            chances (approximate) that a packet lost will cause the next packet
            in the sequence to be lost as well

            it doesn't require % format but it is a percentage style value

        :raises:

            :exception:`<EmulationTypeError>` if passed invalid parameters

            :warnings:`<DeprecationWarning>` if correlation is present
        """
        self.emulation = 'loss random'
        if correlation:
            warnings.warn('using correlation for random loss is deprecated',
                          DeprecationWarning)

        self.validate_and_add(percent, correlation)


class LossState(Emulation):
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

    the 4-state Markov model has (duh) 4 possible states:

    *    'good reception' is a 0% loss state that can transition to
         'burst loss' or to 'single loss'

    *    'burst loss" is a 100% loss state that can transition to either 'good
         reception' or 'good burst reception'. specific and important is that
         in this state, there are no single packet losses

    *    'good burst reception' is a 0% loss state that can only transition to
         'burst loss' and back

    *    'independent loss' is a 100% loss state that can only have 1 event
         (1 lost packet). this state can only transition to the
         'good reception' state

    defaults
    ---------

    **as implemented by this class**

    *    p13: 10%; chance of getting from 'good' to '100% burst loss'

    *    p31: 70%; chance of getting from '100% burst loss' to 'good'

    *    p23: 10%; chance of getting from 'good burst' to '100% burst loss'

    *    p32: 10%; chance of getting from '100% burst loss' to 'good burst'

    *    p41: 1%; chance of isolated packet drops while in 'good'

    as a general rule of thumb:
    ---------------------------

    *    p13 is mandatory, signifies the probability of the system
         transitioning from the 'good reception' state to a 'burst loss' state
         (all the packets are lost), and puts the system in this configuration
         if used alone::

            autolab@netem-z97proto:~$ sudo tc qdisc add dev eth1 root netem \
            loss state 10
            autolab@netem-z97proto:~$ tc -s qdisc show dev eth1
            qdisc netem 801c: root refcnt 2 limit 1000 loss state \
            p13 10% p31 90% p32 0% p23 100% p14 0%
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
    # pylint:disable=R0913

    def __init__(self, p_13=10, p_31=70, p_23=10, p_32=10, p_14=1):
        """
        :param p_13:
            is mandatory, numeric between 0 and 100, default 10

        :param p_31:
            numeruc between 0 and 100, default 70

        :param p_23:
            numeruc between 0 and 100, default 10

        :param p_32:
             numeruc between 0 and 100, default 10

        :param p_14:
            numeruc between 0 and 100, default 1

        :raises:
            :exception:`<EmulationTypeError>` if passed invalid parameters
        """
        self.emulation = 'loss state'
        if not p_13:
            # this one is mandatory
            raise EmulationTypeError(
                emulation=self.emulation, arg='None',
                msg='p_13 is a mandatory argument')

        self.validate_and_add(p_13, p_31, p_23, p_32, p_14)

    # pylint:enable=R0913


class LossGemodel(Emulation):
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
            :exception:`<EmulationTypeError>` if passed invalid parameters
        """
        self.emulation = 'loss gemodel'
        if not p:
            # this one is mandatory
            raise EmulationTypeError(
                emulation=self.emulation, arg='None',
                msg='p is a mandatory argument')

        self.validate_and_add(p, r, one_h, one_k)


class Rate(Emulation):
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
        strip the Ethernet header (e.g. -14) and/or simulate a link layer
        header compression scheme.
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
    _unit = 'mbit'
    _units = ['bit', 'bps', 'kbit', 'kbps', 'mbit', 'mbps', 'gbit', 'gbps', ]

    def __init__(self, rate='1mbit'):
        """
        :param rate:
        :param units:
        :raises:
            :exception:`<EmulationTypeError>` if passed invalid parameters
        """
        self.emulation = 'rate'

        self.validate_and_add(
            rate,
            default_unit=self._unit, units=self._units, can_be_bare=False)


class Reorder(Emulation):
    """
    class wrapper for netem packet reordering

    extract from the netem man page
    ---------------------------------

    REORDERING := reorder PERCENT [ CORRELATION ] [ gap DISTANCE ]

    reorder::

       to use reordering, a delay option must be specified.
       There are two ways  to  use  this  option  (assuming 'delay 10ms' in
       the options list).

       reorder 25% 50% gap 5
       in  this first example, the first 4 (gap - 1) packets are delayed by
       10ms and subsequent packets are sent immediately with a probability
       of 0.25 (with correlation of 50% ) or delayed with a probability
       of  0.75.
       After  a  packet  is  reordered,  the process restarts i.e. the next
       4 packets are delayed and subsequent packets are sent immediately or
       delayed based on reordering probability.
       To cause  a  repeatable  pattern where every 5th packet is reordered
       reliably, a reorder probability of 100% can be used.

       reorder 25% 50%
       in this second example 25% of packets are sent immediately
       (with correlation of 50%) while the others are delayed by 10 ms.


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
            :exception:`<EmulationTypeError>` if passed invalid parameters
        """
        self.emulation = 'reorder'
        if not percent:
            # this one is mandatory
            raise EmulationTypeError(
                emulation=self.emulation, arg='None',
                msg='percent is a mandatory argument')

        self.validate_and_add(percent, correlation)

        if gap:
            self.emulation = '{} gap'.format(self.emulation)
            self.validate_and_add(gap)


class Duplicate(Emulation):
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

    def __init__(self, percent=1, correlation=None):
        """
        :param percent:
            duplicate percent of packets, must be an integer, optional,
            default 1
        :param correlation:
            duplication correlation, must be an integer, optional, default 10
        :raises:
            :exception:`<EmulationTypeError>` if passed invalid parameters
        """
        self.emulation = 'duplicate'

        if not percent:
            # this one is mandatory
            raise EmulationTypeError(
                emulation=self.emulation, arg='None',
                msg='percent is a mandatory argument')

        self.validate_and_add(percent, correlation)


class Corrupt(Emulation):
    """
    class wrapper for netem corrupt params

    CORRUPT := corrupt PERCENT [ CORRELATION ]]

    corrupt
       allows the emulation of random noise introducing an error in  a  random
       position  for a chosen percent of packets. It is also possible to add a
       correlation through the proper parameter.

    """

    def __init__(self, percent=0.1, correlation=None):
        '''
        :param percent:
            percent of corrupt packets in a transmission; default 0.1

        :param correlation:
            chance that a corrupt packet will be followed by another corrupt
            packet

        :raises:
            :exception:`<EmulationTypeError>` if passed invalid parameters
        '''
        self.emulation = 'corrupt'
        if not percent:
            # this one is mandatory
            raise EmulationTypeError(
                emulation=self.emulation, arg='None',
                msg='percent is a mandatory argument')

        self.validate_and_add(percent, correlation)

        self.corrupt = 'corrupt {}% {}'.format(str(percent), correlation)


class Limit(Emulation):
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

    def __init__(self, limit='1e6'):
        """
        :param limit:
            must be an integer, default 1 million packets
        :raises:
            :exception:`<EmulationTypeError>` if passed invalid parameters
        """
        self.emulation = 'limit'
        if not limit:
            # this one is mandatory
            raise EmulationTypeError(
                emulation=self.emulation, arg='None',
                msg='limit is a mandatory argument')

        self.validate_and_add(limit, lt_100=False, integer=True)


class Delay(Emulation):
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
    _unit = 'ms'
    _units = ['s', 'sec', 'secs', 'ms', 'msec', 'msecs', 'us',
              'usec', 'usecs', ]
    _distributions = ['uniform', 'normal', 'pareto', 'paretonormal', ]

    def __init__(self, delay=100, jitter=10,
                 correlation=25, distribution='normal'):
        """
        :param delay:
            must be numeric and positive, optional, default 100ms
            delay to apply to packets, measured in time units
        :param jitter:
            must be numeric and positive, optional, default 10ms
            jitter, the equivalent of specifying +/- for delay,
            measured in time units
        :param correlation:
            the apprcximate statistical dependency between packet delay
            variation expressed in %, default 25, between 0 and 100
        :param distribution:
            uniform|normal|pareto|paretonormal, default normal
            the delay variation follows a pre-defined statistical distribution
            curve. the first 3 distribution tables are defined in the kernel.
            it is possible to specify custom distribution curves if they are
            configured in the kernel
        :raises:
            :exception:`<EmulationTypeError>` if passed invalid parameters
        """
        self.emulation = 'delay'

        if not delay:
            # this one is mandatory
            raise EmulationTypeError(
                emulation=self.emulation, arg='None',
                msg='delay is a mandatory argument')

        self.validate_and_add(
            delay, jitter,
            lt_100=False, default_unit=self._units, units=self._units)

        if correlation:
            self.validate_and_add(correlation)

        if distribution:
            if distribution not in self._distributions:
                raise EmulationTypeError(
                    emulation=self.emulation, arg='None',
                    msg='distribution must be one of %s'
                    % ', '.join(self._distributions))

            self.emulation = '{} distribution {}'.format(
                self.emulation, distribution)

# pylint:enable=R0903
