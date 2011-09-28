#!/usr/bin/env python

import os
import re

from hmosaic.corpus import FileCorpusManager
from hmosaic.settings import SOURCE_REPO
from hmosaic.utils import switch_ext
from hmosaic import log

from hmosaic.analyse import EssentiaAnalyser, EssentiaError
from hmosaic.models import Mosaic, MosaicUnit
from gaia2 import DataSet, transform

def gaia_transform(points):
    """
        Takes a dict of point names and filepaths.
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

def get_unused_descriptors():
    """
        Gets some descriptors which are not commonly used in order to remove
        them from the analysis
    """
    for d in ['rhythm.beats_position', 'rhythm.bpm_estimates', 
                 'rhythm.bpm_intervals', 'rhythm.onset_times', 
                 'rhythm.rubato_start', 'rhythm.rubato_stop', 
                ]:
        yield {'descriptorNames': [d]}


def process_highlevel(corpus, filepath, chop):
    """
        Utility method used to test the hierarchical system and create
        high level segments along with analysis and constituent units
        stored in a gaia dataset for a given ``corpus`` and file from that 
        ``corpus`` .
      
    """
    units = corpus.list_audio_units(audio_filename=filepath, chop=chop)
    new_segments = []
    m = Mosaic()
    analyser = EssentiaAnalyser()
    for u in units:
        if not os.path.isfile(switch_ext(u, '.yaml')):
            log.error("Cannot find analysis, assume that this file is silent: '%s'" % u)
            continue
        m.add_unit(MosaicUnit(u))
        log.debug("Number of units in mosaic is: %d, length of mosaic is %d" % (len(m.units), m.length))
        # This AND clause prevents a Gaia Dataset of only 1 Point being created.
        # The problem is that if the dataset only has one point then all 
        # descriptors get removed during 'cleaner' analysis
        if m.length > 5 and len(m.units) > 1: 
            log.debug("Current length of mosaic is %f, adding to list" % m.length)
            new_segments.append(m)
            m = Mosaic()
    if len(new_segments) == 0:
        log.warn("Retrieved only 1 high level mosaic unit of length: %f" % m.length)
        new_segments.append(m)
    if m != new_segments[-1]:
        log.debug("The final mosaic is of length %f only" % new_segments[-1].length)
        log.debug("The last mosaic has a length of: %f" % m.length)
        m.merge_mosaics(new_segments[-1])
        new_segments[-1] = m
    log.debug("Finished assembling units into segments of > 5s")
    log.debug("There are %d segments in total to be processed for %s" % (len(new_segments), os.path.basename(filepath)))
    highlevel_dir = corpus._make_segments_dir(filepath, 'highlevel_%s' % chop)
    for index, seg in enumerate(new_segments):
        path = os.path.join(highlevel_dir, '%05d.wav' % index)
        seg.export(path)
        log.debug("Analysing audio: %s" % path)
        analyser.analyse_audio(path)
        unit_dict = {}
        log.debug("Segment has %d units" % len(seg.units))
        for unit in seg.units:
            #path_comps = os.path.split(os.path.dirname(unit.filepath))
            #chop_dir = path_comps[1]
            #name = os.path.split(path_comps[0])[1] + '_' + chop_dir + \
            #    '_' + switch_ext(os.path.basename(unit.filepath), '')
            unit_dict.update({switch_ext(unit.filepath, '.yaml'): switch_ext(unit.filepath, '.yaml')})
        tu_ds = gaia_transform(unit_dict)
        tu_ds.save(os.path.join(highlevel_dir, '%05d.db' % index))

    #corpus.create_gaia_db(chop='highlevel')


def highlevel_mosaic(target, tcorpus, scorpus, scope=5):
    """
        This will be used to test the highlevel mosaicing process.
        The scope variable controls the number of results which are returned 
        for each target unit which is sought.

    """
    # Create a temporary file for the mosaic audio
    filepath = os.path.join(os.getcwd(), 'temp_mosaic.wav')
    if os.path.isfile(filepath):
        os.remove(filepath)
    mosaic = Mosaic(filepath)
    cost = RepeatUnitCost()
    context = Context()
    gridder = Gridder()
    units = tcorpus.list_audio_units(audio_filename=target, chop='highlevel')
    hdb = scorpus.get_gaia_unit_db(chop='highlevel_%s' % self.chop)
    distance = get_mood_distance(hdb)
    v = View(hdb, distance)
    results = {}
    for f in units:
        p = Point()
        p.load(switch_ext(f, '.yaml'))
        unit_name = switch_ext(os.path.basename(f), '')
        p.setName(unit_name)
        p_m = hdb.history().mapPoint(p)
        results.update({f:v.nnSearch(p_m).get(scope)})
    log.debug("Ok, now we have a dict with each target segment, along with its corresponding nearest matches in source db")
    log.debug("Check to see that we have every second of target audio accounted for - I think not!") 
    #return results
    #new_results = results.copy()
    ds = DataSet()
    for r in results:
        units = []
        for u in results[r]:
            ds.load(switch_ext(u[0], '.db'))
            for n in ds.pointNames():
                units.append(n)
        new_ds = gaia_transform(dict(zip(units, units)))
        results.update({r:new_ds})
    #return results
    # Very important - target units must be in correct order
    index = 0
    index_skip = 0
    for r in sorted(results.keys()):
        tds = DataSet()
        tds.load(switch_ext(r, '.db'))
        #return tds, results
        sds = results[r]
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
                return results[r], tds
        if len(remove_from_target) > 0:
            log.debug("Will try to remove %s from the target DataSet" % remove_from_source)
            try:
                tds = transform(tds, 'remove', {'descriptorNames':list(remove_from_target)})
            except Exception, e:
                log.error("Failed to remove %s from target DataSet" % list(remove_from_target))
                return results[r], tds

        sv = View(sds, get_low_level_distance(sds))
        log.debug("Beginning to loop through units for this segment")
        #return tds, sds, gridder, sv
        for pname in sorted(tds.pointNames()):
            """
            I don't think I need to map the point in this instance 
            as we have already transformed the DataSet.
            try, analyse_corpus:
                p_m = sds.history().mapPoint(p)
            except Exception, e:
                log.error("Error mapping %s to %s: %s" % (p, sds, e))
                return tds, p, sds
            """
            print pname
            if os.path.basename(pname) != '%07d.yaml' % (index + index_skip):
                log.error("Current unit is %s => Missing a unit '%07d.yaml'- it must be silent... Index is %d, index skip is %d" % (pname, (index + index_skip), index, index_skip))
                u = MosaicUnit(os.path.join(os.path.dirname(pname), '%07d.wav' % (index + index_skip)))
                u.silent = True
                mosaic.add_unit(u)
                index_skip += 1

            p = Point()
            p.load(pname)
            p_m = sds.history().mapPoint(p)
            unit_results = sv.nnSearch(p_m).get(scope)
            log.debug("For %s, the closest matching points are: %s" % (pname, unit_results))
            log.debug("Applying repition cost")
            unit_results = cost.get_results(unit_results)
            log.debug("Results are now: %s" % str(unit_results))
            log.debug("Applying Context cost")
            unit_results = context.get_results(unit_results)
            log.debug("Results are now: %s" % str(unit_results))
            path = unit_results[0][0]
            
            log.debug("Choosing this unit: %s" % path)
            filepath = switch_ext(path, '.wav')
            su = MosaicUnit(filepath)
            tl = float(p['length'])
            log.debug("Length of target unit is %f, length of chosen source unit is %f" % (tl, su.length))
            selected = gridder.fit(su, tl)  
            mosaic.add_unit(selected)
            context.append(path)
            index += 1
       
    return mosaic
        

   # Overall architecture of this mode should support low level and/or highlevel options.
   # The loudness and the beat skip are all highlevel features.
   # Two sets of constraints - highlevel + lowlevel.
   # Track continuity is also supported +  - maybe not...conditions (used to be context) - Just a small subset to begin
   # Continuity yes - This is low level - a certain set of features based on the signal
    



def initial_test():
    """
        Helper method used for analysing a couple of corpuses at once.
    """
    cm = FileCorpusManager(SOURCE_REPO)
    for name in ['melodies', 'motown']:
        corpus = cm.load_corpus((name))
        for f in corpus.list_audio_files():
            process_highlevel(corpus, f, chop='onsets')
        corpus.create_gaia_db(chop='highlevel_onsets')

def process_corpus_highlevel(corpus_name, chop, cman=SOURCE_REPO):
    """
        Wrapper for the **process_highlevel** method in order to process
        all files in a given **corpus** for a given **chop**    
    """
    cm = FileCorpusManager(cman)
    corpus = cm.load_corpus(corpus_name)
    for f in corpus.list_audio_files():
        process_highlevel(corpus, f, chop=chop)
    corpus.create_gaia_db(chop='highlevel_%s' % chop)




if __name__ == '__main__':
    initial_test()  
            
    
    
