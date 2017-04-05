'''
.. _simple_netem_settings:

settings module for the simple_netem package

:module:     settings

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

LOGS = 'logs'
'''
:var str LOGS: the directory path for the log files
'''
if not os.path.isdir(LOGS):
    os.makedirs(LOGS)

LOG = os.path.join(LOGS, 'netem.log')

LOG_LEVEL = logging.DEBUG


def get_logger(name, log_file=LOG, log_level=LOG_LEVEL):
    '''
    :returns: a logger object
    '''
    log_config = {
        'version': 1,
        'propagate': True,
        'disable_existing_loggers': True,
        'formatters': {
            'verbose': {
                'format':
                '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
            },
            'simple': {'format': '%(levelname)s %(message)s'},
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
                        'formatter': 'simple'
                        },
        },
        'loggers': {
            'netem': {'handlers': ['console', 'file'], }
        }
    }

    logging.config.dictConfig(log_config)
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    return logger
