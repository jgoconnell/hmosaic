# -*- coding: utf-8 -*-
"""
Contains all models related to segmentation. 
Aubio and Essentia are both utilised by different routines.

"""

# Standard library imports
import os
import subprocess

# Third party library imports
from scikits.audiolab import wavread, wavwrite
import numpy as np

from essentia import Pool
from essentia.standard import AudioOnsetsMarker, MonoLoader, OnsetDetection
from essentia.standard import Windowing, Spectrum, Flux, FFT, CartesianToPolar 
from essentia.standard import FrameGenerator, Onsets, RMS

# hmosaic package imports
from hmosaic.utils import chop_to_ms, get_fixed_onsets, secs_to_samps
from hmosaic.utils import to_mono, switch_ext
from hmosaic.models import SegmentAudio, Unit
from hmosaic import log



class AudioSegmenter:
    """
        Basic fixed length segmenter. Is initialised with a given 
        ``chop`` size (in ms) and provides methods to retrieve an array
        of marked audio data and a generator function to yield units
        of segmented audio, which can be written to the corpus.
        This class may be considered the base class for a segmenter.
        Any subclasses ought to override these 3 object functions
        
    """
    
    def __init__(self, chop=500, hop=None):
        """
            Set the chop time and/or hopsize here.
        """
        self.chop = chop
        self.hop = hop
        
    def segment(self, filepath):
        """
            Tries to create an Audio instance here.
            Yields segments of sample data.
            
        """
        audio = SegmentAudio(filepath)
        unit_length = chop_to_ms(audio.sample_rate, self.chop)
        if self.hop:
            increment = int(unit_length * self.hop)
        else:
            increment = unit_length
        # Slice the audio and break into units
        for unit_begin in range(0, len(audio.audio_array), increment):
            unit = audio.audio_array[unit_begin: unit_begin + unit_length]
            if len(unit) == unit_length: # Ignore leftover samples. Who cares...
                yield Unit(unit, audio.sample_rate, unit_length)

    def mark_audio(self, filepath):
        """
        """
        audio = SegmentAudio(filepath)
        onsets_all = get_fixed_onsets(self.chop, audio.length*1000)
        print "Onsets are %s" % onsets_all
        marker = AudioOnsetsMarker(onsets = onsets_all, type = 'beep')
        marked_audio = marker(audio.audio_array.astype('single'))
        return marked_audio
                

class NoteOnsetSegmenter(object):
    """
        This is a pure essentia segmenter.
        I have found that hfc and rms give better result so 
        that's why the defaults are as they are. Weights are 
        evaluated as 1. complex, 2. hfc, 3. rms
    """
    
    defaults = {'rms': 1, 'complex': 1, 'hfc': 1, 'flux': 0.0}

    def __init__(self, sr = 44100, frame_size=4096, hop_size=512,
        onset_weights=defaults, filter_audio=False, aubio=False, fixedlength=False):
        """
            
        """
        self.sr = 44100
        self.frame_size = frame_size
        self.hop_size = hop_size
        self.onset_weights = onset_weights
        self.filter_audio=filter_audio
        self.aubio = aubio
        self.aubio_length = 0.2
    
    def set_weights(self, weights):
        """
            Expects weights to be a valid onset_weights dictionary
        """
        self.onset_weights = weights   
        
    def segment(self, filepath):
        """
            
        """
        if self.aubio:
            onsets_all = self._aubio_onsets(filepath)
            audio = MonoLoader(filename=filepath)()
        else:
            pool, audio = self._analyse(filepath)        
            onsets_all = self._convert_weights(pool)

        for index, onset in enumerate(onsets_all):
            if index == 0:
                prev_onset = secs_to_samps(onset, self.sr)
                continue
            else:
                print "Previous onset is: %d" % prev_onset
                print "Current Onset is: %d" % secs_to_samps(onset, self.sr)
                samps = secs_to_samps(onset, self.sr) - prev_onset
                yield Unit(audio[prev_onset:prev_onset+samps],\
                    self.sr, (float(samps) / float(self.sr)))
            prev_onset = secs_to_samps(onset, self.sr)

    def mark_audio(self, filepath):
        """
        """
        if self.aubio:
            onsets_all = self._aubio_onsets(filepath)
            audio = MonoLoader(filename=filepath)()
        else:
            pool, audio = self._analyse(filepath)
            onsets_all = self._convert_weights(pool)
        print "Onsets are %s" % onsets_all
        marker = AudioOnsetsMarker(onsets = onsets_all, type = 'beep')
        marked_audio = marker(audio)
        return marked_audio


    def _convert_weights(self, pool):
        for onset_type in pool.descriptorNames():
            if onset_type in self.onset_weights.keys():
                print "Onset type is: %s" % onset_type
                print pool[onset_type]
                print self.onset_weights[onset_type]
        onset_list = [pool[onset_type] for onset_type in pool.descriptorNames() \
            if onset_type in self.onset_weights.keys()]
        weights = [self.onset_weights[onset_type] for onset_type in \
            pool.descriptorNames() if onset_type in self.onset_weights.keys()]
        
        onsets = Onsets()
        print ("Calculating onsets using these weights '%s' " % weights)
        return onsets(np.array(onset_list), weights)

    def _analyse(self, filepath):
        audio = to_mono(wavread(filepath)[0])
        audio = audio.astype('float32')
        
        w = Windowing(type = 'hann')
        fft = FFT() # this gives us a complex FFT
        c2p = CartesianToPolar() # and this turns it into a pair (magnitude, phase)
        hfc_detect = OnsetDetection(method = 'hfc')
        complex_detect = OnsetDetection(method = 'complex')
        rms_detect = RMS()
        spec = Spectrum()
        #pd = PitchDetection()
        flux = Flux()
        pool = Pool()
        #wap = WarpedAutoCorrelation()
        
    
        # let's get down to business
        print 'Computing onset detection functions...'
        for frame in FrameGenerator(audio, frameSize = self.frame_size,\
            hopSize = self.hop_size):
            mag, phase, = c2p(fft(w(frame)))
            spectrum = spec(w(frame))
            f = flux(spectrum)
            #pitch = pd(spectrum)
            pool.add('hfc', hfc_detect(mag, phase))
            pool.add('complex', complex_detect(mag, phase))
            pool.add('rms', rms_detect(frame))
            pool.add('flux', f)
            #pool.add('pitch', pitch[0])
        #print pool['pitch']
        #pool.add('autoc', wap(pool['pitch']))
     

        return pool, audio

    def _aubio_onsets(self, filepath):
        """
            Uses the aubionotes command line utility to do note segmentation.

        """
        
        command = ['aubionotes','-i', filepath, '-t', '0.9' ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, \
        stderr = subprocess.PIPE)
        (stdout, stderr) = process.communicate()
        
        # Don't know what happpens when this yoke throws an error
        print stdout
        print len(stdout)
        numbers = stdout.split('\n')
        onsets = set()
        prev_note = 0
        skipped=False
        for n in numbers:
            print ("Is this A NUMBER? :%s" %n)
            no_list = n.split()
            if len(no_list) == 3:
                print float(no_list[2]) - float(no_list[1])
                if prev_note == 0:
                    onsets.add(float(no_list[1]))
                    prev_note = float(no_list[1])
                if float(no_list[2]) - prev_note < self.aubio_length:
                    print("Note is too small, lets merge.")
                    #prev_note = float(no_list[1])
                    #onsets.add(float(no_list[1]))
                    skipped =  True
                else:
                    print ("This is data I can use!!: %s" % no_list)
                    if not skipped:
                        onsets.add(float(no_list[1]))
                    onsets.add(float(no_list[2]))
                    skipped=False
                    prev_note = float(no_list[2])
        onset_list = list(onsets)
        onset_list.sort()
        print ("Onsets are: %s" % onset_list)
        return onset_list

    def write_aubio_onsets(self, onset_list, filepath):
        print ("Onsets are :%s" % onset_list)
        audio = MonoLoader(filename=filepath)()
        marker = AudioOnsetsMarker(onsets = onset_list, type = 'beep')
        marked_audio = marker(audio)
        wavwrite(marked_audio, switch_ext(os.path.basename(filepath), \
            'AUBIOONSETS.wav'), 44100)
    

