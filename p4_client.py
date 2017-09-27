'''
.. _simple_netem_p4_client:

pyro4 client module for the simple_netem control instances

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

provides classes for connecting to simple_netem control instances using the
Pyro4 protocol

'''
from __future__ import unicode_literals, absolute_import, print_function

import Pyro4

import config
import emulations


class P4NetemClient(object):
    '''
    client class using the Pyro4 protocol
    '''

    def __init__(self, p4_uri=None):
        '''
        :arg str p4_uri: the PYRO URI used to connect to the netem control
        daemon
        '''
        Pyro4.config.SERIALIZER = 'pickle'
        with Pyro4.Proxy(p4_uri) as p4_client:
            p4_client._pyroHmacKey = config.P4_HMAC

        self.client = p4_client
        print(self.client.info)
