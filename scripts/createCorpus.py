#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Standard library imports
import os
import sys
import shutil
from optparse import OptionParser
import simplejson as json


# Project imports
from hmosaic.scripts import analyse_corpus, analyse_corpus_files
from hmosaic.scripts import convertAudio as ca
from hmosaic.corpus import FileCorpusManager, CorpusExistsException


def create_corpus(filepath, weights, chop):
    """
        Create a directory callled corpus in the same directory as filepath,
        convert all the audio files, segment and analyse...
        ffmpeg must be installed for Mp3 conversion to work 
    
    """
    if os.path.isfile(filepath):
        cm = FileCorpusManager(os.path.dirname(filepath))
        try:
            cm.create_corpus('corpus')
        except CorpusExistsException, e:
            cm.delete_corpus('corpus')
            cm.create_corpus('corpus')
        c = cm.load_corpus('corpus')
        shutil.copy(filepath, os.path.join(os.path.dirname(filepath), 
            'corpus', os.path.basename(filepath)))
    else:
        cm = FileCorpusManager(filepath)
        to_copy = os.listdir(cm.repository)
        try:
            cm.create_corpus('corpus')
        except CorpusExistsException, e:
            cm.delete_corpus('corpus')
            to_copy = os.listdir(cm.repository)
            cm.create_corpus('corpus')
        c = cm.load_corpus('corpus')
        os.chdir(cm.repository)
        for f in to_copy:
            shutil.copy(f, c.location)

    os.chdir(c.location)
    ca.rename_wavs()
    ca.execute_flac_convert()
    ca.execute_mp3_convert()
   

    if chop == 'onsets':
        for audio_file in c.list_audio_files():
            c.segment_audio(audio_file, chop, weights)

    analyse_corpus(c, chop)
    analyse_corpus_files(c)

    

def parseCommandLineOptions():
    """
        Set up the option parser and return onset_detection_type.

    """    

    parser = OptionParser()
    parser.add_option("-t", "--target", \
        help="File or directory from which to create the coorpus. (MANDATORY)")
    parser.add_option("-w", "--weights", 
        help="Set weights for the onset detectors: [hfc, complex, rms]. E.g. -w '[1, 0.3, 0.4]'")
    parser.add_option("-f", "--fixed", 
        help="Use fixed-length segmentation - supply a value in milliseconds e.g. 500, 1000, etc.")

    

    (options, args) = parser.parse_args()   

    if not options.target or not (os.path.isfile(options.target) or os.path.isdir(options.target)):
        print ("Problem with the target file/directory: '%s'" % options.target)
        print parser.print_help()
        sys.exit()

    if options.weights:
        try:
            weights = json.loads(options.weights)
        except Exception, e:
            print("Invalid format for weights: %s" % options.weights.help)
            raise
    else:
        # Default weights
        weights = [0.3, 0.2, 0.8]
     
    if options.fixed:
        try:
            chop = int(options.fixed)
        except ValueError, e:
            print("Invalid format for fixed: %s" % options.fixed.help)
            raise
    else:
        chop = 'onsets'
    
    

    return options.target, weights, chop


if __name__ == '__main__':
    """ run this file as a script. """
    filepath, weights, chop = parseCommandLineOptions()
    try:
        create_corpus(filepath, weights, chop)
    except Exception, e:
        print("Exception occurred: %s" % e)
        raise
    
