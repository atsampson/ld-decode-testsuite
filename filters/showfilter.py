#!/usr/bin/python3
# Visualise filter properties.

import collections
import numpy as np
import scipy.interpolate as sint
import scipy.signal as sps
import matplotlib.pyplot as plt

Filter = collections.namedtuple('Filter', ['name', 'b', 'a'],
                                defaults=[[1.0]])
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

def show_filters(filters, fs, ideal_delays=[]):
    fig, (linax, logax, grpax) = plt.subplots(3)

    for fil in filters:
        print_filter(fil)

        w, h = sps.freqz(fil.b, fil.a, fs=fs)
        linax.plot(w, np.abs(h))
        logax.plot(w, 20 * np.log10(np.abs(h)))
        dw, d = sps.group_delay((fil.b, fil.a), w, fs=fs)
        grpax.plot(dw, d - d[0])

    for ideal in ideal_delays:
        xs = np.linspace(ideal.fs[0], ideal.fs[-1], num=1000)
        vs_interp = sint.interp1d(ideal.fs, ideal.vs, kind='quadratic')(xs)
        grpax.plot(ideal.fs, ideal.vs, 'o')
        if ideal.tols is not None:
            tols_interp = sint.interp1d(ideal.fs, ideal.tols, kind='quadratic')(xs)
            grpax.fill_between(xs, vs_interp - tols_interp, vs_interp + tols_interp, alpha=0.2)

    for ax in (linax, logax, grpax):
        if ax is grpax:
            extras = [ideal.name for ideal in ideal_delays]
        else:
            extras = []
        ax.legend(['%s <%d>' % (fil.name, len(fil.b)) for fil in filters] + extras)
        ax.set_xlabel('Frequency')
        ax.set_xlim(0, fs / 2)
        ax.grid(True)
    linax.set_ylabel('Magnitude response (linear)')
    logax.set_ylabel('Magnitude response (dB)')
    grpax.set_ylabel('Relative group delay (samples)')

    plt.show()
