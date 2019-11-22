#!/usr/bin/python3
# Utilities for EFM filtering.

import numpy as np
import pyfftw
import scipy.signal as sps

SAMPLE_RATE = 40e6

class FFTFilter:
    """A generic FFT-based filter."""

    def __init__(self, real_size=1 << 16, sample_rate=SAMPLE_RATE):
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

    def apply(self, data, freqfunc):
        """Transform data into the frequency domain using the FFT, apply
        freqfunc to it, then transform it back to the time domain and return
        the result.

        freqfunc's argument is a PyFFTW array of size complex_size, which it
        should modify in place."""

        # Aligned buffers for FFT input/output
        fft_real = pyfftw.empty_aligned(self.real_size, np.float64)
        fft_complex = pyfftw.empty_aligned(self.complex_size, np.complex128)

        # Plan the forward and inverse FFTs.
        # (This will be expensive the first time only.)
        forward_fft = pyfftw.FFTW(fft_real, fft_complex)
        inverse_fft = pyfftw.FFTW(fft_complex, fft_real,
                                       direction='FFTW_BACKWARD')

        # Symmetric window for the FFT, so we can just add output blocks together
        forward_window = sps.windows.hann(self.real_size, sym=False)

        # Work through the input data in half_size blocks.
        # We must overlap by half a block at each end.
        length = len(data)
        output = np.zeros(length, np.float64)
        prev_block = np.zeros(self.half_size, np.int16)
        for pos in range(0, length + self.half_size, self.half_size):
            # Copy data from the input, padding with zeroes
            right = min(length, pos + self.half_size)
            if (right - pos) == self.half_size:
                block = data[pos:right]
            else:
                block_right = max(0, right - pos)
                block = np.zeros(self.half_size, np.int16)
                block[:block_right] = data[pos:right]

            # Make up the FFT's input
            fft_real[:self.half_size] = prev_block
            fft_real[self.half_size:] = block
            prev_block = block

            # Apply the window function and do the FFT.
            # This is a real-to-complex FFT so the result has frequencies 0 to
            # SAMPLE_RATE / 2.
            fft_real *= forward_window
            forward_fft()

            # Apply the frequency-domain filter
            freqfunc(fft_complex)

            # Do the inverse FFT
            inverse_fft()

            # Merge the inverse FFT output into the output buffer
            orig_left = pos - self.half_size
            left = max(0, orig_left)
            right = min(length, pos + self.half_size)
            output[left:right] += fft_real[left - orig_left:right - orig_left]

        return output

if __name__ == "__main__":
    # Test with various sizes of data to ensure blocking works properly
    fft = FFTFilter()
    for size in (0, 1, 1000, fft.real_size - 1, fft.real_size, fft.real_size + 1, 500000):
        print("Testing FFTFilter.apply, size", size)
        input_data = np.linspace(-12345, 12345, size)
        def doublefunc(comp):
            comp *= 2
        output_data = fft.apply(input_data, doublefunc)
        assert np.all(np.abs((input_data * 2) - output_data) < 1e-6)
