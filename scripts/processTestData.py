#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This is a commandline script for processing the test data.
It calls segementation routines, analysis routines, etc. and stores
all output in the test corpus. This module also contains some functions
for gathering data during experiments.

"""

# Standard library imports
import os, shutil
from glob import glob
from random import randint

import yaml
import numpy as np
from csv import DictWriter
from gaia2 import Point
from scipy import stats

# Project imports
from hmosaic.analyse import EssentiaAnalyser
from hmosaic.corpus import FileCorpusManager, CorpusExistsException
from hmosaic import log
from hmosaic import settings
from hmosaic.scripts import segment_corpus, analyse_corpus, analyse_corpus_files
from hmosaic.scripts import convertAudio as ca
from hmosaic.utils import switch_ext, get_db_connection, get_gaia_point
from hmosaic.models import DBSegment, DBSong
from hmosaic.control import HighLevelControl


def segment(chop):
    """
        Segment all audio files in the test corpus according to ``chop``.
        
    """
    cm = FileCorpusManager(settings.TEST_CORPUS_REPO)
    corpus = cm.load_corpus(settings.TEST_CORPUS)
    segment_corpus(corpus)
  

def analyse_essentia_units(chop):
    """
        Analyse all essentia units of segmentation type: ``chop`` in the test 
        corpus.
        
    """
    cm = FileCorpusManager(settings.TEST_CORPUS_REPO)
    corpus = cm.load_corpus(settings.TEST_CORPUS)
    analyse_corpus(corpus, chop)
    
def analyse_essentia_files(corpus_name=settings.TEST_CORPUS):
    """
        Analyse all essentia units of segmentation type: ``chop`` in the test 
        corpus.
        
    """
    cm = FileCorpusManager(settings.TEST_CORPUS_REPO)
    corpus = cm.load_corpus(corpus_name)    
    analyse_corpus_files(corpus)
                
                
def create_and_populate():
    """
        Recreates **settings.TEST_CORPUS** from the set of files in 
        **settings.TEST_DATA_DIR**, converts 
    """

    cm = FileCorpusManager(settings.TEST_CORPUS_REPO)
    try:
        log.info("Creating a test corpus.")
        cm.create_corpus(settings.TEST_CORPUS)
    except CorpusExistsException, e:
        log.error("Corpus already exists '%s'" % settings.TEST_CORPUS)
        log.info("Deleting the test corpus")
        cm.delete_corpus(settings.TEST_CORPUS)
        log.debug("Recreating the test corpus.")
        cm.create_corpus(settings.TEST_CORPUS)
     
    corpus = cm.load_corpus(settings.TEST_CORPUS)
    
    os.chdir(settings.TEST_DATA_DIR)
    ca.rename_wavs()
    ca.execute_flac_convert()
    ca.execute_mp3_convert()
    
    for audio_file in glob(os.path.join(settings.TEST_DATA_DIR, '*.wav')):
        log.debug("Storing '%s' in corpus" % audio_file)
        corpus.store_audio(audio_file)
   

def run_tasks():
    """
        Very rough and ready set of instructions to process.
        Delete the test_corpus and start over, segment and analyse
        different chop sizes. 
        
    """
    
    log.info("Creating and populating the test_corpus")
    create_and_populate()
    
    log.info("Segmenting into units of 200 ms")
    segment(200)
    
    log.info("Segmenting into units of 500 ms")
    segment(500)
    
    log.info("Segmenting into units of 1250 ms")
    segment(1250)
    
    #log.info("Segmenting into units based on onsets")
    #segment('onsets')
    
    log.info("Analysing audio files using Essentia")
    analyse_essentia_files()
    
    log.info("Analysing  onsets using Essentia")
    analyse_essentia_units('onsets')
    
    log.info("Analysing  units of  500 ms using Essentia")
    analyse_essentia_units(500)
    log.info("Analysing  units of  200 ms using Essentia")
    analyse_essentia_units(200)
    log.info("Analysing  units of  1250 ms using Essentia")
    analyse_essentia_units(1250)

def display_file_values(*args):
    """
        Display an aribitrary set of descriptor values from analysis contained
        in **settings.TEST_CORPUS**. The descriptor keys ought to be passed 
        in ``args``

    """
    cm = FileCorpusManager(settings.TEST_CORPUS_REPO)
    corpus = cm.load_corpus(settings.TEST_CORPUS)
    for f in corpus.list_audio_files():
        a = yaml.load(open(switch_ext(f, '.yaml'), 'r').read())
        for arg in args:
            log.info("For file %s" % f)
            keys = arg.split('.')
            newa = a
            for k in keys:
                newa = newa[k]
            log.info("%s is %s" % (arg, newa))


def create_db():
    """
        Recreates the database with the segment information

    """
    store = get_db_connection()
   
    
    db_handle = store.execute("CREATE TABLE segment "
    "(id INTEGER PRIMARY KEY, song_name VARCHAR(500), segment_name VARCHAR(500), segment_duration INTEGER, vocal FLOAT, instrumental FLOAT, male FLOAT, female FLOAT)")
    
    store.commit()
    store.close()

def add_to_db():
    """
        Recreates the song table in the database.

    """
    store = get_db_connection()  
    db_handle = store.execute("DROP TABLE song ") 
    db_handle = store.execute("CREATE TABLE song "
    "(id INTEGER PRIMARY KEY, song_name VARCHAR(500), vocal FLOAT, instrumental FLOAT, male FLOAT, female FLOAT)")
    store.commit()
    store.close()
            
def gather_csv_data(*args):
    """
        This function gets given a corpus and extracts the descriptors 
        given in the *args* to the function. It records this data, 
        audio file name and segment duration.

    """
    cm = FileCorpusManager(settings.TEST_CORPUS_REPO)
    corpus = cm.load_corpus(settings.TEST_CORPUS)
    fieldnames = ['segment_path', 'song_name', 'segment_duration']
    for arg in args:
        fieldnames.append(arg.split('.')[-1])
   
    report = open('ExperimentReport.csv', 'wb') # Will overwrite any existing file!!
    csv = DictWriter(report,fieldnames)
    csv.writerow(dict(zip(fieldnames, fieldnames)))
    
    for f in corpus.list_audio_files():
        for c in [200, 500, 1250]:
            for s in corpus.list_audio_units(audio_filename=os.path.basename(f), chop=c):
                try:
                    a = yaml.load(open(switch_ext(s, '.yaml'), 'r').read())
                except IOError, e:
                    log.error("Analysis not found - must be silent: %s" % e)
                    continue
                vals = [s, os.path.basename(f), c]
                for arg in args:
                    newa = a
                    keys = arg.split('.')
                    for k in keys:
                        newa = newa[k]
                    vals.append(newa)
                csv.writerow(dict(zip(fieldnames,  vals)))
    report.close()

    
def gather_db_data():
    """
        This function gets given a corpus and extracts the descriptors 
        for male, female, vocal and instrumental. It encapsulates this data, 
        along with audio file name, segment filepath and segment duration in a  
        ``hmosaic.models.DBSegment`` object and then stores it in a 
        sqlite database.

    """
    cm = FileCorpusManager(settings.TEST_CORPUS_REPO)
    corpus = cm.load_corpus('gender')
    create_db()
    store = get_db_connection()
    
    for f in corpus.list_audio_files():
        for s in corpus.list_audio_units(audio_filename=os.path.basename(f)):
            try:
                a = get_gaia_point(switch_ext(s, '.yaml'))
            except Exception, e:
                log.error("Analysis not found - must be silent: %s" % e)
                continue
            seg = DBSegment()
            seg.song_name = unicode(os.path.basename(f)[:10]) #first 10 characters only
            seg.segment_name = unicode(s)
            seg.segment_duration = int(os.path.basename(os.path.dirname(s)))
            seg.vocal = float(a[settings.VOCAL])
            seg.instrumental = float(a[settings.INSTRUMENTAL])
            seg.male = float(a[settings.MALE])
            seg.female = float(a[settings.FEMALE])
            store.add(seg)
               
    store.commit()
    store.flush()
    store.close()             

def create_mood_mosaics(*args):
    """
        Given a path to some mood music this function loads up the moods,
        creates a mosaic with each mood and saves them.
    """
    cm = FileCorpusManager(settings.SOURCE_REPO)
    
    control = OSCControl(cm, daemon=False)
    control.set_source_corpus('mixedcorpus')
    moods_dataset = '/home/john/Moods'
    for directory in os.listdir(moods_dataset):
        try:
            current_mood = getattr(settings, directory.upper())
            dir_path = os.path.join(moods_dataset, directory)
            os.chdir(dir_path)
            #ca.execute_mp3_convert()
            #ca.rename_wavs()   
            for f in glob('*.wav'):
                #map(lambda p: os.path.join(dir_path, p), os.listdir(dir_path)):
                control.set_target(f)
                control.process_target()
                control.set_constraints([current_mood, 1])
                control.mosaic_from_target()
                control.save_mosaic('mood' + directory + os.path.basename(f))
                  
        except Exception, e:
            log.error("Mood: '%s' does not exist: '%s'" % (directory.upper(), e))

def check_gender(*args):
    """
        Checks the analysis in *TEST_CORPUS* in order to ascertain the male/female
        values of each one. Those which score higher than 0.85 are 
        added to a list which is returned
    """
    cm = FileCorpusManager(settings.TEST_CORPUS_REPO)
    corpus = cm.load_corpus(settings.TEST_CORPUS)
    high_achievers = []
    for f in corpus.list_audio_files():
        try:
            a = get_gaia_point(switch_ext(f, '.yaml'))
            if a[settings.MALE] >= 0.85 or a[settings.FEMALE] >= 0.85:
                log.debug("Found a new high achiever: %s" %f)
                high_achievers.append(f)
        except Exception, e:
            log.error("Analysis not found - must be silent: %s" % e)
            continue
    log.debug("Found %d high achievers" % len(high_achievers))
    return high_achievers

def run_gender_analysis():
    """
        Analyse the files in a corpus called **gender**
        in **settings.TEST_CORPUS_REPO**.
 
    """
    gender_songs = check_gender()
    cm = FileCorpusManager(settings.TEST_CORPUS_REPO)
    cm.create_corpus('gender')
    corpus = cm.load_corpus('gender')
    for f in gender_songs:
        corpus.store_audio(f)
        shutil.copy(switch_ext(f, '.yaml'), corpus.location)
    segment_corpus(corpus)
    analyse_corpus(corpus, 2000)
    analyse_corpus(corpus, 4000)
    
    
def run_gender_report(*args):
    """
        Checks the database and runs a report. 
        We include vocal/instrumental and male/female. 
        Actual gender will have to be entered manually.

    """
    fieldnames = ['song_name', 'song_male', 'song_female', 'segment_name', 'segment_duration', 'male', 'female', 
        'instrumental', 'vocal', 'gender']
    
   
    report = open('ExperimentGenderReport.csv', 'wb') # Will overwrite any existing file!!
    csv = DictWriter(report,fieldnames)
    # write header first
    csv.writerow(dict(zip(fieldnames, fieldnames)))
    dbname = 'gender24.db'
    store = get_db_connection(dbname)
    res = store.find(DBSong)
    for r in res:
        res2 = store.find(DBSegment, song_name=r.song_name)
        csv.writerow(dict(zip(fieldnames, [r.song_name, res2.male, res2.female, r.segment_name, r.segment_duration, 
            r.male, r.female,  r.instrumental, r.vocal, u''])))
    

def gender_breakdown():
    """
       Process the results of the gender analysis experiments
    """
    dbname='gender24.db'
    store = get_db_connection(dbname)
    res = store.find(DBSegment)
    res.group_by(DBSegment.song_name)
    song_names = []
    for r in res:
        song_names.append(r.song_name)
    for s in song_names:
        for dur in [2000, 4000]:
            male = []
            female = []
            temp_res = store.find(DBSegment, song_name=s, segment_duration=dur)
            for seg in temp_res:
                if seg.male > 0.5:
                    male.append(seg)
                elif seg.female > 0.5:
                    female.append(seg)
                else:
                    print "Got an even split: %s - female: %f, male: %f" % (seg.song_name, seg.female, seg.male)
            print s + ' ' + '%d' % dur + " Total segments: %d " % temp_res.count() + " female %d " % len(female)+ "male %d " % len(male)
        
        

def add_gender(*args):
    """
        Checks the analysis in *TEST_CORPUS* in order to ascertain the male/female
        values of each one. Those which score higher than 0.85 have their values 
        plus their name added to the db.

    """
    store = get_db_connection('gender.db')
    cm = FileCorpusManager(settings.TEST_CORPUS_REPO)
    corpus = cm.load_corpus(settings.TEST_CORPUS)
    high_achievers = []
    for f in corpus.list_audio_files():
        try:
            a = get_gaia_point(switch_ext(f, '.yaml'))
            if a[settings.MALE] >= 0.85 or a[settings.FEMALE] >= 0.85:
                log.debug("Found a new high achiever: %s" %f)
                high_achievers.append(f)
                s = DBSong()
                s.song_name=unicode(os.path.basename(f)[:10])
                s.male = float(a[settings.MALE])
                s.female = float(a[settings.FEMALE])
                store.add(s)
        except Exception, e:
            log.error("Analysis not found - must be silent: %s" % e)
            continue
    log.debug("Found %d high achievers" % len(high_achievers))
    store.commit()
    store.flush()
    store.close()
    return store

def map_mosaics(corpus_name, chop, from_scratch=False, hop=False):
    """
        Returns dictionary containing mood values over time for all
        audio files in the test corpus. The resolution of the graphs can be 
        increased using the **hop** parameter
        (a value between 0 and 1 indicating overlap factor).

    """
    cm = FileCorpusManager(settings.TEST_CORPUS_REPO)       
    c = cm.load_corpus(corpus_name)

    if from_scratch:
        e = EssentiaAnalyser()
        for f in c.list_audio_files():
            c.segment_audio(f, chop, hop)
            e.analyse_audio(f)
            for u in c.list_audio_units(audio_filename=f, chop=chop):
                e.analyse_audio(u)  
    
    graphs = {'RELAXED':{}, 'SAD':{}, 'HAPPY':{}, 'AGGRESSIVE':{}}

    for f in c.list_audio_files():
        analysis = [switch_ext(u, '.yaml') for u in 
            c.list_audio_units(audio_filename=f)]
        points = []
        for a in analysis:
            p = Point()
            p.load(a)
            points.append(p)
        for k in graphs.keys():
            graphs[k].update({os.path.basename(f):
                [p[getattr(settings, k)] for p in points]})

    return graphs

def equalise(seq1, seq2):
    """
        Takes two sequences finds out which one is longer and
        reduces elements from the end of this in order to make it
        the same length as the smaller one.

    """
    if len(seq1) > len(seq2):
        seq1 = seq1[:(len(seq2)-len(seq1))]
    elif len(seq2) > len(seq1):
        seq2 = seq2[:(len(seq1)-len(seq2))]
    return seq1, seq2

mdiff = lambda tar, m: np.array(map(lambda p: abs(p[0]-p[1]), zip(tar, m))).mean()   

def calc_similarity(graphs):
    """
        This takes the graphs variable returned by the map_mosaics 
        function and calculates the average of the distance between 
        target and mosaics for each of the moods.

    """
    for mood in graphs.keys():
        tar = graphs[mood]['TARGET.wav']
        graphs[mood].pop('TARGET.wav')
        for mname in graphs[mood].keys():
            tar, m = equalise(tar, graphs[mood][mname])
            log.info("The average of the distances between %s \
                and the target for %s mood is %f" % (mname, mood, mdiff(tar, m)))
            
  
def dataset_metrics(graphs):
    """
        This takes the graphs variable returned from the *map_mosaics* function 
        and transforms it, showing the distance between the pairs of mosaics for the two corpora.

    """
    import re
    metrics = {'RELAXED':{}, 'SAD':{}, 'HAPPY':{}, 'AGGRESSIVE':{}}
    # First step is to extract all the targets
    for mood in graphs.keys():
        for f in graphs[mood]:
            if f.endswith('TARGET.wav'):
                metrics[mood].update({f:{}})
    # Now find 4 mosaics for each target
    p = re.compile('Onsets[A-Z]+\d{1}')
    for mood in metrics.keys():
        for f in metrics[mood]:
            metrics[mood].update({f:[]})
            m = p.search(f).group()
            matches =  [f2 for f2 in graphs[mood] if p.search(f2).group() == m]
            matches.remove(f)
            for mat in matches:
                metrics[mood][f].append((mat, mdiff(graphs[mood][f], graphs[mood][mat])))
    return metrics
            

def ttest_metrics(graphs):
    """
        This takes the graphs variable returned from the *map_mosaics* function 
        and transforms it, calculating ttests between the target and each mosaic.

    """
    metrics = dataset_metrics(graphs)
    new_metrics = {'RELAXED':{}, 'SAD':{}, 'HAPPY':{}, 'AGGRESSIVE':{}}
    for mood in ['HAPPY', 'SAD', 'RELAXED', 'AGGRESSIVE']:
        map(list.sort, [metrics[mood][t] 
            for t in metrics[mood]])
        llScores = [metrics[mood][t][1] 
            for t in metrics[mood]]
        hlScores = [metrics[mood][t][0]
            for t in metrics[mood]]
        # Make sure the results are all in the same order!!
        map(list.sort, [hlScores, llScores])
        # Just the numbers please!
        hlAvgs = [float(h[1]) for h in hlScores]
        llAvgs = [float(h[1]) for h in llScores]
        tstat, pval = stats.ttest_rel(llAvgs, hlAvgs)
        new_metrics[mood].update({'NH_diff': llScores})
        new_metrics[mood].update({'H_diff': hlScores})
        new_metrics[mood].update({'ttest': tstat})
        new_metrics[mood].update({'pval': pval})
    return new_metrics

def pick_mood_collection():
    
    for f in os.listdir(settings.MOOD_COLLECTION):
        os.remove(f)
    sad_songs = filter(lambda x: x.split('.')[1] == 'wav',
        [os.path.join(settings.MOOD_DATASET, 'sad',  x) for x in
            os.listdir(os.path.join(settings.MOOD_DATASET, 'sad'))])
    happy_songs = filter(lambda x: x.split('.')[1] == 'wav', 
        [os.path.join(settings.MOOD_DATASET, 'happy', x) for x in
            os.listdir(os.path.join(settings.MOOD_DATASET, 'happy'))])
    relaxed_songs = filter(lambda x: x.split('.')[1] == 'wav', 
        [os.path.join(settings.MOOD_DATASET, 'relaxed', x) for x in
            os.listdir(os.path.join(settings.MOOD_DATASET, 'relaxed'))])
    aggressive_songs = filter(lambda x: x.split('.')[1] == 'wav', 
        [os.path.join(settings.MOOD_DATASET, 'aggressive', x) for x in
           os.listdir(os.path.join(settings.MOOD_DATASET, 'aggressive'))])
    for i in range(7):
        shutil.copyfile(sad_songs[randint(0,111)], 
            os.path.join(settings.MOOD_COLLECTION, 
                'SADTARGET%d.wav' % (i+1)))
        shutil.copyfile(happy_songs[randint(0,111)], 
            os.path.join(settings.MOOD_COLLECTION, 
                'HAPPYTARGET%d.wav' % (i+1)))
        shutil.copyfile(relaxed_songs[randint(0,111)], 
            os.path.join(settings.MOOD_COLLECTION, 
                'RELAXEDTARGET%d.wav' % (i+1)))
        shutil.copyfile(aggressive_songs[randint(0,111)], 
            os.path.join(settings.MOOD_COLLECTION, 
                'AGGRESSIVETARGET%d.wav' % (i+1)))

def create_mood_mosaics():
    from hmosaic.control import HighLevelControl
    from hmosaic.corpus import FileCorpusManager
    from hmosaic import settings
    from hmosaic.utils import get_files_recursive
    targets = get_files_recursive(settings.MOOD_COLLECTION)
    cm = FileCorpusManager(settings.SOURCE_REPO)
    constraints = [settings.HAPPY, 1, settings.RELAXED, 1, settings.AGGRESSIVE, 1,
         settings.SAD, 1]
    con = HighLevelControl(cm, daemon=False)
    # Set identical constraints in both levels of the hieracrchy 
    con.setConstraints(constraints)
    con.setHLConstraints(constraints)
    #con.setHighScope(10) # Adjust this depending on quality of the results
    for t in targets:
        # For each target generate 4 mosaics, 2 for source sorpus, 
        # 1 time-stretched onset segmented, the other fixed size segmentation
        con.setTarget(t)
        con.chop='onsets'
        con.highlevel = True
        con.processTarget()
        #con.chop=500
        #con.processTarget()
        #con.chop='onsets'
        #con.target_chop='onsets'
        #con.process_target_hl()
        for name in ['sunra']:
            con.setSourceCorpus(name)
            con.trackLength(1)
            con.createMosaic()
            con.saveMosaic('hlOnsets%s_%s' % (switch_ext(con.target.filepath, ''), name))
            con.highlevel=False
            con.createMosaic()
            con.saveMosaic('llOnsets%s_%s' % (switch_ext(con.target.filepath, ''), name))
            """
            con.chop=500
            con.target_chop=500
            con.trackLength(0)
            #con.processTarget()
            con.createMosaic()
            con.saveMosaic('llFixed%s_%s' % (switch_ext(con.target.filepath, ''), name))
        con.highlevel=True
        con.process_target_hl()
        for name in ['sunra', 'motown']:
            con.setSourceCorpus(name)   
            con.createMosaic()
            con.saveMosaic('hlFixed%s_%s' % (switch_ext(con.target.filepath, ''), name))
            """
            

    
if __name__ == '__main__':
    create_mood_mosaics()
    #graphs = map_mosaics('testAudio')
    #plot_graphs(graphs)
    sys.exit()
    #create_and_populate()
    #analyse_essentia_files('moods')
    #display_file_values(settings.SAD, settings.HAPPY, settings.RELAXED, settings.AGGRESSIVE)
    #gather_db_data()
    #run_tasks()
    #report_descriptor_accuracy('label.' + settings.MALE, 'label.' + settings.FEMALE)
    #gender_breakdown()
    #
    add_to_db()
    add_gender()
    run_gender_report()
    #create_mood_mosaics()
    #run_gender_analysis()
