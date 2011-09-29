# -*- coding: utf-8 -*-
"""
Initialise logging here. The logging settings are read from ``settings.py``
There are two available modes:
* FILE_LOGGING
* SCREEN_LOGGING
These variables can be set to 'ERROR', 'DEBUG', 'WARN', 'INFO' or None
If both variables are set to None then no logging system is initialised

"""
import os, logging

__all__ = ['control', 'settings']

__version__ = 0.1

from hmosaic.settings import FILE_LOGGING, SCREEN_LOGGING

if FILE_LOGGING or SCREEN_LOGGING:
    log = logging.getLogger('hmosaic')
    formatter = logging.Formatter("%(levelname)s %(asctime)s (Line %(lineno)d of  %(module)s , in %(funcName)s ) - %(message)s")
    if FILE_LOGGING:
        LOG_FILENAME = os.path.join(os.path.dirname(__file__), 'hmosaic.log')
        file_handler = logging.FileHandler(filename=LOG_FILENAME)
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)
    if SCREEN_LOGGING:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        log.addHandler(console_handler)
    log.setLevel(logging.DEBUG)
    log.debug('Logging system is set up')
