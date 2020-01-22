#!/usr/bin/python3
# Utilities for EFM filtering.

import numpy as np
import pyfftw
import scipy.interpolate as spi
import scipy.signal as sps

SAMPLE_RATE = 40e6

class FFTFilter:
    """A generic FFT-based filter."""

    def __init__(self, real_size=1 << 11, sample_rate=SAMPLE_RATE):
        """Initialise the filter, using blocks of real_size samples."""

        # We will apply the FFT to real_size samples at a time, in blocks that
        # overlap by half_size samples.
        self.real_size = real_size
        self.half_size = real_size // 2
        self.complex_size = (real_size // 2) + 1

        # The width of each bin in Hz.
        # (This isn't used by apply, but it's handy when writing freqfunc.)
        self.sample_rate = sample_rate
        self.freq_per_bin = (self.sample_rate / 2) / self.complex_size

        # Symmetric window for the FFT, so we can just add output blocks together
        self.forward_window = sps.windows.hann(self.real_size, sym=False)

    def process(self, readfunc, writefunc, freqfunc):
        """Process a stream of data through a frequency-domain filter. This
        takes three callback functions:

        readfunc(size) -> data
          Read exactly size samples from the input, returning a numpy array.
          At the end of the file, return a short (or 0-length) array.

        writefunc(data)
          Write a numpy array of samples to the output.

        freqfunc(comp)
          Perform the frequency-domain filter in place on a numpy array of
          complex FFT bins. The bins correspond to frequencies
          0 ... sample_rate/2 (i.e. freq_per_bin Hz in each bin)."""

        # Aligned buffers for FFT input/output
        fft_real = pyfftw.empty_aligned(self.real_size, np.float64)
        fft_complex = pyfftw.empty_aligned(self.complex_size, np.complex128)

        # Plan the forward and inverse FFTs.
        # (This will be expensive the first time but cheap for repeated calls,
        # because PyFFTW caches the plans.)
        forward_fft = pyfftw.FFTW(fft_real, fft_complex)
        inverse_fft = pyfftw.FFTW(fft_complex, fft_real, direction='FFTW_BACKWARD')

        # We work through the input in blocks of half_size samples, padding at
        # both ends with zeros.
        #
        # So the input:
        #         aaa bbb ccc dd
        #
        # will be processed as:
        #     000 aaa
        #         aaa bbb
        #             bbb ccc
        #                 ccc dd0
        #                     dd0 000

        first_block = True
        prev_input = np.zeros(self.half_size, np.float64)
        prev_input_len = self.half_size
        prev_output = np.zeros(self.half_size, np.float64)
        while True:
            # The left half of the FFT input is the right half from last time
            fft_real[:self.half_size] = prev_input

            if prev_input_len == 0:
                # Optimisation: the last read returned 0 samples (so the total
                # length of the data was a multiple of the FFT size). We
                # wouldn't produce any output from this final FFT so we can
                # stop now.
                break
            elif prev_input_len < self.half_size:
                # We read (and padded) a partial input block last time, so this
                # will be our last output
                input_len = 0
                fft_real[self.half_size:] = 0.0
            else:
                # Read the next half_size samples
                input_data = readfunc(self.half_size)
                input_len = len(input_data)
                fft_real[self.half_size:self.half_size + input_len] = input_data

                if input_len < self.half_size:
                    # Last partial input block -- pad with zeros
                    fft_real[self.half_size + input_len:] = 0.0

                prev_input[:] = fft_real[self.half_size:]

            # Apply the window function and do the FFT.
            # This is a real-to-complex FFT so the result has frequencies 0 to
            # SAMPLE_RATE / 2.
            fft_real *= self.forward_window
            forward_fft()

            # Apply the frequency-domain filter
            freqfunc(fft_complex)

            # Do the inverse FFT
            inverse_fft()

            if first_block:
                # The first output block is padding; discard it
                first_block = False
            else:
                # Add the right half of the previous FFT result to the left
                # half of this one, giving us an output block
                fft_real[:self.half_size] += prev_output

                # Write it, trimmed to the length of the corresponding input
                # from last time
                writefunc(fft_real[:prev_input_len])
                if prev_input_len < self.half_size:
                    # And that's the end of the input, so we can stop
                    break

            prev_input_len = input_len
            prev_output[:] = fft_real[self.half_size:]

    def apply(self, input_data, freqfunc, dtype=np.float64):
        """Process a numpy array through a frequency-domain filter, returning a
        new numpy array of results of type dtype.

        freqfunc(comp)
          Perform the frequency-domain filter in place on a numpy array of
          complex FFT bins. The bins correspond to frequencies
          0 ... sample_rate/2 (i.e. freq_per_bin Hz in each bin)."""

        input_pos = [0]
        def readfunc(size):
            end = min(input_pos[0] + size, len(input_data))
            data = input_data[input_pos[0]:end]
            input_pos[0] = end
            return data

        output_data = np.zeros(len(input_data), dtype)
        output_pos = [0]
        def writefunc(data):
            end = output_pos[0] + len(data)
            output_data[output_pos[0]:end] = data
            output_pos[0] = end

        self.process(readfunc, writefunc, freqfunc)

        assert input_pos[0] == len(input_data)
        assert output_pos[0] == len(input_data)
        return output_data

class EFMEqualiser:
    """Frequency-domain equalisation filter for the LaserDisc EFM signal.

    This was inspired by the input signal equaliser in WSJT-X, described in
    Steven J. Franke and Joseph H. Taylor, "The MSK144 Protocol for
    Meteor-Scatter Communication", QEX July/August 2017.
    <http://physics.princeton.edu/pulsar/k1jt/MSK144_Protocol_QEX.pdf>
    """

    def __init__(self):
        # Frequency bands
        self.freqs = np.linspace(0.0e6, 2.0e6, num=11)

        # Amplitude and phase adjustments for each band.
        # These values were adjusted empirically based on a selection of NTSC and PAL samples.
        self.amp = np.array([0.0, 0.2, 0.41, 0.73, 0.98, 1.03, 0.99, 0.81, 0.59, 0.42, 0.0])
        self.phase = np.array([0.0, -0.95, -1.05, -1.05, -1.2, -1.2, -1.2, -1.2, -1.2, -1.2, -1.2])

        self.coeffs = None

    def compute(self, fft):
        """Compute filter coefficients for the given FFTFilter."""

        # Anything above the highest frequency is left as zero.
        self.coeffs = np.zeros(fft.complex_size, dtype=np.complex)

        # Generate the frequency-domain coefficients by cubic interpolation between the equaliser values.
        a_interp = spi.interp1d(self.freqs, self.amp, kind="cubic")
        p_interp = spi.interp1d(self.freqs, self.phase, kind="cubic")
        nonzero_bins = int(self.freqs[-1] / fft.freq_per_bin) + 1
        bin_freqs = np.arange(nonzero_bins) * fft.freq_per_bin
        bin_amp = a_interp(bin_freqs)
        bin_phase = p_interp(bin_freqs)

        # Scale by the amplitude, rotate by the phase
        self.coeffs[:nonzero_bins] = bin_amp * (np.cos(bin_phase) + (complex(0, -1) * np.sin(bin_phase)))

    def filter(self, comp):
        """Frequency-domain filter function to use with FFTFilter."""

        comp *= self.coeffs

class VideoEqualiser(EFMEqualiser):
    """Frequency-domain equalisation filter for TBC video."""

    def __init__(self):
        # Frequency bands
        self.freqs = np.linspace(0.0e6, 15e6, num=4)

        # Amplitude and phase adjustments for each band.
        # These values were adjusted empirically based on a selection of NTSC and PAL samples.
        self.amp = np.ones(len(self.freqs), np.float)
        self.phase = np.zeros(len(self.freqs), np.float)

        self.coeffs = None

if __name__ == "__main__":
    # Test FFTFilter with various sizes of data to ensure blocking works properly
    fft = FFTFilter()
    for size in (0, 1, 1000, fft.real_size - 1, fft.real_size, fft.real_size + 1, 500000):
        print("Testing FFTFilter.apply, size", size)
        input_data = np.linspace(-12345, 12345, size)
        def doublefunc(comp):
            comp *= 2
        output_data = fft.apply(input_data, doublefunc)
        assert np.allclose(input_data * 2, output_data)

    eq = EFMEqualiser()
    for gain in (0, 1, 2):
        print("Testing EFMEqualiser, gain", gain)

        eq.amp[:] = gain
        eq.phase[:] = 0
        eq.compute(fft)

        # This has to be a low-frequency signal (and an approximate match)
        # because EFMEqualiser is still doing an LPF above the top frequency
        # band...
        input_data = np.sin(np.linspace(0, 4 * np.pi, 5000))
        output_data = fft.apply(input_data, eq.filter)
        assert np.allclose(input_data * gain, output_data, atol=0.1)
