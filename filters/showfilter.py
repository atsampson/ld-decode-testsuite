#!/usr/bin/python3
# Visualise filter properties.

import collections
import numpy as np
import scipy.interpolate as sint
import scipy.signal as sps
import matplotlib.pyplot as plt

Filter = collections.namedtuple('Filter', ['name', 'b', 'a', 'awkward'],
                                defaults=[[1.0], False])
Ideal = collections.namedtuple('Ideal', ['name', 'fs', 'vs', 'tols'],
                               defaults=[None])

def print_filter(fil):
    def consts(nums):
        for i in range(0, len(nums), 5):
            print('    ', ' '.join(str(c) + ',' for c in nums[i:i+5]))

    if np.allclose(fil.a, [1.0]):
        print('%s <%d> = {' % (fil.name, len(fil.b)))
        consts(fil.b)
        print('};')
    else:
        print('%s <%d, %d> = {' % (fil.name, len(fil.b), len(fil.a)))
        consts(fil.b)
        print('}, {')
        consts(fil.a)
        print('};')

def analyse_filter(fil, fs, w):
    h = np.zeros(len(w), dtype=complex)

    for i, freq in enumerate(w):
        # We can't do this for frequency 0
        if freq < 1000:
            h[i] = 0.0
            continue

        # Generate a cos waveform at frequency freq.
        # We want at least 10 cycles, and at least 4 multiples of the filter
        # length.
        num_cycles = 10.0
        num_samples = int((fs * num_cycles) / freq)
        filter_len = 4 * max(len(fil.a), len(fil.b))
        num_samples = max(num_samples, filter_len)
        assert num_samples < 1e9

        phases = (np.linspace(0.0, float(num_samples), num_samples)
                  * 2.0 * np.pi / (fs / freq))
        wave_in = 2.0 * np.cos(phases)

        # Filter it
        wave_out = sps.lfilter(fil.b, fil.a, wave_in)

        # Detect it using a quadrature carrier
        carrier = np.e ** (-1.0j * phases)
        h[i] = np.sum(wave_out * carrier) / len(wave_out)

    return w, h

def show_filters(filters, fs, maxfreq=None, ideal_dbs=[], ideal_delays=[]):
    if maxfreq is None:
        maxfreq = fs / 2

    fig, (linax, logax, phaseax, grpax) = plt.subplots(4)

    POINTS = 65536

    for fil in filters:
        print_filter(fil)

        w = np.linspace(0, maxfreq, POINTS)
        if fil.awkward:
            w, h = analyse_filter(fil, fs, w)
        else:
            w, h = sps.freqz(fil.b, fil.a, fs=fs, worN=w)
        linax.plot(w, np.abs(h))
        logax.plot(w, 20 * np.log10(np.abs(h)))
        phaseax.plot(w, np.angle(h))

        dw, d = sps.group_delay((fil.b, fil.a), w, fs=fs)
        grpax.plot(dw, d - d[0])

    for ideal in ideal_dbs:
        xs = np.linspace(ideal.fs[0], ideal.fs[-1], num=POINTS)
        vs_interp = sint.interp1d(ideal.fs, ideal.vs, kind='quadratic')(xs)
        logax.plot(ideal.fs, ideal.vs, 'o')
        if ideal.tols is not None:
            tols_interp = sint.interp1d(ideal.fs, ideal.tols, kind='quadratic')(xs)
            logax.fill_between(xs, vs_interp - tols_interp, vs_interp + tols_interp, alpha=0.2)

    for ideal in ideal_delays:
        xs = np.linspace(ideal.fs[0], ideal.fs[-1], num=POINTS)
        vs_interp = sint.interp1d(ideal.fs, ideal.vs, kind='quadratic')(xs)
        grpax.plot(ideal.fs, ideal.vs, 'o')
        if ideal.tols is not None:
            tols_interp = sint.interp1d(ideal.fs, ideal.tols, kind='quadratic')(xs)
            grpax.fill_between(xs, vs_interp - tols_interp, vs_interp + tols_interp, alpha=0.2)

    for ax in (linax, logax, phaseax, grpax):
        if ax is logax:
            extras = [ideal.name for ideal in ideal_dbs]
        elif ax is grpax:
            extras = [ideal.name for ideal in ideal_delays]
        else:
            extras = []
        ax.legend(['%s <%d>' % (fil.name, len(fil.b)) for fil in filters] + extras)
        ax.set_xlabel('Frequency')
        ax.set_xlim(0, maxfreq)
        ax.grid(True)
    linax.set_ylabel('Magnitude response (linear)')
    logax.set_ylabel('Magnitude response (dB)')
    phaseax.set_ylabel('Phase')
    grpax.set_ylabel('Relative group delay (samples)')

    plt.show()
