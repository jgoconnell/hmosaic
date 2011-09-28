#!/usr/bin/env python

# Third party imports 
from pylab import show, plot, legend, xlim, xlabel, ylabel, title, figure, scatter
import numpy as np

# Project imports
from hmosaic.utils import get_db_connection
from hmosaic.models import DBSegment, DBSong
from hmosaic.scripts.processTestData import map_mosaics, dataset_metrics


def scatterPlotIt():
    """
        Makes scatterplots based on the results of
        the gender analysis for songs and segments.

    """
    from hmosaic.utils import get_db_connection
    from hmosaic.models import DBSegment, DBSong

    store = get_db_connection('gender24.db')
    results = store.find((DBSegment, DBSong),DBSegment.song_name == DBSong.song_name)
    handles = []
    myColors = []
    xlabel('Male <-----> Female (Segments)')
    ylabel('Male <-----> Female (Songs)')
    title('Time resolution of the Gender classifier')

    for r in results:
        if r[0].segment_duration == 2000:
            handles.append(scatter(r[0].female, r[1].female, c='blue', s=10, alpha=0.5))
            myColors.append('blue')
        elif r[0].segment_duration == 4000:
            handles.append(scatter(r[0].female, r[1].female, c='green', s=10, alpha=0.5))
            myColors.append('green')
    #legend(handles)

def barChartIt():
    """
        Makes a bar chart based on the results of
        the gender analysis for songs and segments.

    """
    
    store = get_db_connection('gender24.db')
    results = store.find((DBSegment, DBSong),DBSegment.song_name == DBSong.song_name)

    results
    correct_segs = []
    incorrect_segs = []
    for r in results:
        if r[1].female > 0.5:
            if r[0].female > 0.5:
                correct_segs.append(r[0])
            else:
                incorrect_segs.append(r[0])
        else:
            if r[0].male > 0.5:
                correct_segs.append(r[0])
            else:
                incorrect_segs.append(r[0])
    correct_4secs = [x for x in correct_segs if x.segment_duration==4000]
    correct_2secs = [x for x in correct_segs if x.segment_duration==2000]
    incorrect_2secs = [x for x in incorrect_segs if x.segment_duration==2000]
    incorrect_4secs = [x for x in incorrect_segs if x.segment_duration==4000]
    total_2secs = len(correct_2secs) + len(incorrect_2secs)
    total_4secs = len(correct_4secs) + len(incorrect_4secs)
    p2correct = ((float(len(correct_2secs)))/float(total_2secs)) * 100
    p2incorrect = ((float(len(incorrect_2secs)))/float(total_2secs)) * 100
    p4correct = ((float(len(correct_4secs)))/float(total_4secs)) * 100
    p4incorrect = ((float(len(incorrect_4secs)))/float(total_4secs)) * 100

    
    N = 2
    width = 0.35
    ind = np.arange(N)
    correct = (p2correct, p4correct)
    incorrect = (p2incorrect, p4incorrect)
    fig = figure()
    ax = fig.add_subplot(111)
    rects1 = ax.bar(ind, correct, width, color='green')
    rects2 = ax.bar(ind+width, incorrect, width, color='red')
    ax.set_ylabel('% of segments classified')
    ax.set_title('% of correctly and incorrectly classified segments by duration')
    ax.set_xticks(ind+width)
    ax.set_xticklabels(('2 second duration\n Total of %d segments' % total_2secs, '4 second duration\n Total of %d segments' % total_4secs))
    ax.legend((rects1[0], rects2[0]), ('Correct', 'Incorrect'))


def moodBarChart(mood, metrics=None):
    """
        PAss the metrics object in from the dataset_metrics function,
        along with a mood to pl

    """
    if metrics is None:
        results = map_mosaics('moodexperiment', 5000, False, 0.3)
        metrics = dataset_metrics(results)
    
    N = 28
    width = 0.2
    ind = np.arange(N)
    #hlp = re.compile('hl.+MOSAIC.wav')
    #llp = re.compile('ll.+MOSAIC.wav')
    map(list.sort, [metrics[mood][t] 
        for t in metrics[mood]])
    llScores = [metrics[mood][t][1] 
        for t in metrics[mood]]
    hlScores = [metrics[mood][t][0] 
        for t in metrics[mood]]
    labels = [k for k in metrics[mood].keys()]
    map(list.sort, [labels, hlScores, llScores])
    combscores = zip([float((1-s[1])*100) 
        for s in llScores], 
            [float((1-s[1])*100) for s in hlScores])
    better = 0
    for p in combscores:
        if p[0] < p[1]:
            better += 1
    fig = figure()
    ax = fig.add_subplot(111)
    rects1 = ax.bar(ind, [float((1-s[1])*100) 
        for s in hlScores], width, color='green')
    rects2 = ax.bar(ind+width, [float((1-s[1])*100) 
        for s in llScores], width, color='yellow')
    ax.set_ylabel('Similarity to Target (%)')
    ax.set_xlabel('Hierachical and Non-Hierarchical Mosaics for each %s target in the dataset' % mood)
    #ax.set_title('Hierarchical model performs better in %d out of 28 cases' % (better))
    #ax.set_xticks(ind+width)
    #ax.set_xticklabels(labels)
    ax.legend((rects1[0], rects2[0]), 
        ('Hierchical Model', 'Non-Hierarchical Model'))
    
    
def plotPerfBars(ll_array, full_array):
    """
        Get the normalised processing times and plot

    """
    
    
    N = 1
    width = 0.35
    ind = np.arange(N)
    
    fig = figure()
    ax = fig.add_subplot(111)
    rects1 = ax.bar(ind, full_array.mean(), width=width, color='green', yerr=full_array.std())
    rects2 = ax.bar(ind+width, ll_array.mean(), width=width, color='yellow', yerr=ll_array.std())
    ax.set_ylabel('Average Processing Time Normalised by Audio Length')
    ax.set_xlabel('Performance comparision - with and without high level descriptors')
    
    ax.set_xticks(np.arange(1)+width)
    ax.set_xticklabels([''])
    ax.legend((rects1[0], rects2[0]), 
        ('Full Extractor', 'Low Level Extractor'))


def plot_mosaic_curves(g, key, tune):
    """
        Takes the graph from **hmosaic.scripts.processTestData.map_mosaics**,
        along with values for mood key and tune and plots the graphs.

    """
    hl = g[key]['HL'+tune+'.wav']
    ll = g[key]['LL'+tune+'.wav']
    tar  = g[key]['TARGET.wav']
    limit = min(map(len, [hl,ll,tar]))
    title("%s mood curves over time for %s" % (key, tune))
    xlim(0,limit)
    ylabel("%s Value" % key)
    xlabel('Number of 5 second segments analysed')
    plot(tar, 'r')
    plot(ll, 'b')
    plot(hl, 'g')
    labels = ('target', 'non-hierarchical', 'hierarchical')
    legend(labels) 


if __name__ == '__main__':
    
    barChartIt()
    show()



