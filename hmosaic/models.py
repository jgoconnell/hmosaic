# -*- coding: utf-8 -*-
"""
This module contains most of the models used in the framework.
This includes **storm** ORM models, as well as quite sophisticated
Mosaic models which keep track of their constituent units and can apply 
global crossfades and timestretching.

"""

# Standard library imports
import os
import numpy as np
import subprocess

# Third party library imports
from scikits.audiolab import wavread, wavwrite
from storm.locals import Date, Bool, Reference, Unicode, Int, Float

# Project imports
from hmosaic import log
from hmosaic.utils import secs_to_samps, timestretch

class DBSong(object):
    """
        Information about the full source audio files
    """

    __storm_table__ = "song"
    id = Int(primary=True)
    song_name = Unicode()
    male = Float()
    female = Float()
    vocal = Float()
    instrumental = Float()

class DBSegment(object):
    """
        Information about segments drawn from the *DBSongs*
        Contains high level analysis data like *male*, *female*
        *vocal*, *instrumental*, etc.

    """
    __storm_table__ = "segment"
    id = Int(primary=True)
    song_name = Unicode()
    song = Reference(song_name, DBSong.song_name)
    segment_name = Unicode()
    segment_duration = Int()
    vocal = Float()
    instrumental = Float()
    male = Float()
    female = Float()




class SegmentAudio():
    """
        Very simple audio class - encapsulates the following information
        about an audio file
         *  ``filepath`` - location of original file.
         *  ``audio_array`` - 32bit floating point array of audio signal.
         *  ``sample_rate`` - Sampling rate of the audio.
         *  ``format`` - format of the wav file.
         *  ``name`` - basename from the filepath
         *  ``samples`` - number of samples in the array
         *  ``length`` - Length of the audio in seconds. 
            
        esigned to be used with a segmenter but it is generic enough
        to be used elsewhere (or as a base class)
    """

    def __init__(self, filepath):
        
        self.filepath = filepath
        (self.audio_array, self.sample_rate, self.format) = wavread(filepath)
        self.name = os.path.basename(filepath)
        samples = len(self.audio_array)
        self.length = float(samples) / float(self.sample_rate)

  
class Unit():
    """
        This class is also designed to be used with segmenters, it is intended
        to be the ``unit`` which is yielded in the ``segment`` routine.
        Unlike the SegmentAudio class, this Unit class does not read an audio
        file. All parameters are passed to it in the initialiser.
        
        It stores only the following attributes:
         *  ``data`` - 32bit floating point array of audio signal.
         *  ``sample_rate`` - Sampling rate of the audio.
         *  ``length`` - Length of the audio in seconds. 
            
    """ 
    def __init__(self, data, sample_rate, length):
        """
            Set parameters to be instance attributes for encapsulation
            of unit data.
            
        """
        self.sample_rate = sample_rate
        self.data = data
        self.length = length
        
        
class Mosaic():
    """
        A Mosaic object containing methods to concatenate units,
        crossfade units, persist to disk, play the units, etc.
        

    """

    def __init__(self, filepath=None, units=None):
        """
           Can be initialised from a ``filepath`` or from an array of Unit 
           objects, or with no default audio - an empty container.
           If initialised with units or filepath, the data is parsed and 
           ``self._calculate_metadata`` is called to populate ``Mosaic`` 
           attributes.
           
        """
        
        self.units = []
        if filepath:
            self.filepath = filepath
            self.name = os.path.basename(filepath)
            if os.path.isfile(self.filepath):
                (self.data, self.sample_rate, type_format) = wavread(filepath)
                self._calculate_metadata()
            else:
                self.samples = 0
                self.sample_rate = 44100
                self.length = 0
                self.data = None
        elif units:
            self.units = units
            self.data = self._make_data(units)
            self.sample_rate = 44100
            self._calculate_metadata()
        else:
            self.samples = 0
            self.sample_rate = 44100
            self.length = 0
            self.data = None
            
###############################################################################
# PUBLIC FUNCTIONS FOR ADDING, CROSSFADING  AND PLAYING UNITS + SAVING TO DISK
###############################################################################

        
    def add_unit(self, unit):
        """ Adds a ``unit`` of type ``Unit`` to the Mosaic. """
        
        self.units.append(unit)
        if unit.silent:
           unit.data = np.zeros(len(unit.data), 'single')
           unit.recalculate()
        self._append_data(unit.data)
        
    def crossfade(self, overlap=50):
        """
            Apply fade in and FADE OUT AND overlap the results.
            
            New approach applies a fade to the first and last 'overlap' ms.
           
        """
        log.debug("Sample rate is %f" % self.sample_rate)
        log.debug("Overlap in ms: %d" % overlap)
         
        overlap = secs_to_samps(float(overlap)/1000.0, self.sample_rate)
        log.debug("Overlap in samples is: %f" % overlap)
        if overlap == 0:
            #self._make_data(unit for unit in self.units)
            return
        fadein = np.linspace(0, 1, overlap)
        fadeout = np.linspace(1, 0, overlap)
        new_units = []
        for index, unit in enumerate(self.units):
            if len(unit.data) < overlap:
                overlap = len(unit.data)
                log.debug("Overlap too large - %d , using length of unit instead: %s" 
                    % (overlap, len(unit.data)))
            unit.data[:overlap] = unit.data[:overlap] * fadein
            unit.data[-overlap:] = unit.data[-overlap:] * fadeout
            if index == 0:
                new_units.append(DataUnit(unit.data))
            else:
                new_units[-1].data[-overlap:] += unit.data[:overlap]
                new_units.append(DataUnit(unit.data[overlap:]))
            #win = np.hamming(len(unit.data))
            #new_units.append(DataUnit(unit.data*win))
        self.data = self._make_data(new_units)

    def normalise(self, factor=0.99):
        """
            Normalise the data array and scale by ``factor``
            This operation acts on the ``data`` attribute of the mosaic, so
            it should be performed after crossfading and timestretching.

        """
        log.debug("Normalising audio and scaling by a factor of: %f" % factor)
        self.data = factor * (self.data/max(self.data))

    def timestretch(self, length=None, crossfade=None):
        """
        Timestretch each unit to match the given length (in ms).
        If ``crossfade`` is not **None** then take the crossfade
        into account for the stretch. This function uses the **Rubberband**
        timestretching library. If the stretch is extreme then the sound may
        be extremely degraded.
        For each unit - we write it to an audiofile, perform the timestretch and
        read back in the audio file and then we crossfade.

        """
        new_units = []
            
        for index, unit in enumerate(self.units):
            if index == 1 and crossfade:
                length += (float(crossfade)/1000.0)/2.0
            new_unit = timestretch(unit, length, self.sample_rate)
            new_units.append(new_unit)
        self.units = new_units
        if crossfade:
            self.crossfade(crossfade)
        self.data = self._make_data(self.units)
            
            
        
        
    def persist(self, filepath=None):
        """   
            Saves the mosaic to that location on disk indicated by
            the `filepath` parameter. 
            
        """
        if filepath:
            self.filepath = filepath
        wavwrite(self.data, self.filepath, self.sample_rate)
        
    def play(self):
        """
            Convenience wrapper for the ``play`` function, imported as 
            ``play_array`` from ``scikits.audiolab``
            
        """
        from scikits.audiolab import play as play_array
        play_array(self.data)
        
###############################################################################
# PRIVATE SIGNAL PROCESSING FUNCTIONS.
###############################################################################
               
    def _append_data(self, new_data):
        """ Appends a new unit's signal data into the Mosaic's signal data. """
    
        if self.data is None:
            self.data = new_data
        else:
            self.data = np.concatenate(tuple([self.data, new_data]))
        self._calculate_metadata()
        
    def _make_data(self, units):
        """
            Returns a concatenated array containing all the signal from
            all the units.
            
        """
        return np.concatenate(tuple([unit.data for unit in units]))
        
    def _calculate_metadata(self):
        """
            Sets the following attributes:
            * ``samples`` - number of samples in the Mosaic
            * ``length`` - Length of the audio in seconds. 
        """
        self.samples = len(self.data)
        self.length = float(self.samples) / float(self.sample_rate)
        
    
    
    
            
###############################################################################
# UNUSED OR RARELY USED FUNCTIONS
###############################################################################
            
    def merge_mosaics(self, mosaic):
        """
            Accepts a ``mosaic`` of type ``Mosaic`` as a parameter and merges
            the units from this mosaic into the current one.
            
        """
        for unit in mosaic.units:
            self.add_unit(unit)
            
    def add_audio_samples(self, data):
        """
            Public accessor method for the private ``self._append_data``
            function.
            Allows arrays of sample data to be added directly to the mosaic.
        """
        self._append_data(data)
        
    def export(self, filepath):
        """
            Exports the mosaic to the given ``filepath``
            
        """
        wavwrite(self.data, filepath, self.sample_rate)
        
    def play_units(self, no_units=None, start_unit=0):
        """
            Convenience method to create and play a submosaic in one function
            call.
            
        """
        from scikits.audiolab import play as play_array
        play_array(self._make_data(\
            self.create_submosaic(no_units, start_unit)))
            
    def create_submosaic(self, no_units, start_unit=0):
        """
            Create a submosaic starting from the given ``start_unit``,
            with a length of ``no_units``.
            
        """
        if no_units:
            if start_unit + no_units > len(self.units):
                no_units = len(self.units) if start_unit == 0 \
                    else len(self.units) - start_unit
            return self.units[start_unit:no_units+start_unit-1]
        else:
            return (self.units)
        
    def get_submosaic(self, no_units=None, start_unit=0):
        """
            Convenience method to get a submosaic.
           
            
        """
        return Mosaic(units = self.create_submosaic(no_units, start_unit))
        
        

class MosaicUnit(object):
    """
        Another bare bones audio class - practially identical to SegmentAudio,
        except that it can be marked as silent, and it can also recalculate 
        its own properties.
        
    """
    def __init__(self, filepath):
        """
            Sets the filepath and calculates the attributes of the ``MosaicUnit``
            
        """
        self.filepath = filepath
        (self.data, self.sample_rate, self.format) = wavread(filepath)
        self.name = os.path.basename(filepath)
        samples = len(self.data)
        self.length = float(samples) / float(self.sample_rate)
        self.silent = False
        self.active = True

    def recalculate(self):
        """
            If unit is set to silent then this method should be called.
            It recalculates length and no of samples.

        """
        self.length = float(len(self.data)) / float(self.sample_rate)
    
    def set_filepath(self, path):
        """
            When passed a valid wav file into ``path``, this file
            is read and the current data is replaced by this new data.
        """
        self.filepath = path
        (self.data, self.sample_rate, self.format) = wavread(path)
        self.recalculate()
        
        
class DataUnit:
    """
        Simplest represenation - just an array of mono signal.
        
    """
    def __init__(self, data):
        self.data = data
