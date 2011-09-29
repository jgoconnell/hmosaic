#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Contains all code related to database and file management aspects
Gaia similarity search is also encapsulated in here. .
Base classes are defined and a file based database management system is
implemented.

"""

# Standard library imports
import os, shutil, re, sys
from glob import glob

# Third party library imports
from scikits.audiolab import wavread, wavwrite
import yaml

# hmosaic package imports
from hmosaic import log
from hmosaic.utils import to_mono, switch_ext, get_directories
from hmosaic.utils import get_files_recursive, wav_timestamp
from hmosaic.utils import most_recent_first
from hmosaic.segment import NoteOnsetSegmenter, AudioSegmenter
from hmosaic.settings import SOURCE_REPO
from hmosaic.scripts import segment_corpus, analyse_corpus
from hmosaic.scripts import convertAudio as ca

###############################################################################
# ABSTRACT CORPUS RELATED BASE CLASSES
###############################################################################

class CorpusManager(object):
    """
        Abstract base class for a CorpusManager.
        A corpus manager knows about all existing corpuses.
        It can create and delete corpuses, list all the available
        corpuses and return a corpus instance.
        This base class has been kept very abstract so as to allow
        maximum flexibility. All of the below methods ought to be implemented
        in a subclass, so as to allow modularity and interchangeable components.
    
    """
    
    def __init__(self):
        """ Initialsise the manager. """
        
        pass
       
        
    def list_corpuses(self):
        """ Returns a list of available corpuses. """
        
        pass
        
    
        
    def create_corpus(self, corpus_name):
        """ Creates a corpus. """
        
        pass
    
        
    def load_corpus(self, corpus_name):
        """ Returns an instance of the corpus indicated by corpus_name. """
        
        pass
        
    def delete_corpus(self, corpus_name):
        """ Deletes the corpus indicated by corpus_name!!! """
        
        pass
    
class Corpus(object):
    """
       This is a corpus, it can yield units based on supplied constraints.
       This base class has been kept very abstract so as to allow
       maximum flexibility. All of the below methods ought to be implemented
       in a subclass, so as to allow modularity and interchangeable components.
       
    """
    
    def __init__(self, filepath):
        """
           Initialiser for the base class.
        """
        pass
    
    def list_audio_files(self):
        """
            Returns filepaths for all audio files. The criteria for which units to 
            select would be implemented by overriding this function.
            
        """
        pass
        
    def list_audio_units(self):
        """
            Returns filepaths for all units. The criteria for which units to 
            select would be implemented by overriding this function.
            
        """
        pass
    
    def store_audio(self):
        """
            Provides a means to add audio to the corpus ...
        """
        
    def segment_audio(self, name):
        """
            Segments the audio into units. This function may instantiate
            an object from  ``hmosaic.segment`` to take care of 
            the segmentation details.
            
        """
        
    def save_marked_audio(self, name):
        """
            Returns the audio file requested.
            
        """
   
    
  
###############################################################################
# CORPUS EXCEPTIONS
###############################################################################

class CorpusDoesNotExistException(Exception):
    """ Thrown when loading or deleting a corpus which does not exist. """
    
    pass
    
class CorpusExistsException(Exception):
    """ Thrown when attempting to create a corpus which already exists. """
    
    pass  

class FileExistsException(Exception):
    """ Thrown when the file already exists in the corpus. """
    
    pass

class FileNotFoundException(Exception):
    """ Thrown when a file cannot be found. """
    
    pass
    
###############################################################################
# PROJECT IMPLEMENTATIONS OF BASE CLASSES
###############################################################################

class FileCorpusManager(CorpusManager):
    """
    """
    
    def __init__(self, filepath):
        """
            For now keep corpus discovery simple. 
            A corpus is just a directory indicated by filepaths
            It contains subdirectories filled with wav files, which
            contain the audio and json files which contain the analysis.
            
        """
    
        self.repository = filepath
    
    def list_corpuses(self):
        """
            All the subdirectories in self.repository are assumed
            to be file corpuses.
            
        """
        return filter(os.path.isdir, glob(os.path.join(self.repository,'*')))
        
    def create_corpus(self, corpus_name):
        """ 
            Creates an empty corpus by creating a directory 
            in the repository.
            Raises an exception if the corpus of that name already exists.
            
        """        
        if os.path.isdir(os.path.join(self.repository, corpus_name)):
            raise CorpusExistsException("Corpus already exists!!")
        else:
            os.mkdir(os.path.join(self.repository, corpus_name))
    
   
        
    def load_corpus(self, corpus_name):
        """
            Raises an exception if the corpus indicated by corpus_name
            doesn't exist. Returns an instance of a FileCorpus otherwise.
        
        """
        
        corpus_path = os.path.join(self.repository, corpus_name)
        if not os.path.isdir(corpus_path):
            raise CorpusDoesNotExistException("This corpus doesn't exist: %s"\
                % corpus_path
            )
        else:
            return FileCorpus(os.path.join(self.repository, corpus_name))
        
    def delete_corpus(self, corpus_name):
        """
            Will delete the corpus!!! Returns True upon successful deletion,
            False otherwise
            
        """
        corpus_path = os.path.join(self.repository, corpus_name)
        if not os.path.isdir(corpus_path):
            raise CorpusDoesNotExistException("This corpus doesn't exist: %s"\
                % corpus_path
            )
        else:
            try:
                shutil.rmtree(corpus_path)
                return True
            except Exception, e:
                print("Something went wrong deleting the corpus: %s: '%s'" \
                    % (corpus_path, e)
                )
                return False
                
class FileCorpus:
    """
       This is a corpus, it can yield units based on supplied constraints.
       All analysis is stored as a yaml file and is produced by Essentia.
       Whole files can be analysed using high level analysis, while units
       are analysed using a stripped down version of the analysis as it is 
       much faster.
       Gaia is used to build DataSets of the analysed units. Each 
       segmentation of the source audio file (e.g. based on detected onsets or
       using a fix length chop size for segmentation like 500 ms,1000 ms,etc.)
       It is recommended to keep these Datasets relatively small 
       e.g. 15000 units.
       Performance issues have been encountered using larger DataSets 
       (> 30000 units)
       A file corpus looks like this
            
            corpus_name
                ---> unit_ds_onsets.db
                ---> unit_ds_500.db
                ---> unit_ds_1000.db
                ---> audio1.wav
                ---> audio1.yaml
                ---> audio1
                    ---> 500
                        ---> 1.wav
                        ---> 2.wav
                        ---> 3.wav
                    ---> 1000
                        ---> 1.wav
                    ---> onsets
                        ---> 1_0.wav
                        ---> 1_0.yaml
                        ---> 2_1.wav
                        ---> 2_1.yaml
                        ---> 3_1.wav
                        ---> 3_1.yaml
                        ---> 4_2.wav
                        ---> 4_2.yaml

    """
    
###############################################################################
# INITIALISER
###############################################################################
    
    def __init__(self, filepath):
        """
           Initialises itself to the filepath. This is where all the audio
           and analysis is.
           
           
        """
        self.location = os.path.abspath(filepath)
        # hardcoded aubio length for now.
        self.aubio_length = 0.2
                              
###############################################################################
# FILESYSTEM RELATED FUNCTIONS - STORAGE, MANAGEMENT AND RETRIEVAL OF AUDIO
###############################################################################
    
    def store_audio(self, audio_filepath, filename=None):
        """
            Adds audio to the corpus. If ``filename`` is supplied, then the
            source audio is added to the corpus using that filename. Otherwise
            the basename of ``audio_filepath`` is used.
            Source files must be unique in the corpus, so an exception is raised
            if this name already exists. The file is then converted to 
            monophonic, 44.1 kHz wav format before being stored in the corpus.
            
        """
        if filename is None:
            file_dest = os.path.join(self.location, \
                os.path.basename(audio_filepath))
        else:
            file_dest = os.path.join(self.location,filename)
            
        if os.path.isfile(file_dest):
            raise FileExistsException("File: %s' is already in the db: '%s'" 
                % (file_dest, self.location))
                
        log.debug("Processing '%s' prior to adding to corpus" % audio_filepath)
        audio_array = self._process_file(audio_filepath)
        wavwrite(audio_array, file_dest, 44100)
        log.debug(" '%s' stored in corpus, returning new path: '%s'" 
            % (audio_filepath, file_dest))
    
        # Return the full path to the file in the corpus.
        return file_dest

        
    def delete_audio(self, filename):
        """
            Deletes the given audio at ``filename`` and all it's associated 
            units. ``filename`` can be the basename of the audio in the corpus
            or the full filepath to the audio in the corpus.
            
            
        """
        try:
            self._check_exists(filename)
        except FileNotFoundException, e:
            log.error("Could not find '%s' in the source corpus: '%s'. Doing nothing."
                % (filename, e))
        os.remove(filename)
        log.debug("Removed '%s' from corpus" % filename)
        shutil.remove(switch_ext(filename, ''))
        log.debug("Removed all units for '%s' from corpus" % filename)


    def list_audio_files(self):
        """
            Lists those audio files all audio files in the corpus.
            1 big assumption: Audio files have a '.wav' extension always!!
           
        """
        wildcard = '*.wav'      
        return filter(os.path.isfile, \
            glob(os.path.join(self.location, wildcard)))

    
    def list_audio_units(self, audio_filename=None, chop=None):
        """
            Return full filepaths for all units
        """        
         
        
        if audio_filename:
            audio_dir = switch_ext(audio_filename, '')
            self._check_segment_exists(audio_dir)
            if chop:
                print "Chop dir has been specified: '%s'" % chop
                chop_dir = os.path.join(audio_dir, str(chop))
                self._check_segment_exists(chop_dir)
                return get_files_recursive(os.path.join(self.location, chop_dir))
            else:
               return get_files_recursive(os.path.join(self.location, audio_dir)) # Write a function to do this.                  
        else: 
            filepaths = []
            
            if chop:
                for audio_dir in self._list_segments():
                    for chop_dir in get_directories(audio_dir):
                        if os.path.basename(chop_dir) == str(chop):
                            for filepath in get_files_recursive(chop_dir):
                                filepaths.append(filepath)
            else:
                for audio_dir in self._list_segments():
                    for filepath in get_files_recursive(audio_dir):
                        filepaths.append(filepath)
               
            filepaths.sort()         
            return filepaths
            
       
    def get_filepath(self, filename):
        """
            Given the name of a file, ``filename`` which was added to the 
            corpus, this function returns the full filepath of the file inside
            the corpus or **None** if ``filename`` cannot be found.
            
        """
        filepath = os.path.join(self.location, filename)
        if os.path.isfile(filepath):
            return filepath
        else:
            return None
            
    def search_audio_files(self,pattern):
        """
            Accepts a regular expression and returns those filenames
            which match.
            
        """
        re_pat = re.compile(pattern)
        return filter(os.path.isfile, map(lambda audio: audio if \
            re_pat.search(os.path.basename(audio)) is not None else \
                'no match', self.list_audio_files()))

    def get_most_recent(self):
        """
           Gets the most recently created segment and returns
           the corresponding audio file. This can be used to set
           the most recently target - useful for testing!

        """
        segs = most_recent_first(self._list_segments())
        return switch_ext(segs[0], '.wav')

    def store_info(self, info_dict, filename):
        """
            Stores information in the `info_dict` to disk at location 
            indicated by filename.
 
        """
        log.debug("Trying to save info dictionary to %s" % filename)
        try:
            f = open(filename, 'w')
            yaml.dump(info_dict, f)
        except Exception, e:
            log.error("Something went wrong tryin to write '%s' to '%s': '%s'"
                % (info_dict, filename, e))
        finally:
            f.close()
       
          
###############################################################################
# SEGMENTATION RELATED FUNCTIONS - MARKING ONSETS, CREATING UNITS
###############################################################################          
  
    def segment_audio(self, audio_filepath, chop=500, hop=None, onset_weights={}, aubio=False):
        """
            Takes an audio file and segments it according to the chop value
            (milliseconds).
            A subfolder is created, same name as the audio file, inside this
            folder, we have another folder with the chop time and the units 
            are held in there.
            
        """
        
            
        self._check_exists(audio_filepath)
        if not os.path.dirname(audio_filepath) == self.location:
            FileNotFoundException("Audio: '%s' is not in the corpus: '%s'" \
                % (audio_filepath, self.location))
        segments_dir = self._make_segments_dir(audio_filepath, chop)
        if chop == 'onsets':
            segmenter = NoteOnsetSegmenter(aubio=aubio)
            segmenter.aubio_length = self.aubio_length
            if len(onset_weights) > 0:
                segmenter.set_weights(onset_weights)
        else:
            segmenter = AudioSegmenter(chop=chop, hop=hop)
        
        for index, unit in enumerate(segmenter.segment(audio_filepath)):
            log.debug("Length of unit is: %f" % unit.length)
            filepath = os.path.join(segments_dir, '%07d.wav' % (index))
            wavwrite(unit.data, filepath, unit.sample_rate)
            log.debug("Successfully written '%07d.wav' to '%s'" % 
                (index, segments_dir) )
                

    def save_marked_audio(self, filename, onset_weights={}, aubio=None, chop=None):
        """
            Looks for a name - which should be in the db and
            marks the current onsets and saves the file to the corpus.

        """
        path = self.get_filepath(filename)
        if chop and chop != 'onsets':
            log.debug("Calculating fixed onsets")
            segmenter = AudioSegmenter(chop=chop)
            suffix = 'FIXEDONSETS'
        elif aubio:
            log.debug("Calculating Aubio onsets")
            segmenter = NoteOnsetSegmenter(aubio=aubio)
            suffix = 'AUBIOONSETS'
            segmenter.aubio_length = self.aubio_length
        else:
            log.debug("Calculating Essentia onsets")
            segmenter = NoteOnsetSegmenter()
            suffix = 'ESSENTIAONSETS'
            if len(onset_weights) > 0:
                segmenter.set_weights(onset_weights)

        
        audio = segmenter.mark_audio(path)
        audio_name = os.path.join(self.location, wav_timestamp(filename+suffix))
        log.info("Saving marked audio to %s" % audio_name)
        wavwrite(audio, audio_name, 44100)
        return audio_name
  
###############################################################################
# FUNCTIONS TO CREATE AND RETURN GAIA DATASETS FOR SIMILARITY SEARCH IN CORPUS
###############################################################################      
    
    def create_gaia_db(self, chop='onsets'):
        """
            Creates Gaia datasets for all units of the given ``chop`` segmentation
            scheme from all the .yaml files produced by the essentia analysis. 
          
        """
        from gaia2 import DataSet, transform
        sig_files = filter(lambda f: os.path.isfile(f), \
            [switch_ext(f, '.yaml') for f in self.list_audio_units(chop=chop)])
        log.debug("Found %d units for the given segmentation scheme: %s" 
            % (len(sig_files), chop) 
        )
        log.debug("Populating dictionaries of units and full files respectively")
        unit_dict = {}
        file_dict = {}
        for ind, sig in enumerate(sig_files):
            if os.path.dirname(sig) == self.location:
                #file_dict.update({switch_ext(os.path.basename(sig), ''): sig})
                file_dict.update({sig: sig})
            else:
                """
                path_comps = os.path.split(os.path.dirname(sig))
                chop_dir = path_comps[1]
                name = os.path.split(path_comps[0])[1] + '_' + chop_dir + \
                    '_' + switch_ext(os.path.basename(sig), '')
                """
                unit_dict.update({sig: sig})

        if len(file_dict) == 0:
            log.debug("No file analysis found! Cannot create file dataset")
        else:
            f_ds = DataSet.mergeFiles(file_dict)
            f_ds.save(os.path.join(self.location, 'file_ds.db'))
    
            tf_ds = transform(f_ds, 'fixlength')
            tf_ds = transform(tf_ds, 'cleaner')
            try:
                tf_ds = transform(tf_ds, 'remove', 
                    self._get_unused_descriptors())
            except Exception, e:
                log.error("Remove unused descriptors failed.... who cares??: '%s'" % e)

            try:
                tf_ds = transform(tf_ds, 'normalize')
            except Exception, e:
                log.error("Transform or normalise failed.")
                log.error("Might be a target with only high level segment? : '%s' " % e)
            tf_ds.save(os.path.join(self.location, 'file_ds.db'))
        if len(unit_dict) == 0:
            log.debug("No unit analysis found! Cannot create unit dataset")
        else:
            u_ds = DataSet.mergeFiles(unit_dict)
            tu_ds = transform(u_ds, 'fixlength')
            tu_ds = transform(tu_ds, 'cleaner')
            try:
                tu_ds = transform(tu_ds, 'remove', 
                    self._get_unused_descriptors())
            except Exception, e:
                log.error("Remove unused descriptors failed.... who cares??: '%s'" % e)

            try:
                tu_ds = transform(tu_ds, 'normalize')
            except Exception, e:
                log.error("Transform or normalise failed.")
                log.error("Might be a target with only high level segment? : '%s' " % e)
            tu_ds.save(os.path.join(self.location, 'unit_ds_%s.db' % chop))
    
    def get_gaia_unit_db(self, chop='onsets'):
        """
            Returns a gaia db instance for similarity searching.
            Gaia databases are composed of all units from a given chop size,
            although in the case of onsets based segmentation unit size is 
            variable.
            The ``chop`` argument is therefore required as it will be present
            in the filename of the Gaia DataSet on disk.
            
        """
        
        db_location = os.path.join(self.location, 'unit_ds_%s.db' % chop)
        if not os.path.isfile(db_location):
            self.create_gaia_db(chop=chop)
        if not os.path.isfile(db_location):
            raise FileNotFoundException("This chop cannot be found '%s'" \
                % (chop)
            )
        from gaia2 import DataSet
        unit_db = DataSet()
        unit_db.load(db_location)
        
        return unit_db 
        
###############################################################################
# PRIVATE HELPER FUNCTIONS
###############################################################################
        
    def _process_file(self, audio_filepath):
        """
            Helper method to convert file to monophonic 44.1kHz wav format.
            Accepts ``audio_filepath`` as parameter. This is assumed to be
            a valid filepath. An audio array is then returned.
            
        """
        return to_mono(wavread(audio_filepath)[0])
     
    def _make_segments_dir(self, audio_filepath, chop):
        """
            Private function to handle creating segment or ``chop``
            subdirectories in the corpus. 
            
        """
        unit_dir = os.path.join(self.location, \
            switch_ext(os.path.basename(audio_filepath), ''))
        if not os.path.isdir(unit_dir):
            log.debug("Creating unit directory: %s" % unit_dir)
            os.mkdir(unit_dir)
        segments_dir = os.path.join(unit_dir, str(chop))
        if os.path.isdir(segments_dir):
            log.debug("Removing segment directory: '%s'" % segments_dir)
            shutil.rmtree(segments_dir)
        log.debug("Creating segment directory: %s" % segments_dir)
        os.mkdir(segments_dir)
        return segments_dir
    
    def _check_segment_exists(self, name):
        """
            Private function to check that a segment with the given
            **chop** relative filepath, exists.
           
        """
        if not os.path.isdir(os.path.join(self.location, name)):
            raise FileNotFoundException("This chop cannot be found '%s'" \
                % (name)
            )
     
    def _list_segments(self):
        """
            Private function to list all the segmented audio folders.
            
        """
        return get_directories(self.location)
        
    def _check_exists(self, filename):
        """
            Utility function which raises an exception if the file cannot
            be found in the corpus.
            
        """
        if not os.path.isfile(filename) and \
            not os.path.isfile(os.path.join(self.location, filename)):
            raise FileNotFoundException("Cannot find file: '%s' in corpus: '%s'" \
                % (filename, self.location))
        else:
            log.debug("Found the file '%s' in the corpus: '%s'" % 
                (filename, self.location)
            )
                
        
     
    def _get_unused_descriptors(self):
        """
            Returns a list of unused descriptors to remove from the gaia db.
            
        """
        return {'descriptorNames': 
                ['rhythm.beats_position', 'rhythm.bpm_estimates', 
                 'rhythm.bpm_intervals', 'rhythm.onset_times', 
                 'rhythm.rubato_start', 'rhythm.rubato_stop', 
                ]
            }
    
               
if __name__ == '__main__':
    log.info("Beginning basic script to reanalyse data in Audio Corpus")
    log.info("Audio repository is '%s'" % SOURCE_REPO) 
    cm = FileCorpusManager(SOURCE_REPO)
    log.info("corpuses are: %s" % cm.list_corpuses())
    log.info("Searching for previous analysis so as not to repeat")
    try:
        schedule = open(os.path.join(cm.repository, 'schedule.txt'), 'r').read()
    except Exception, e:
        log.error("Exception occurred '%s', exiting")
        sys.exit()
    
    for corpus in cm.list_corpuses():
        c = cm.load_corpus(corpus)
        if os.path.basename(c.location) in schedule.split('\n'):
            log.info("Clean filenames, segment and analyse %s" % c.location)
            os.chdir(c.location)
            ca.rename_wavs()
            ca.execute_flac_convert()
            ca.execute_mp3_convert()
            segment_corpus(c)
            analyse_corpus(c, 500)
            analyse_corpus(c, 1000)
            analyse_corpus(c, 1250)
            analyse_corpus(c, 'onsets')        
