# -*- coding: utf-8 -*-
"""
This file contains settings for the project.
e.g. 
* Ip addresses, ports and allowable address strings for OSC communication.
* Filepaths to target corpus, test_corpus.
* shortcuts for analysis keys and paths to Essentia Binaries.

"""
import os


CLIENT_IP='localhost' # Ip address of the gui client
CLIENT_PORT=8000      # Port at which to deliver OSC messages to client

SERVER_IP='localhost'  # Ip address of the mosaicing daemon process
SERVER_PORT=8001       # Port at which to listen on for OSC messages from client

TARGET_REPO = '<path to directory to be used for segmenting and analysing targets>'
SOURCE_REPO = '<path to directory containing source corpora>'

# Default directory of the binary analysers is a directory called 'analyser'
# which is located in the same directory as this file. 
ESSENTIA_BIN_DIR =  os.path.join(os.path.dirname(__file__), 'analyser') 

# Names of the analyser binary to use
DEFAULT_ANALYSER = 'streaming_extractor'


# File logging logs to a file, screen logging logs to the terminal window 
# where the process was started.
# Allowable values here are: 'DEBUG', 'INFO', 'ERROR', 'WARN' or None
FILE_LOGGING = None
SCREEN_LOGGING = 'DEBUG'


# Test data directories - used by some of the experiment routines in the 
# scripts folder

TEST_DATA_DIR = '<path to a directory containing test data>'
TEST_CORPUS_REPO = '<path to a repository containing test corpora>'
TEST_CORPUS = '<name of current test corpus>'
MOOD_DATASET='<path to moods dataset>'
MOOD_COLLECTION='<path to moods collection>'

# Analysis dictionary shortcuts

HAPPY = 'highlevel.mood_happy.all.happy'
SAD = 'highlevel.mood_sad.all.sad'
RELAXED = 'highlevel.mood_relaxed.all.relaxed'
AGGRESSIVE = 'highlevel.mood_aggressive.all.aggressive'
BPM = 'rhythm.bpm'
LIVE = 'highlevel.live_studio.all.live'
STUDIO = 'highlevel.live_studio.all.studio'
VOCAL = 'highlevel.voice_instrumental.all.voice'
INSTRUMENTAL = 'highlevel.voice_instrumental.all.instrumental'
MALE = 'highlevel.gender.all.male'
FEMALE = 'highlevel.gender.all.female'
LOUDNESS = 'lowlevel.spectral_rms.mean'
LENGTH = 'metadata.audio_properties.length'
PITCH = 'lowlevel.pitch.mean'
SCALE = 'tonal.key_scale'
KEY = 'tonal.key_key'

# Each name in this list must correspond to a method of the HighLevelControl object
# this is checked when initialising the object as a daemon process listening on OSC
 
ADDRESS_STRINGS = ['setSourceCorpus', 'analyseCorpus', 'setTarget', 
                       'processTarget', 'createMosaic', 'saveMosaic',
                       'setConstraints', 'setHLConstraints', 
                       'useLabelThreshold', 'useLabel',
                       # useLabelThreshold should set a highlevel label like 
                       # mood and also supply a value for the threshold
                       # useLabel just makes sure that the high level labels 
                       # match for selected units.
                       'setCrossfade', 'setCost', 'useContext', 
                       'toggleHighLevel', 'toggleBPM', 'toggleFixed',
                       'fitToGrid', 'useDynamicCorpus', 'setOnsets', 
                       'getMarkedAudio', 'setAubio', 'setAubioLength',
                       'trackLength', 'trackLengthType', 'setLowScope', 
                       'setHighScope', 'loadLastTarget'
                      ]


