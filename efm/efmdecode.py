#!/usr/bin/python3
# Utilities for EFM decoding.

import numpy as np

EFM_RATE = 4321800.0

def zero_crossings(data):
    """Given a numpy array of values, return the positions of zero crossings
    within the array. Crossing positions are linearly interpolated between
    samples."""

    # Find locations of crossings: XOR the sign of each sample with the
    # following sample's sign; it'll be 1 if they were different
    # XXX This may need hysteresis as in ld-ldstoefm?
    signs = data >= 0
    crossings = np.nonzero(np.logical_xor(signs[:-1], signs[1:]))

    # At each crossing, linearly interpolate where the crossing occurred between the two samples
    before = data[:-1][crossings]
    after = data[1:][crossings]
    # This can't divide by zero because the two must have different signs!
    return crossings[0] + ((-before) / (after - before))

if __name__ == "__main__":
    def check_nearly_equal(a, b, epsilon=1e-6):
        assert np.all(np.abs(a - b) < epsilon)

    print("Testing zero_crossings")
    crossings = zero_crossings(np.array([1.0, 1.0, 1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, -3.0, -3.0]))
    check_nearly_equal(crossings, [2.5, 5.5, 8.25])
