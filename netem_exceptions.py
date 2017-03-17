"""
.. _simple_netem_exceptions:

:module:     simple_netem_exceptions

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

"""
from __future__ import unicode_literals


class CommandError(Exception):
    '''
    raised if there is an error in invoking a :class:`<Command>` command
    '''

    def __init__(self, *arg_names, **kwargs):
        self.message = 'mandatory arguments: {}'.format(', '.join(arg_names))
        self.__dict__.update(kwargs)
        super(CommandError, self).__init__(self.message)


class NetemBaseError(Exception):
    """
    NetemBaseError
    """

    def __init__(self, message, **kwargs):
        self.message = message
        self.__dict__.update(kwargs)
        super(NetemBaseError, self).__init__(message)


class NetemSideException(NetemBaseError):
    """
    NetemSideException raised when a NetemInterface instance is initialized
    without a side argument
    """

    def __init__(self, **dummy_kwargs):
        message = 'the side argument is mandatory'
        super(NetemSideException, self).__init__(message)


class NetemCtrlFqdnException(NetemBaseError):
    """
    NetemCtrlFqdnException raised when trying to initialize a NetemInterface
    object without specifying the fqdn where the app is running
    """

    def __init__(self, **dummy_kwargs):
        message = '''the ctrl_fqdn parameter is mandatory'''
        super(NetemCtrlFqdnException, self).__init__(message)


class NetemCtrlPortException(NetemBaseError):
    """
    NetemCtrlPortException raised when trying to initialize a NetemInterface
    object without specifying the port where the app is running
    """

    def __init__(self, **dummy_kwargs):
        message = '''the ctrl_port parameter is mandatory'''
        super(NetemCtrlPortException, self).__init__(message)


class NetemNotSupportedError(NetemBaseError):
    """
    NetemNotSupportedError raised when trying to initialize NetemCtrl
    classes on platforms other than Linux
    """

    def __init__(self, out, err, **dummy_kwargs):
        """
        :param out:
            the command and it's output
        :param err:
            the error message returned by the command
        """
        self.out = 'unsupported command: {}'.format(out)
        self.err = 'error: {}'.format(err)
        message = '{}. {}'.format(self.out, self.err)
        super(NetemNotSupportedError, self).__init__(message)


class NetemInvalidInterface(NetemBaseError):
    """
    NetemInvalidInterface raised when trying to initialize a NetemInterface
    instance on an ethernet name that does not exist on the host
    """

    def __init__(self, bad_iface, all_ifaces, **dummy_kwargs):
        """
        :param bad_iface:
            the offending interface namne
        :param all_ifaces:
            a list of valid interface names according to the host operating
            system
        """
        self.bad_iface = bad_iface
        self.all_ifaces = ', '.join(all_ifaces)
        message = '''invalid ethernet name {}. must use one of {}'''.format(
            self.bad_iface,
            self.all_ifaces
        )
        super(NetemInvalidInterface, self).__init__(message)


class NetemInterfaceBusyError(NetemBaseError):
    '''
    raised when one tries to start a new NetemInterface instance on a
    network device already in use
    '''

    def __init__(self, interface, **dummy_kwargs):
        '''
        :arg str interface: the name of a network device
        '''
        message = 'device {} is already being used for another emulation'.\
            format(interface)
        super(NetemInterfaceBusyError, self).__init__(message)


class NetemSideAlreadyDefinedError(NetemBaseError):
    '''
    raised when one tries to start a new NetemInterface instance on a
    network device already in use
    '''

    def __init__(self, side, **dummy_kwargs):
        '''
        :arg str side: the name of a network device
        '''
        message = 'side {} is already being used for another emulation'.\
            format(side)
        super(NetemSideAlreadyDefinedError, self).__init__(message)


class NetemInsufficientInterfaces(NetemBaseError):
    """
    NetemInsufficientInterfaces raised when there aren't enough interfaces on
    the host; need at least 2 and need a free interface for each NetemInterface
    instance
    """

    def __init__(self, interfaces, **dummy_kwargs):
        message = 'a netem node needs at least 2 network devices.'
        ' network interfaces on this host: \n{}'.format(interfaces)
        super(NetemInsufficientInterfaces, self).__init__(message)


class NetemUnexpectedError(NetemBaseError):
    """
    shit happens netem exception
    """

    def __init__(self, err, **dummy_kwargs):
        message = 'unexpected error {}'.format(err)
        super(NetemUnexpectedError, self).__init__(message)
        self.err = err


class NetemConfigException(NetemBaseError):
    """
    NetemDelayException raised when invalid parameters are fed into the
    'tc qdisc add dev $iface root netem' command
    """

    def __init__(self, bad_parm=None, bad_val=None, accepts='', **dummy_kwargs):
        """
        :param bad_parm:
            the offending parameter
        :param bad_val:
            the offending value
        :param accepts:
            acceptable parameter values
        """
        self.bad_val = '{}'.format(bad_val) or None
        self.bad_parm = '{}'.format(bad_parm) or None

        if isinstance(accepts, list):
            self.accepts = '. must be one of {}'.format(', '.join(accepts))
        else:
            self.accepts = ', {}'.format(accepts)

        message = '''invalid parameter {}={}{}'''.format(self.bad_parm,
                                                         self.bad_val,
                                                         self.accepts)

        super(NetemConfigException, self).__init__(message)
