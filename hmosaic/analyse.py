# -*- coding: utf-8 -*-
"""
Different music content analysers are stored here.
The system was built on top of Essentia, however in order to
use some other analyser you just need to provide
"""

import subprocess, os, re
import numpy as np
from scikits.audiolab import wavread



from hmosaic.utils import switch_ext, load_yaml 
from hmosaic import log, settings


class EssentiaError(Exception):
    """
    """
    pass

class EssentiaAnalyser:
    """
        Is used for invoking the binary essentia analyser.
        It may be run in batch mode or for a single file.
        The extracted analysis is always written to a .yaml
        file with the same filepath as the original .wav file
        which was presented for analysis.

    """

    def __init__(self):
        """
            Sets the essentia binary to the path stored in settings.

        """    
        self.ESSENTIA_BIN = os.path.join(settings.ESSENTIA_BIN_DIR, settings.DEFAULT_ANALYSER)  
        
    def analyse(self, audio_files):
        """
             Parameter is a list of audio files.
             A generator is returned with the analysis data for each file.

        """
        for filepath in audio_files:
            yield self.analyse_audio(filepath)
            
    def set_bin(self, bin_name):
        """
            Allows dynamic switching of binary analysers, e.g. for analysing 
            solely low level features one can enjoy a much faster analysis 
            process by switching the analyser binary. The only constraint is 
            that the new binary must be stored in the same directory as the 
            default setting (read from settings.py)

        """
        new_bin = os.path.join(settings.ESSENTIA_BIN_DIR, bin_name)
        if os.path.isfile(new_bin):
            log.info("Using new essentia bin: '%s'" % new_bin)
            self.ESSENTIA_BIN = new_bin
        else:
            log.error("'%s' is not a file, keeping original: '%s'" 
               % (new_bin, self.ESSENTIA_BIN))
    
    def analyse_audio(self,audio_filepath):
        """
            This function invokes the essentia binary.
            Reads in the output file, deletes the file 
            and returns a dictionary.
            
        """
    
        #We actuallly have to be in the same directory as the streaming
        # extracor in order to make this work....
        current_dir = os.getcwd()
        os.chdir(settings.ESSENTIA_BIN_DIR)
        
        command = [self.ESSENTIA_BIN, audio_filepath, \
            switch_ext(audio_filepath, '.yaml')]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, \
        stderr = subprocess.PIPE)
        (stdout, stderr) = process.communicate()
        log.debug('%s \n %s' % (stdout, stderr))
        pat = re.compile('ERROR.+$')
        match = pat.search(stdout)
        
        os.chdir(current_dir)

        if match:
            raise EssentiaError(match.group())
        # Change this to return the analysis filepath!!
        return audio_filepath


# This function returns the magnitude of the positive spectrum from the 
# fft frame.
pos_spec = lambda fft_frame: abs(fft_frame[0:len(fft_frame)/2 - 1])

# This function finds all magnitudes in a certain frequency range
# It is, effectively speaking, a band pass filter.
find_mags = lambda mag, freq_bins, val1, val2: \
    [mag[index] for index, val in enumerate(freq_bins) \
        if val >= val1 and val <= val2]


# This is a function to get the next power of 2 up from the given window_size
next_pow2 = lambda window_size: int(np.power(2, np.ceil(np.log2(window_size))))

# This function returns an array of frequency values in Hz which indicate
# the centre frequency of each bin in the positive part of the spectrum
# for a given fft size and sample rate
get_freq_bins = lambda fft_size, sample_rate: np.array(range(1, fft_size/2)) * \
    float(sample_rate)/float(fft_size)


class LoudnessAnalyser(object):
    """
    """

    def __init__(self,  hop_size=512, window_size=1024):
        """
        """
        self.window_size = window_size
        self.fft_size = next_pow2(self.window_size)
        self.hop_size = hop_size
        self.window = np.hamming(self.window_size)

    def get_loudness(self, filepath):
        """
        """
        
        
        # Read in the file and extract samples, sample rate and format
        filepath = filepath
        (audio_data, self.sample_rate, file_format) = wavread(filepath)
        
        # Set the low band and build our logarithmic frequency ranges up as
        # far as the Nyquist.
        lowband = 100.0
        no_bands = 8.0
        freq_bands = np.concatenate((np.array([0.0]), np.array(\
            lowband * np.power((float(self.sample_rate)/2.0/lowband), \
                np.arange(no_bands)/(no_bands - 1)))
        ))
        print ("Freq_bands: %s" % freq_bands )
        # Define a function to calculate the energy
        calc_energy = lambda mag: np.power(sum(mag), 2)
        
        # Get centre frequency of each bin in Hz    
        freq_bins = get_freq_bins(self.fft_size, self.sample_rate)
        # Create a container for the value in each band at each hop and then..
        # loop!
        energy_bands = np.zeros((len(audio_data)/self.hop_size, no_bands), dtype='single')
        for index, frame in enumerate(self.get_frames(audio_data)):
            fft_frame = self.fft(frame)
            mag = pos_spec(fft_frame.astype('single'))
            for ind, freq in enumerate(freq_bands):
                if ind == 0:
                    prev_freq = freq
                else:
                    #print "Calculating energy of band: %f to %f" \
                        #% (prev_freq, freq)
                    energy_bands[index, ind-1] = \
                        calc_energy(find_mags(mag, freq_bins, prev_freq, freq))
                    prev_freq = freq
        
        #Take the log of the energy values            
        energy = 10*np.log10(energy_bands + 0.0001)
        return energy

    def get_frames(self, audio_data):
        """ 
            Generator function to return frames of the audio. 
            Only yield complete frames. No zero padding. We ditch
            leftover samples that can't fill a frame.
            
        """
        for frame_begin in range(0, len(audio_data), self.hop_size):
            frame = np.array(audio_data[frame_begin:frame_begin+self.window_size])
            if len(frame) == self.window_size: # Ignore leftover samples. Who cares...
                yield frame
            
    def fft(self, audio_frame):
        """
            Generates frames of raw fft'ed audio.
            Window size is set to self.frame_size so it might be an idea to
            set this to 701 or something before calling this function.
            The middle sample in the window stays at 0 - is this correct?

        """
        # Window the frame
           
        
        win_frame = audio_frame * self.window
            
        # Center the frame
        centred_frame = np.zeros(self.window_size)
            
        centred_frame[0:(self.window_size/2)-1] = \
            win_frame[self.window_size/2:self.window_size-1]
        centred_frame[self.window_size/2:self.window_size-1] = \
            win_frame[0:(self.window_size/2)-1]
        return np.fft.fft(centred_frame, self.fft_size)



if __name__ == '__main__':
    log.info("TODO - write a script to parameterise the analyser...")
