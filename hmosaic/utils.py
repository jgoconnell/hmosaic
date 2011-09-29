# -*- coding: utf-8 -*-
"""
Contains functions which are repeatedly used by different parts of 
the framework.

"""

import os
from glob import glob
from datetime import datetime
import subprocess


import numpy as np
import yaml
from gaia2 import Point
from scikits.audiolab import wavwrite

from hmosaic import log
from storm.sqlobject import Store
from storm.database import create_database

###############################################################################
# AUDIO SIGNAL PROCESSING UTILITY FUNCTIONS
###############################################################################

def to_mono(audio_data):
    """
        Accepts an array of audio data and converts it to mono, ensuring that
        it is represented as an array of 32bit floating point numbers.
        
    """
    if len(audio_data.shape) < 2:
        log.debug("Audio data is already mono, doing nothing.")
        return audio_data
    else:
        mono_array = 0.5 * (audio_data[:,0] + audio_data[:,1])
        log.debug("Audio data is multichannel...")
        log.debug("Convert to mono by taking the mean of the first 2 channels")
        return mono_array.astype('single')
        
        
# Returns a chop value in ms from the bpm value.        
calc_chop_from_bpm = lambda bpm: int((60 * 1000) / float(bpm)) 

# Returns the no of samples given a sample rate and a time in seconds.
secs_to_samps = lambda time, sr: int(round(time*sr))

# Converts the chop size in samples to milliseconds
chop_to_ms = lambda sr, chop: int(sr*(float(chop)/float(1000)))

# Returns onset times in seconds as an array of 32bit floating point numbers
get_fixed_onsets = lambda chop, length: np.array(map(
    lambda x: float((x * chop)/1000.0), range(length/chop)), 'single')
       


###############################################################################
# FILESYSTEM RELATED UTILITY FUNCTIONS
###############################################################################

get_directories = lambda path: filter(lambda x: os.path.isdir(x), \
            glob(os.path.join(path, '*')))

def most_recent_first(paths):
    """
        Orders a list of filepaths by most recently modified first.

    """
    timestamped_paths = [(os.path.getmtime(f), f) for f in paths]
    timestamped_paths.sort()
    timestamped_paths.reverse()
    return [f[1] for f in timestamped_paths]
            
def get_files_recursive(directory, ext = '.wav'):
    """
        Generator to finds all files with extension 'ext'
            
    """
    filepaths = []
    
    for root, dirs, files in os.walk(directory):
        for f in files:
            filepath = (os.path.join(root, f))
            if os.path.splitext(filepath)[1] == ext:
                filepaths.append(filepath)
    filepaths.sort()
    return filepaths
    
    
###############################################################################
# STRING PROCESSING RELATED UTILITY FUNCTIONS
###############################################################################
    
def wav_timestamp(filename):
        """
            Returns a filename or path renamed to contain a timestamp, unique
            to the minute...
            
        """
        t = datetime.now()
        return switch_ext(filename, '%d%d%d%d%d.wav' 
            % (t.year, t.month, t.hour, t.minute, t.second))

switch_ext = lambda name, ext: os.path.splitext(name)[0] + ext

def load_yaml(self, analysis_filepath):
        """
            Uses yaml to return a dictionary of analysis values 
            given an ``analysis_filepath``
            
        """
        return yaml.load(open(switch_ext(analysis_filepath, '.yaml')))

def prepare_thresholds(func, *args):
        """
            A decorator to clean the thresholds string and pass it
            to the function.


        """
        def wrapped_func(*args):
            if not args[1].startswith('WHERE '):
                thresholds = func(args[0], 'WHERE ')
            else:
                thresholds = func(args[0], args[1])
            return thresholds
        return wrapped_func

###############################################################################
# DATABASE RELATED UTILITY FUNCTIONS
###############################################################################
    

def get_db_connection(dbname):
    """
        Opens a connection to the database. The db is assumed to be in 
        the same directory. Returns a ``Store`` interface to the db.

    """
    db = create_database('sqlite:%s' % dbname)
    store = Store(db)
    return store

def get_gaia_point(filepath):
    """
        Tries to load an essentia yaml analysis file (specified in `filepath`)
        as a gaia point.
    """ 
    p = Point()
    p.load(filepath)
    return p

def timestretch(unit, length, sr):
    """
        Stretches a `hmosaic.models.MosaicUnit` to the given **length** 
        for the specified sample rate, **sr**.

    """
    if unit.silent:
        log.info("Unit is silent - no need to timestretch!")
        unit.data = np.zeros(secs_to_samps(length, sr), 'single')
        unit.recalculate()
        return unit
                
    log.debug("Stretching unit of length: %f to %f" % 
         (unit.length, length)
    )
    index = 33
    wavwrite(unit.data, '%d.wav' % index, sr)
    command = ['rubberband', '-D', str(length), '%d.wav' % index, \
            '%d_stretch.wav' % index]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, \
            stderr = subprocess.PIPE)
    (stdout, stderr) = process.communicate()
    log.info(stdout)
    log.info(stderr)
    log.debug("Appending stretched unit to the mosaic")
    unit.set_filepath('%d_stretch.wav' % index)
    log.debug("Removing temporary files: %d.wav, %d_stretch.wav" 
           % (index, index))
    os.remove('%d.wav' % index)
    os.remove('%d_stretch.wav' % index)
    return unit


