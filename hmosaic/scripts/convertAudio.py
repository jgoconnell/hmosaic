#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This is a commandline script for checking the test_data directory for
mp3s and flacs and converting them to wav files.
Takes care of dodgy filenames too!

"""

# Standard library imports

import os, sys
from glob import glob
from scikits.audiolab import wavwrite, flacread

from hmosaic.utils import switch_ext
from hmosaic.settings import TEST_DATA_DIR
from hmosaic import log

def execute_flac_convert():
    """
    Cycles through test_data, converting all flac to wav
    Script includes a utility remove spaces and problem 
    characters from file name 
    """
    files = [f for f in glob('*.flac')]

    for af in files:
        x = flacread(af)[0]
        log.debug("Found a flac file: '%s'" % af)
        n = switch_ext(strip_all(af), '.wav')
        print ("Converting '%s' to: '%s'" % (af, n))
        wavwrite(x, n, 44100)
        
def execute_mp3_convert():
    """
    Cycles through test_data, converting all mp3 to wav
    Script includes a utility remove spaces and problem 
    characters from file name.
    **WARNING** - This routine uses ffmpeg to convert the mp3s.
    It will fail if ffmpeg is not installed *or* if ffmpeg is installed
    without mp3 support.
    
    """
    files = [f for f in glob('*.mp3')]

    for af in files:
        log.debug("Found an mp3 file: '%s'" % af)
        # Initial step is rename as shell command is a little fussy
        nf = strip_all(af)
        os.rename(af, nf)
        n = switch_ext(nf, '.wav')
        log.info("Converting '%s' to: '%s'" % (nf, n))
        os.system("ffmpeg -i %s %s" % (nf, n))
        
def rename_wavs():
    """
        Short utility script to rename the wav files.
    """
    files = [f for f in glob('*.wav')]
    for af in files:
        log.debug("Found a wav file: '%s'" % af)
        nf = strip_all(af)
        os.rename(af, nf)

def strip_all(input_string):
    """
        Remove problem characters from filenames.
        Minimises annoying errors later on. Better safe than sorry!!
        
    """
    new_string = input_string.replace(' ', '').replace('_', '').replace('-','').replace('(', '').replace(')', '').replace(',', '').replace("'", "").replace('&', '')
    # This expects at least 1 '.' to be present - i.e. the lowest count is 1
    return new_string.replace('.','',(new_string.count('.'))-1)
    

if __name__ == '__main__':
    if not os.path.isdir(TEST_DATA_DIR):
        log.error("The test data directory read from settings does not exist!:%s"
            % TEST_DATA_DIR
        )
        sys.exit()
    else:
        os.chdir(TEST_DATA_DIR)
        execute_flac_convert()
        execute_mp3_convert()
        

