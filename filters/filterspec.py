#!/usr/bin/python3
# Generate arbitrary FIR filters from specifications.

import re

import numpy as np
import numpy.fft as npfft
import scipy.interpolate as spi
import scipy.signal as sps

def raw_filter_from_spec(spec, fir_size, fft_real_size, fs):
    """Generate coefficients for a FIR filter from a given specification:
    a 2D array of [frequency, amplitude, phase] rows, sorted in frequency
    order and with phase unwrapped. Intermediate points are interpolated.

    This works by using a large inverse FFT to generate an impulse response,
    which does not necessarily have a smooth response between the points in
    the frequency domain, then windowing the IR to the specified size, which
    smooths it out.

    Returns the FIR filter coefficients, padded to fft_real_size.

    See: Steven W. Smith, "The Scientist and Engineer's Guide to DSP", 2nd
    edition, chapter 17, p299. <https://dspguide.com/>"""

    assert (fir_size % 2) == 1
    assert fft_real_size >= fir_size

    # Get views of the columns in the spec
    spec_t = spec.transpose()
    freq_spec = spec_t[0]
    amp_spec = spec_t[1]
    phase_spec = spec_t[2]

    # Size of the FFT input and output
    fft_complex_size = (fft_real_size // 2) + 1

    # Frequency of each bin, up to the last frequency given in the spec
    freq_per_bin = (fs / 2) / fft_complex_size
    nonzero_bins = min(int(freq_spec[-1] / freq_per_bin) + 1, fft_complex_size)
    bin_freqs = np.arange(nonzero_bins) * freq_per_bin

    # Convert complex response spec to amplitude and unwrapped phase,
    # then interpolate to give amplitude/phase for each bin
    amp_interp = spi.interp1d(freq_spec, amp_spec, kind='cubic')
    phase_interp = spi.interp1d(freq_spec, phase_spec, kind='cubic')
    bin_amps = amp_interp(bin_freqs)
    bin_phases = phase_interp(bin_freqs)

    # Convert back into complex input data for the IFFT
    complex_data = np.zeros(fft_complex_size, dtype=np.cdouble)
    complex_data[:nonzero_bins] = bin_amps * (np.cos(bin_phases) + 1.0j * np.sin(bin_phases))

    # Run the IFFT, giving a real result
    impulse = npfft.irfft(complex_data)

    # Rotate and window the result to get the FIR filter
    impulse[:] = np.roll(impulse, fir_size // 2)
    impulse[:fir_size] *= sps.get_window('hamming', fir_size)
    impulse[fir_size:] = 0.0
    return impulse

def fir_filter_from_spec(spec, fir_size, fs):
    """As raw_filter_from_spec, returning FIR filter coefficients."""

    # Determine size of the FFT, making sure it's much bigger than the output
    fft_real_size = 1024
    while fft_real_size < (64 * fir_size):
        fft_real_size *= 2

    # Generate the filter
    impulse = raw_filter_from_spec(spec, fir_size, fft_real_size, fs)
    return impulse[:fir_size]

def fft_filter_from_spec(spec, fir_size, fft_real_size, fs):
    """As raw_filter_from_spec, returning the filter in FFT form."""

    # Generate the filter
    impulse = raw_filter_from_spec(spec, fir_size, fft_real_size, fs)

    # Rotate the FIR filter back, so it doesn't add a delay
    impulse[:] = np.roll(impulse, (-len(impulse)) // 2)

    return npfft.rfft(impulse)

def read_ngspice_spec(in_fn):
    """Read the output of an ngspice simulation as a filter spec.
    This assumes that your circuit's output is called 'out',
    and the input is always 1.0+0.0j."""

    spec = None
    num_rows = None

    with open(in_fn) as f:
        while True:
            line = f.readline()
            if line == "":
                break
            line = line.strip()

            # Read frequencies
            m = re.match(r'^<indep frequency (\d+)>$', line)
            if m is not None:
                # Add an extra row for 0 Hz
                num_rows = int(m.group(1)) + 1
                spec = np.zeros((num_rows, 3), dtype=np.double)

                # Assume the 0 Hz point has 0 amplitude
                # (This obviously won't be true for all filters!)
                spec[0][0:3] = 0.0

                for i in range(num_rows - 1):
                    line = f.readline().strip()
                    spec[i + 1][0] = float(line)

            # Read output
            if line == '<dep ac.v(out) frequency>':
                for i in range(num_rows - 1):
                    line = f.readline().strip()
                    m = re.match(r'^(.*)([+-])j(.*)$', line)

                    # Convert to amplitude/phase form
                    value = complex(float(m.group(1)),
                                    float(m.group(2) + m.group(3)))
                    spec[i + 1][1] = np.abs(value)
                    spec[i + 1][2] = np.angle(value)

    spec_t = spec.transpose()

    # Normalise the amplitudes
    spec_t[1] /= np.max(spec_t[1])

    # Unwrap the phases (for ease of interpolation later)
    spec_t[2] = np.unwrap(spec_t[2])

    return spec

# XXX Trim spec to remove values that could be interpolated accurately

def specs_to_python(specs, out_fn):
    """Write filter specs to a Python file.
    specs is [("name1", spec1), ("name2", spec2) ...]."""

    with open(out_fn, 'w') as f:
        f.write('# Generated by compute-efm-filter\n\n')
        f.write('import numpy as np\n\n')

        for name, spec in specs:
            f.write('%s = np.array([\n' % name)
            for row in spec:
                f.write('    [%s],\n' % (', '.join(str(v) for v in row)))
            f.write('    ], np.double)\n\n')
