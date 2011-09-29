from hmosaic.analyse import EssentiaAnalyser, EssentiaError
from hmosaic import log

def segment_corpus(corpus):
    """
        Reusable script function for segmenting a corpus.
        
    """
    weights = {'rms': 0.8, 'hfc': 0.3, 'complex': 0.2}
    print corpus.list_audio_files()
    for audio_file in corpus.list_audio_files():
        corpus.segment_audio(audio_file, 'onsets')
        #corpus.segment_audio(audio_file, 4000)
        #corpus.segment_audio(audio_file, 1250)
        #corpus.segment_audio(audio_file, 'onsets', weights)     
        

def analyse_corpus(corpus, chop=None):
    """
        Reusable script function for analysing a corpus.
        
    """
    file_list = corpus.list_audio_units(chop=chop)
    analyser = EssentiaAnalyser()
    for audio_file in file_list:
        try:
            analyser.analyse_audio(audio_file)
        except EssentiaError, e:
            log.error("Essentia threw an error (%s), skipping this one: '%s'" 
                % (e, audio_file))

def analyse_corpus_files(corpus):
    """
        Reusable script function for analysing the audio files comprising a corpus.
        
    """
    file_list = corpus.list_audio_files()
    analyser = EssentiaAnalyser()
    for audio_file in file_list:
        try:
            analyser.analyse_audio(audio_file)
        except EssentiaError, e:
            log.error("Essentia threw an error (%s), skipping this one: '%s'" 
                % (e, audio_file))
