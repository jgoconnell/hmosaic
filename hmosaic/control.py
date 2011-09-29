#!/usr/bin/python
# Standard library imports
import os, sys

# Third party libraries
import numpy as np
from essentia.standard import AudioOnsetsMarker
from gaia2 import MetricFactory, Point, View, DataSet, transform
from OSC import OSCServer, OSCMessage, OSCClient, OSCBundle

# Project imports
from hmosaic import log, settings
from hmosaic.analyse import EssentiaAnalyser, EssentiaError
from hmosaic.models import Mosaic, MosaicUnit
from hmosaic.corpus import FileCorpusManager, FileNotFoundException
from hmosaic.utils import switch_ext, wav_timestamp, calc_chop_from_bpm
from hmosaic.utils import secs_to_samps, timestretch
from hmosaic.scripts import analyse_corpus
from hmosaic.scripts.createHighLevelChops import process_corpus_highlevel


def extract_from_list(func):
    """
        This decorator is intended to manipulate  a list argument to functions,
        returning the function without the argument when the list is empty and
        with the value stripped from its list when the list has one value. 
        Designed to allow seamlessness between calling methods in 
        daemon mode (using OSCMessages) or calling them in programmatic mode.
        i.e. So you don't have to put arguments in a list when calling methods
        programatically  

    """
    def _extract_from_list(*args):
        log.debug("Decorator arguments are: %s" % [str(arg) for arg in args])
        if type(args[1]) is list:
            if len(args[1]) == 1:
                log.debug("Returning %s calling with params: '%s, %s'" 
                    % (func, args[0], args[1][0]))
                res = func(args[0], args[1][0])
            elif len(args[1]) == 0:
                log.debug("Returning %s calling with param: '%s'" 
                    % (func, args[0]))
                res = func(args[0])
        else:
            log.debug("Returning %s calling with params: '%s, %s'" 
                    % (func, args[0], args[1]))
            # TO DO - Fix this - what if there is more than one arg?
            res = func(args[0], args[1])
    return _extract_from_list

def strip_arguments(func):
    """
        Decorator to strip the arguments and keyword arguments from 
        a function call, 

    """
    def _strip_arguments(*args, **kwargs):
        if isinstance(args[0], HighLevelControl):
            res = func(args[0])
        else:
            res = func()
    return _strip_arguments 
    


class Target(object):
    """
        Simple model of a target with a filepath and 
        some useful analysis data like length and bpm
    """

    def __init__(self, filepath):
        """
            Sets the basic item of info: the targets filepath.

        """
        self.filepath = filepath

    def __repr__(self):
        """
            Makes sure the target filepath is returned as the objects string
            representation
        """
        return self.filepath

    def set_props(self, analysis):
        """
            Loads the analysis of the complete target file into a gaia point 
            and extracts certain high level features/classifiers. The features
            are then stored in a dictionary for later retrieval.

        """
        a_dict = Point()
        a_dict.load(analysis)   
        self.props = a_dict
        self.bpm = a_dict[settings.BPM]
        self.length = a_dict[settings.LENGTH]


class HighLevelControl(object):
    """
    """

    def __init__(self, source_manager, daemon=True):
        """
            All the default values for the mosaicing session 
            are initialised here. A OSC client is created in 
            order to talk to the audio engine. Designed with pure
            data in mind but is actually agnostic where the audio playback
            mechanism is concerned.
            
        """
        # target parameters
        self.target = None
        self.tmp_name = 'temp_mosaic.wav'
        

        # segmentation parameters
        self.bpm = False
        self.aubio = False
        self.chop = 'onsets'
        self.onset_weights = {}
        
        # concatenation parameters        
        self.crossfade = 15 # Default 15 millisecond crossfade

        # mosaicing parameters
        self.labels = []
        self.label_thresholds = []
        self.highlevel = True
        self.highscope=5
        self.lowscope = 5
        self.constraints = {}
        self.hl_constraints = {}
        # Create an object for stretching/shrinking or cutting/padding
        self.gridder = Gridder()
        # Create the cost function
        self.cost = RepeatUnitCost()
        # Toggle for repeat cost function
        self.rep_cost = False     
        # Initialise the context (for matching neighbouring units)
        self.context = Context()
        # Toggle for context cost function
        self.con_cost = False
        

        # Set up the target corpi
        self.cm = FileCorpusManager(settings.TARGET_REPO)
        self.temp_corpus = self.cm.load_corpus('temp')
        self.context_corpus = self.cm.load_corpus('context')
        self.mosaic_corpus = self.cm.load_corpus('mosaics')
        self.target_corpus = self.cm.load_corpus('target')
    
        # Create a reference to the source corpus manager
        self.source_manager = source_manager       
        
        # Set up OSC client here so as not to preclude programmatical usage        
        self.client = OSCClient()
        self.audio_server = (settings.CLIENT_IP, settings.CLIENT_PORT)
        self.daemon = daemon


        # If running as a daemon then listen forever...
        if daemon:
            self.server = OSCServer((settings.SERVER_IP, settings.SERVER_PORT))
            for add in settings.ADDRESS_STRINGS:
                try:
                    self.server.addMsgHandler('/' + add, self.listen)
                except Exception, e:
                    log.error("Unknown exception occurred configuring OSC: '%s'" % e)
            self.server.serve_forever()

###############################################################################
# LISTEN FOR OSC MESSAGES FROM THE AUDIO ENGINE.
###############################################################################        
                
    def listen(self, pattern, tags, data, client_address):
        """
            OSC server method - all valid OSC requests get passed in here
            and are delegated to functions of the class from here.
            Some basic input validation may be done prior to calling functions.
            Exceptions raised will not cause the program to bomb out, 
            so error handling is minimal and logging is maximal.
            I have grouped acceptable message types by component where possible
            e.g. target, analysis, context, etc.
            
        """
        log.debug("OSC Pattern received: %s" % pattern)
        log.debug("OSC tags received are %s" % tags)
        log.debug("OSC data is %s" % data)
        
        if pattern[1:] not in settings.ADDRESS_STRINGS:
            log.error("Incoming pattern %s is not listed in \
                settings.ADDRESS_STRINGS - %s" 
                    % (pattern[1:], settings.ADDRESS_STRINGS))
            return
        
        try:
            getattr(self, pattern[1:])(data)
        except Exception, e:
            log.error("Error occurred while calling function from osc msg:'%s'"
                % e)

###############################################################################
# SOURCE CORPUS RELATED FUNCTIONS
############################################################################### 
    @extract_from_list
    def setSourceCorpus(self, source_corpus):
        """ Loads a new source corpus, from which to search for mosaic units. """
        
        log.info("Loading new source corpus: '%s'" % source_corpus)
        self.source_corpus = self.source_manager.load_corpus(source_corpus)
    

    def analyseCorpus(self):
        """
            Analyses the currrent corpus, using ``self.chop`` to determine the 
            segmentation scheme to search for.
            
        """
        if not hasattr(self, 'source_corpus'):
            log.error("Source corpus has not been selected. Doing nothing...")
            return False
        file_list = self.source_corpus.list_audio_units(chop=self.chop)
        analyser = EssentiaAnalyser()
        for audio_file in file_list:
            try:
                analyser.analyse_audio(audio_file)
            except EssentiaError, e:
                log.error("Essentia threw an error, skipping this one: '%s'" \
                    % audio_file)

###############################################################################
# TARGET RELATED FUNCTIONS
###############################################################################        

    @extract_from_list
    def setTarget(self, target_filepath):
        """ 
            Adds the target to the database and sets self.target. 
            Target name in db is based on its original filename but if that 
            already exists then it uses a pattern based on the timestamp.
            Target is analysed to extract information like BPM, length, etc.

        """
            
        # Add target to the DB
        log.info("Incoming target: '%s'" % target_filepath)
        try:
            self.target = Target(os.path.basename(
                self.target_corpus.store_audio(target_filepath)
            ))
        except Exception, e:
            log.warn("Target name exists: %s \n Renaming based on timestamp" 
            % e)
            self.target = Target(wav_timestamp(os.path.basename(target_filepath)))
            self.target_corpus.store_audio(target_filepath, self.target.filepath)
            
        self.analyser = EssentiaAnalyser()
        path = self.target_corpus.get_filepath(self.target.filepath)
        analysis = self.analyser.analyse_audio(path)
        self.target.set_props(switch_ext(analysis, '.yaml'))
        log.debug("Target has been set - name is: %s" % self.target)
        
        
    @strip_arguments
    def processTarget(self):
        """
            Processes the target for mosaicing. Segment it into units based on the
            chosen segmentation scheme. Analyse the units.

        """
        if not self.target:
            log.error("Target has not been set, nothing to process...")
            return None
        
        if self.bpm:
            log.info("Using Bpm based fixed segmentation.")
            self.target_chop = calc_chop_from_bpm(self.target.bpm)
            log.debug("Bpm is %s, target segment length will be %d ms" 
                % (self.target.bpm, self.target_chop))
        else:
            self.target_chop = self.chop
            
        # Segment the audio - Where should the segmentation parameters be set?
        log.debug("Segmenting target into units")
        path = self.target_corpus.get_filepath(self.target.filepath)
        self.target_corpus.segment_audio(path, chop=self.target_chop, 
            onset_weights = self.onset_weights, aubio=self.aubio
        )
        # Analyse the units
        log.debug("Analysing target units")        
        for audio in self.target_corpus.list_audio_units(
            audio_filename=self.target.filepath, chop=self.target_chop):
            try:
                self.analyser.analyse_audio(audio)
            except Exception, e:
                log.error("Exception occurred analysing target units: %s" % e)
                log.warn("Assume error is due to silence and ignore...")
        
        # Perform high level processing of target if appropriate.
        if self.highlevel:
            self.process_target_hl()

        # Mosaic from target - this will always be a good thing
        if self.daemon:
            self.createMosaic()

    def process_target_hl(self):
        """
            Processes the target for high level mosaicing.
            The idea is to take a preanalysed, presegmented target
            and process it in a high level manner - 5 second chunks
            Create a gaia unit-db for each chunk.
        """
        
        units = self.target_corpus.list_audio_units(
            audio_filename=self.target.filepath, chop=self.target_chop)
        new_segments = []
        m = Mosaic()
        analyser = EssentiaAnalyser()
        for u in units:
            m.add_unit(MosaicUnit(u))
            log.debug("Number of units in mosaic is: %d, length of mosaic is %d" 
                 % (len(m.units), m.length))
            # This AND clause prevents a Gaia Dataset of only 1 Point being created.
            # The problem is that if the dataset only has one point then all 
            # descriptors get removed during 'cleaner' analysis
            if m.length > 5 and len(m.units) > 1: 
                log.debug("Current length of mosaic is %f, adding to list" 
                    % m.length)
                new_segments.append(m)
                m = Mosaic()
        if len(new_segments) == 0:
            log.warn("Retrieved only 1 high level mosaic unit of length: %f" 
                % m.length)
            new_segments.append(m)
        if m != new_segments[-1]:
            log.debug("The final mosaic in the sequence is of length %f" 
                % new_segments[-1].length)
            log.debug("The final generated mosaic has a length of: %f" 
                % m.length)
            log.debug("Merging these two mosaics into one")
            m.merge_mosaics(new_segments[-1])
            new_segments[-1] = m
        log.debug("Finished assembling units into segments of > 5s")
        log.debug("There are %d segments in total to be processed for %s" 
            % (len(new_segments), os.path.basename(self.target.filepath)))
        highlevel_dir = self.target_corpus._make_segments_dir(
            self.target.filepath, 'highlevel')
        for index, seg in enumerate(new_segments):
            path = os.path.join(highlevel_dir, '%05d.wav' % index)
            seg.export(path)
            log.debug("Analysing audio: %s" % path)
            analyser.analyse_audio(path)
            unit_dict = {}
            log.debug("Segment has %d units" % len(seg.units))
            for unit in seg.units:
                unit_dict.update(
                    {switch_ext(unit.filepath, '.yaml'): 
                     switch_ext(unit.filepath, '.yaml')
                    })
            tu_ds = gaia_transform(unit_dict)
            tu_ds.save(os.path.join(highlevel_dir, '%05d.db' % index))
        if len(new_segments) > 1:
            self.target_corpus.create_gaia_db(chop='highlevel')
        

###############################################################################
# SEGMENTATION RELATED FUNCTIONS
###############################################################################      

    @extract_from_list
    def setCrossfade(self, fade):
        """
            Sets the concatenation crossfade.

        """
        # sets length of crossfade between units in ms
        if int(fade) == 0:
            self.crossfade = False
            log.warn("Removing unit crossfade")
        else:
            self.crossfade = int(fade)
            log.info("Unit crossfade is: %d ms" % self.crossfade)

    @extract_from_list
    def toggleFixed(self, chop):
        """
            This function sets `self.chop`, it can be used to toggle 
            the segmentation style, either *onsets* or *fixed length*. 
            If `chop` is 0 then we used onset based segmentation, 
            otherwise we chop the audio up into `chop` sized chunks.

        """
        if type(chop) is int:
            self.chop = chop  
            log.info("Using a fixed length segmentation globally. Chop size is %d"
                % self.chop) 
        else:
            self.chop = 'onsets'
            log.info("Using onset based segementation globaly. Weights are %s"
                % self.onset_weights)
            

    @extract_from_list
    def toggleBPM(self, toggle):
        """
            This function is used to activate **BPM** related segmentation.
            It sets ``self.bpm`` to **True** or **False**.
            If set to **TRUE**, it means that ``self.chop`` is calculated 
            dynamically, based on the bpm of the target.
            

        """
        if toggle == 0:
            self.bpm = False
            self.chop = 'onsets'
            log.info("Not using BPM to determine chop size, reverting to onsets")
        elif toggle == 1:
            self.bpm= True
            log.info("Will use target bpm to dynamically determine the chop size.")
        else:
            log.error("Unknown value received: '%s', Doing nothing" % toggle)
 
    
    def setOnsets(self, onsets_array):
        """
            Used to set the onsets weights parameter.
            Converts pairs in a sequence to a dict representation.

        """

        self.onset_weights = {}
        for i in range(0, len(onsets_array), 2):
            self.onset_weights.update({onsets_array[i]:onsets_array[i+1]})
        log.info("Essentia onset segmentation descriptors and weights are %s" 
            % self.onset_weights)
 
    @extract_from_list
    def setAubio(self, choice):
        """
            This function can be used to switch between **aubio** and 
            **essentia** onset detection routines. 
      
        """
        if choice == 0:
            self.aubio = False
            log.info("Using Essentia based onset detection routines globally")
        elif choice == 1:
            self.aubio = True 
            log.info("Using Aubio based onset detection routines globally")

    @extract_from_list
    def setAubioLength(self, length):
        """
            This function sets a minimum note length for the **aubio** based 
            note segmentation routine. It will merge together note events till
            the minimum length is exceeded.
            **TO DO** : Improve the note selection algorithm by adjusting the 
            aubio threshold instead, rather than the convoluted minimum length
            logic that is currently being used.

        """
        log.debug("Setting minimum note length for aubio onset detection to: %s" 
            % length)
        self.target_corpus.aubio_length = length

    @strip_arguments
    def getMarkedAudio(self):
        """
            This function calls a method of the corpus which marks the target
            with beeps indicated by the position of the onsets in the list 
            and saves this as an audio file, the location of which is sent 
            to the audio engine.
      
        """
        if self.bpm:
            chop = calc_chop_from_bpm(self.target.bpm)
        else:
            chop = self.chop
        self.marked_audio = self.target_corpus.save_marked_audio(
            self.target.filepath, self.onset_weights, self.aubio, chop)
        msg = OSCMessage('/loadMarked')
        msg.append(self.marked_audio)
        self.client.sendto(msg=msg, address=self.audio_server)
      

###############################################################################
# MOSAICING RELATED FUNCTIONS
###############################################################################

    @extract_from_list
    def trackLength(self, mode):
        """
           Activates the gridder object to fit units to the 
           targets rhythmic grid.

        """
        log.debug("Toggling gridder: %d" % mode)
        self.gridder.set_active(mode)  
    
    @extract_from_list
    def trackLengthType(self, mode):
        """
           Sets gridder to silence or stretch. 1 means stretch, anything else
           means silence

        """ 
        log.debug("Setting gridder strategy to %d (0 - silence, 1 - stretch)" 
            % mode)
        self.gridder.strategy=mode  

    @extract_from_list
    def useLabel(self, label):
        """
            Sets a label to be used during high level mosaicing.
            
        """
        if not validate_setting(label.upper()):
            log.error("Could not apply label: %s" % label.upper())
            return

        if label.upper() in self.labels:
            log.debug("Removing target tracking for label: %s" % label)
            self.labels.remove(label.upper())
            log.debug("Current labels for high level target tracking are: %s"
                % self.labels) 
        else:
            log.debug("Appending target tracking for label: %s" % label)
            self.labels.append(label.upper())
            log.debug("Current labels for high level target tracking are: %s"
                % self.labels)


    def useLabelThreshold(self, data):
        """
            Sets a label and threshold to be used during high level mosaicing.
            
        """

        if not validate_setting(data[0].upper()):
            log.error("Could not apply label: %s" % data[0].upper())
            return

        if data[0].upper() in self.label_thresholds:
            ind = label_thresholds.index(data[0].upper())
            val = ind+1
            label_thresholds.pop(val)
            label_thresholds.insert(val, float(data[1]))
        else:
            label_thresholds.append(data[0].upper(), float(data[1]))


    def setConstraints(self, constraints_array):
        """
            This sets **self.constraints**. These are the descriptors 
            and weights used during the low level unit search process.

        """
        log.debug("Received low level constraints array: %s" % constraints_array)
        self.constraints = {} # Dict is reset every time? This could change.
        for i in range(0, len(constraints_array), 2):
            self.constraints.update({constraints_array[i]:constraints_array[i+1]})
        log.info("Gaia euclidean distances and weights for searching are %s"
            % self.constraints)


    def setHLConstraints(self, constraints_array):
        """
            This sets **self.chl_onstraints**. These are the descriptors 
            and weights used during the high level unit search process.

        """
        log.debug("Received high level constraints array: %s" % constraints_array)
        self.hl_constraints = {} # Dict is reset every time? This could change.
        for i in range(0, len(constraints_array), 2):
            self.hl_constraints.update({constraints_array[i]:constraints_array[i+1]})
        log.info("Gaia euclidean distances and weights for searching \
                      at a high level are %s" % self.hl_constraints)

    @extract_from_list
    def toggleHighLevel(self, val):
        """
            A simple switch for bypassing high level mosaicing.

        """
        log.debug("Toggling highlevel mosaicing, val is %d" % val)
        self.highlevel = val

    @extract_from_list
    def setHighScope(self, scope):
        """
            Defines the number of results returned during high level search.

        """
        log.debug("Will return %d units from high level similarity search." % scope)
        self.highscope = scope

    @extract_from_list
    def setLowScope(self, scope):
        """
            Defines the number of results returned during low level search.

        """
        log.debug("Will return %d units from low level similarity search." % scope)
        self.lowscope = scope

    @extract_from_list
    def saveMosaic(self, save_name=None):
        """
            Saves the target, the mosaic and a beep demarcated target 
            (where beeps sound at the locations of the detected onsets).
            The files are saved into the **mosaic** corpus of the target 
            repository.
            If ``save_name`` is **None** then the filename is autogenerated 
            based on the timestamp, else ``save_name`` is used as the root name
            for saving the files, using the following convention:
            * *save_nameMOSAIC.wav*
            * *save_nameONSETS.wav*
            * *save_nameTARGET.wav*
            * *save_nameINFO.txt*

        """
        if not save_name:
            save_name = wav_timestamp(self.target.filepath)
        target_filepath = os.path.join(self.target_corpus.location, self.target.filepath)
        info_path = os.path.join(self.mosaic_corpus.location, save_name)
        self.mosaic_corpus.store_audio(\
            self.temp_corpus.get_filepath(self.tmp_name), switch_ext(save_name, 'MOSAIC.wav'))
        log.debug("Saved the mosaic as '%s'" 
            % switch_ext(save_name, 'MOSAIC.wav')
        )
        if not hasattr(self, 'marked_audio'):
            self.marked_audio = self.target_corpus.save_marked_audio(target_filepath)
        self.mosaic_corpus.store_audio(self.marked_audio, switch_ext(save_name, 'ONSETS.wav'))
        log.debug("Saved the marked audio as '%s'" 
            % switch_ext(save_name, 'ONSETS.wav')
        )
        self.mosaic_corpus.store_audio(target_filepath, switch_ext(save_name, 'TARGET.wav'))
        log.debug("Saved the target as '%s'" 
            % switch_ext(save_name, 'TARGET.wav')
        )
        self.mosaic_corpus.store_info(self._get_info(), switch_ext(info_path, 'INFO.txt'))
        log.debug("Saved the information as '%s'" 
            % switch_ext(info_path, 'INFO.txt')
        )
        
    
    def send_mosaic_path(self):
        """
            Simple method to copy the file at ``self.mosaic.filepath`` 
            to some predefined location where PureData or any other audio
            engine can find it. An OSC message is then sent to the engine
            to notify it that the file is ready. 

        """
        
        log.info("Sending mosaic filepath '%s' to the audio engine. "
            % self.mosaic.filepath)
        msg = OSCMessage('/loadMosaic')
        msg.append(self.mosaic.filepath)
        self.client.sendto(msg=msg, address=self.audio_server)

    #@extract_from_list
    def loadLastTarget(self):
        """
            This finds the most recently processed target and sets it for use here.

        """
        target_filepath = self.target_corpus.get_most_recent()
        log.info("Loading last target: '%s'" % target_filepath)
        self.target = Target(os.path.basename(target_filepath))
        self.target.set_props(switch_ext(target_filepath, '.yaml'))
        log.debug("Target has been set - name is: %s" % self.target)
        if self.daemon:
            log.debug("Sending target_filepath: '%s' to GUI" % target_filepath)
            msg = OSCMessage('/loadTarget')
            msg.append(target_filepath)
            self.client.sendto(msg=msg, address=self.audio_server)
            
        
        
    @strip_arguments 
    def createMosaic(self):
        """
            This is the main method of this class. It checks all the settings
            and creates the mosaic accordingly. It sends the filepath to the 
            finished mosaic back to the gui client at the end if running in 
            daemon mode.

        """
        # Check if target has been set.
        if not self.target:
            log.error("Target has not been set !!! ")
            return None
            

        # Create a temporary file for the mosaic audio
        filepath = os.path.join(self.temp_corpus.location, self.tmp_name)
        if os.path.isfile(filepath):
            os.remove(filepath)
        self.mosaic = Mosaic(filepath)

        
        

        # If high level mosaicing is activated - perform high level processing.
        # The low level processing just needs a db of target points, 
        # a view on the source db and the source db itself

        if self.highlevel:
            try:        
                units = self.target_corpus.list_audio_units(
                    audio_filename=self.target.filepath, chop='highlevel')
            except Exception, e:
                log.error("Exception occurred looking for highlevel chop for %s"
                    % self.target.filepath)
                self.process_target_hl()
                units = self.target_corpus.list_audio_units(
                    audio_filename=self.target.filepath, chop='highlevel')
            try:
                hdb = self.source_corpus.get_gaia_unit_db(chop='highlevel_%s' % self.chop)
            except FileNotFoundException, e:
                log.error("Chop: 'highlevel_%s' does not exist, creating..."
                    % self.chop
                )
                process_corpus_highlevel(os.path.basename(
                    self.source_corpus.location), self.chop
                )
                hdb = self.source_corpus.get_gaia_unit_db(chop='highlevel_%s' % self.chop)
                
            distance = self._get_distance(hdb, 'highlevel')
            v = View(hdb, distance)
            results = {}
            for f in units:
                p = Point()
                p.load(switch_ext(f, '.yaml'))
                unit_name = switch_ext(os.path.basename(f), '')
                p.setName(unit_name)
                p_m = hdb.history().mapPoint(p)
                results.update({f:v.nnSearch(p_m).get(self.highscope)})
            log.debug("Ok, now we have a dict with each target segment, along with its corresponding nearest matches in source db")
            log.debug("Check to see that we have every second of target audio accounted for - I think not!") 
            
            ds = DataSet()
            for r in results.keys():
                units = []
                
                for u in results[r]:
                    if type(u) == type(Point()):
                        log.error("It's a gaia point...%s" % u.name())
                        log.error("Here is what's in results: %s" % results)
                        log.error("This is the key that spawned it: '%s', and the item for that key: '%s' Ok, we'll skip it" % (r, results[r]))
                        continue
                    else:
                        ds.load(switch_ext(u[0], '.db'))
                       
                    for n in ds.pointNames():
                        units.append(n)
                new_ds = gaia_transform(dict(zip(units, units)))
                results.update({r:new_ds})
            index = 0
            index_skip = 0
            # Very important - target units must be in correct order
            for r in sorted(results.keys()):
                tds = DataSet()
                tds.load(switch_ext(r, '.db'))
            
                sds = results[r]
                tds, sds = equalise_datasets(tds, sds)

                sv = View(sds, self._get_distance(sds))
                log.debug("Beginning to loop through units for this segment")
        
                for pname in sorted(tds.pointNames()):
                    if os.path.basename(pname) != '%07d.yaml' % (index + index_skip):
                        log.error("Current unit is %s => Missing a unit '%07d.yaml' \
                            - it must be silent... Index is %d, index skip is %d" 
                                % (pname, (index + index_skip), index, index_skip))
                        u = MosaicUnit(os.path.join(os.path.dirname(pname), '%07d.wav' 
                            % (index + index_skip)))
                        u.silent = True
                        self.mosaic.add_unit(u)
                        index_skip += 1

                    self._assemble_low_level(pname, sds, sv)
                    index += 1
        else:
            sds = self.source_corpus.get_gaia_unit_db(chop=self.chop)
            sv = View(sds, self._get_distance(sds))
        
            # Loop through target units and create mosaic 
            for index, unit in enumerate(self.target_corpus.list_audio_units(\
                audio_filename=self.target.filepath, chop=self.target_chop)):
                a = switch_ext(unit, '.yaml')
                if not os.path.isfile(a):
                    log.error("%s doesn't exist-insert silent unit, same len as %s!"
                        % (a, unit))
                    mu = MosaicUnit(unit)
                    mu.silent = True
                    self.mosaic.add_unit(mu)
                    continue
                else:
                    self._assemble_low_level(a, sds, sv)
            
        log.info("Finished looping though target units")
        log.debug("Mosaic length is: %f, target length is: %f" 
            % (self.mosaic.length, self.target.length))
          
        # apply crossfade

        if self.bpm:
            log.info("BPM is: (%s) => unit length is: (%f)"
                % (self.target.bpm, self.target_chop))
            log.info("Timestretching to fit BPM - unit length is: %f, crossfade is %d" 
                % (self.target_chop,self.crossfade))
            self.mosaic.timestretch(self.target_chop/float(1000), self.crossfade)
        elif self.crossfade:
            log.info("Applying crossfade of %d" % self.crossfade)
            self.mosaic.crossfade(self.crossfade)

        log.debug("Mosaic length is: %f" % self.mosaic.length)

        # Reset the cost and context objects
        self.cost.reset()
        self.context.reset()
        
        # Persist mosaic to disk and send a messsage to audio engine.
        log.info("Persisting mosaic to disk")
        self.mosaic.persist()
        if self.daemon:
            self.send_mosaic_path()
       
            #return mosaic

###############################################################################
# PRIVATE FUNCTIONS
############################################################################### 


    def _assemble_low_level(self, pname, sds, sv):
        """
            Factor out the low level code in order to avoid
            repeating it in the main *createMosaic* method.
            

        """
        p = Point()
        p.load(pname)
        p_m = sds.history().mapPoint(p)
        unit_results = sv.nnSearch(p_m).get(self.lowscope)
        log.debug("For %s, the closest matching points are: %s" % (pname, unit_results))
        if self.rep_cost:
            log.debug("Applying repetition cost")
            unit_results = self.cost.get_results(unit_results)
            log.debug("Results are now: %s" % str(unit_results))
        if self.con_cost:
            log.debug("Applying Context")
            unit_results = self.context.get_results(unit_results)
            log.debug("Results are now: %s" % str(unit_results))
        path = unit_results[0][0]
            
        log.debug("Choosing this unit: %s" % path)
        filepath = switch_ext(path, '.wav')
        su = MosaicUnit(filepath)
        if self.gridder.active:
            tl = float(p['length'])
            log.debug("Length of target unit is %f, length of chosen source unit is %f" % (tl, su.length))
            su = self.gridder.fit(su, tl)  
        self.mosaic.add_unit(su)
        if self.con_cost:
            self.context.append(path)
        if self.rep_cost:
            self.cost.check_repeats(path)
        

    def _get_distance(self, db, ctype='lowlevel'):
        """
            Expects constraints to be populated but applies a default linear
            combination if not. Returns a gaia distance object to be used
            when searching for source units.

        """
        # Set db,constraints and default settings depending on ctype being high or low!
        if ctype == 'highlevel':
            constraints = self.hl_constraints
            default = get_mood_distance
            db = self.source_corpus.get_gaia_unit_db(chop='highlevel_%s' % self.chop)
        else:
            constraints = self.constraints
            default = get_low_level_distance
            #db = self.source_corpus.get_gaia_unit_db(chop=self.chop)
            
        
        # If the desired constraints are empty then create the defaults.
        if len(constraints) == 0:
            distance = default(db)
        else:  
            distances = {}        
            for key in self.constraints.keys():
                distances.update({key: { 'distance': 'euclidean',
                              'params': { 'descriptorNames': 
                                  key
                               },
                               'weight': self.constraints[key] 
                             }})
        
            log.debug("Similarity search distances are : %s, type is %s" % (distances, ctype))  
            distance = MetricFactory.create('linearcombination', db.layout(), \
                 distances)
        return distance

    def _get_info(self):
        """
            Builds a dictionary of information, relating to the current state
            of the mosaicer.
            Information is:
            * bpm
            * onset_weights
            * chop
            * constraints
            * high level constraints
          
        """
        return { 
                 'bpm': self.bpm,
                 'aubio': self.aubio,
                 'chop': self.chop,
                 'onset_weights': self.onset_weights,
                 'corpus': self.source_corpus.location,
                 'constraints': self.constraints,
                 'HighLevelConstraints': self.hl_constraints
                }
     

def validate_setting(setting):
    """
        Makes sure that the given **setting** exists in `settings.py`.

    """
    try:
        getattr(settings, setting)
        return True
    except AttributeError, e:
        log.error("Setting '%s' does not exist!! -- '%s'" 
            % (setting, e))
        return False

def equalise_datasets(tds, sds):
    """
       Takes two Gaia datasets and makes sure they have the same layout.
   
    """
    source_set = set(sds.layout().descriptorNames())
    target_set = set(tds.layout().descriptorNames())
    remove_from_source = source_set.difference(target_set)
    remove_from_target = target_set.difference(source_set)
    if len(remove_from_source) > 0:
        log.debug("Will try to remove %s from the source DataSet" % remove_from_source)
        try:
            sds = transform(results[r], 'remove', {'descriptorNames':list(remove_from_source)})
        except Exception, e:
            log.error("Failed to remove %s from source DataSet" % list(remove_from_source))
                
    if len(remove_from_target) > 0:
        log.debug("Will try to remove %s from the target DataSet" % remove_from_source)
        try:
            tds = transform(tds, 'remove', {'descriptorNames':list(remove_from_target)})
        except Exception, e:
            log.error("Failed to remove %s from target DataSet" % list(remove_from_target))

    return tds, sds


class Gridder(object):
    """
        Transforms Mosaic Units to match the length of the target unit.

    """

    def __init__(self, strategy=1):
        """
            Two possible strategies
            * timestretch (default)
            * Cut or pad with silence
            The first strategy is self explanatory, the second operates 
            differently depending on the length of the unit. If the target 
            unit is longer, it pads the mosaic unit with silence, if the 
            target unit is shorter it simply cuts the mosaicUnit.

        """
        self.strategy = strategy
        self.active = False

    def set_active(self, switch):
        """
            Turn this gridder object on or off.
        """
        if switch:
            self.active=True
        else:
            self.active = False

    def fit(self, unit, tlength):
        """
            The fit method takes two params
            * *unit* - The unit to be modified
            * *tlength* - The target length
            This method simply applies the current strategy and returns a new unit
            of the correct length.

        """
        if self.strategy == 1:
            unit = timestretch(unit, tlength, 44100)
        else:
            tsamps = secs_to_samps(tlength, 44100)
            if unit.length > tlength:
                log.debug("Cut the unit data to %d samples" % tsamps)
                unit.data = unit.data[:tsamps]
                unit.recalculate()
            elif unit.length < tlength:
                padsamps = tsamps - len(unit.data)
                log.debug("Pad with %d samples of silence" % padsamps)
                if padsamps > 0:
                    unit.data = np.concatenate((unit.data, np.zeros(padsamps, 'single')))
                    unit.recalculate()
        return unit
                
   
       
        

class Context(object):
    """
        This class keeps track of a certain number of previous units
        It can be used to weight the gaia results based on similarity 
        between each result and the audio in the context.

    """

    def __init__(self, length=20):
        """
            Sets the ``length`` of the context.
            
        """
        self.length = length
        self.data = []
        
    def append(self, key):
        """
            Appends an entry to the dictionary, changes behaviour when full
            This was inspired by the Python Cookbook RingBuffer recipe.
 
        """
        self.data.append(key)
        if len(self.data) == 20:
            self.append = self._append_full
            self.cur = 0

    def _append_full(self, key):
        """
            Method used to poulate elements once ringbuffer is full.
        """
        self.data[self.cur] = key
        self.cur = (self.cur + 1) % self.length
        
        
     
    def reset(self):
        """
            Helper method to reset the cost function every time.

        """
        self.data = [] 

    def get_results(self, results):
        """
           Creates a GaiaDB of the previous context and searches for each point 
           in the resultset. Returns results updated with the local distance
           factored in.
           The simplest way is to calculate the total distance from each point
           for each result and add that to the result score. That way, those which are very 
           different will be penalised.

        """
        if len(self.data) <= 4: # Try and avoid problems with gaia - missing descriptors cause the DS is too small
            return results
        points = dict(zip(self.data, self.data))
        cds = gaia_transform(points)
        v = View(cds, get_low_level_distance(cds))
        new_results = []
        for r in results:
            p = Point()
            p.load(r[0])
            p_m = cds.history().mapPoint(p)
            results = v.nnSearch(p_m).get(len(self.data))
            cost = sum(r[1] for r in results)
            new_results.append((r[1]+cost, r[0]))
        return tuple([(x[1], x[0]) for x in sorted(new_results)])
           

    

class RepeatUnitCost(object):
    """
        This should accept a gaia result set as input and
        return a single unit as output.
        Cost is based on gaia similarity score, if the result has
        already been selected and (maybe) the similarity of the result
        to the context.
        This Cost object ought to be configurable...
        
    """

    def __init__(self, factor=0.02, context=20):
        """
            ``factor`` is multiplied by the number of times the unit appears in the context.
            This number is then added to the score for that unit in the current search results.
            This incresases its distance and thus a different unit may be selected if the units
            are quite similar to each other.

        """
        self.prev_units = {}
        self.factor = factor

    def reset(self):
        """
            helper method to reset the cost function
        """
        self.prev_units = {}
        
        

    
    def get_results(self, results):
        """
        """
        new_results = []
        for r in results:
            if r[0] in self.prev_units.keys():
                # A crude weight, it will favour less repition over time
                new_results.append((r[1] + (self.factor * self.prev_units[r[0]]), r[0]))
                
            else:
                new_results.append((r[1], r[0]))

        sorted_results = tuple([(x[1], x[0]) for x in sorted(new_results)])
        

        return sorted_results

    def check_repeats(unit):
        """
        """
        if unit in self.prev_units.keys():
            self.prev_units[unit] += 1
        else:
            self.prev_units[unit] = 1

        


    


def get_unused_descriptors():
    """
        Returns a set of descriptors which are not used and which occasionaly 
        cause problems with gaia due to their values.

    """
    for d in ['rhythm.beats_position', 'rhythm.bpm_estimates', 
                 'rhythm.bpm_intervals', 'rhythm.onset_times', 
                 'rhythm.rubato_start', 'rhythm.rubato_stop', 
                ]:
        yield {'descriptorNames': [d]}
    


    #corpus.create_gaia_db(chop='highlevel')
        


def get_mood_distance(unit_db):
    """
        Returns a hard coded mood distance. A linear combination of
        euclidean distances for all 4 moods.

    """

    distances = {}
        
    distances.update({'dist1': { 'distance': 'euclidean',
                      'params': { 'descriptorNames': 
                          ['highlevel.mood_happy.all.happy']
                               },
                               'weight': 1 
                             }})
    distances.update({'dist2': { 'distance': 'euclidean',
                      'params': { 'descriptorNames': 
                          ['highlevel.mood_sad.all.sad']
                               },
                               'weight': 1 
                             }})
    distances.update({'dist3': { 'distance': 'euclidean',
                      'params': { 'descriptorNames': 
                          ['highlevel.mood_relaxed.all.relaxed']
                               },
                               'weight': 1 
                             }})
    distances.update({'dist4': { 'distance': 'euclidean',
                      'params': { 'descriptorNames': 
                          ['highlevel.mood_aggressive.all.aggressive']
                               },
                               'weight': 1 
                             }})
    log.debug("highlevel level search distances are : %s" % distances)
    distance = MetricFactory.create('linearcombination', unit_db.layout(), \
             distances)
    return distance   

def get_low_level_distance(unit_db):
    """
        Returns a hard coded low level distance based on length, pitch and 
        spectral energy

    """
    distances = {}
        
    distances.update({'dist1': { 'distance': 'euclidean',
                      'params': { 'descriptorNames': 
                          ['metadata.audio_properties.length']
                               },
                               'weight': 1 
                             }})
    distances.update({'dist2': { 'distance': 'euclidean',
                              'params': { 'descriptorNames': 
                                  ['pitch.mean', 'spectral_energy.mean']
                               },
                               'weight': 0.5 
                             }})
    log.debug("Low level search distances are : %s" % distances)
    distance = MetricFactory.create('linearcombination', unit_db.layout(), \
             distances)
    log.debug("Distance created successfully")
    return distance
    

def gaia_transform(points):
    """
        Takes a dict of point names and filepaths
        Creates a DataSet and performs the standard transformations 
    """
    ds = DataSet.mergeFiles(points)
    ds = transform(ds, 'fixlength')
    ds = transform(ds, 'cleaner')
    for desc in get_unused_descriptors():
        try:   
            ds = transform(ds, 'remove', desc)
        except Exception, e:
            log.error("Problem removing this descriptor: %s" % e)
    ds = transform(ds, 'normalize')
    return ds




if __name__ == '__main__':

    cm = FileCorpusManager(settings.SOURCE_REPO)
    t = HighLevelControl(cm)
    
    
    

    
