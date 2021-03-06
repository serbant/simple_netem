'''
.. _simple_netem_config:

settings module for the simple_netem package

:module:     config

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

'''
from __future__ import unicode_literals
import os
import logging
import logging.config


__version__ = '0.0.1'

##############################################################################
# startup
##############################################################################
DESCRIPTION = '''
exposes network device commands via a Pyro4 RPC server.
 UP, DOWN, LIST, SHOW and netem emulation commands are available
'''
EPILOG = '''
Copyright 2017 Serban Teodorescu.
 Licensed under the Apache License, Version 2.0
'''
HOST = 'localhost'
PORT = 21499
LOG_LEVELS = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']
DEFAULT_LOG_LEVEL = 'INFO'

##############################################################################
# logging
##############################################################################
LOGS = 'logs'
'''
:var str LOGS: the directory path for the log files
'''

LOG = 'netem.log'


def get_logger(name, log_path=LOGS, log_name=LOG, log_level=logging.DEBUG):
    '''
    :returns: a logger object
    '''
    if not os.path.isdir(log_path):
        os.makedirs(log_path)

    log_file = os.path.join(log_path, log_name)

    log_config = {
        'version': 1,
        'propagate': True,
        'disable_existing_loggers': True,
        'formatters': {
            'verbose': {
                'format':
                '%(asctime)s %(levelname)s %(module)s, line %(lineno)d'
                ' (%(process)d %(thread)d): %(message)s'},
            'simple': {
                'format':
                '%(relativeCreated)d %(levelname)s %(module)s,'
                ' line %(lineno)d: %(message)s'},
        },
        'handlers': {
            'file': {'level': log_level,
                     'class': 'logging.handlers.RotatingFileHandler',
                     'filename': log_file,
                     'maxBytes': 5242880,
                     'backupCount': 7,
                     'formatter': 'verbose'},
            'console': {'level': log_level,
                        'class': 'logging.StreamHandler',
                        'formatter': 'simple'},
        },
        'loggers': {
            'local_netem': {'handlers': ['console', 'file'], },
            'pyro4_netem': {'handlers': ['console', 'file'], }
        }
    }
    # pylint:enable=C0301

    logging.config.dictConfig(log_config)
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    return logger


##############################################################################
# netem control defaults
##############################################################################
XCLUDE_WLAN = True
'''
:var bool XCLUDE_WLAN: default configuration for not using WLAN devices
'''

XCLUDE_LOOPBACK = True
'''
:var bool XCLUDE_LOOPBACK: default configuration for not using loopback devices
'''

##############################################################################
# Pyro4 settings
##############################################################################
P4_SERVERTYPE = 'multiplex'
'''
:var P4_SERVERTYPE: Pyro4.config.SERVERTYPE value

    default is threaded but we want multiplexed
'''

P4_HMAC = b'buona fortuna, donna lucia!'
'''
:var P4_HMAC: Pyro4 require an HMAC key to communicate across the network

    note that there security concerns when hard coding the key like above
'''

P4_PICKLE = 'pickle'
'''
:var P4_PICKLE: the serilaizer to use in Pyro4 for complex, unsafe objects
'''
