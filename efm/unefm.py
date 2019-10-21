#!/usr/bin/python3
# Try (unsuccessfully) to decode EFM from GNU Radio.

import numpy
import scipy.cluster
import struct
import sys

def load_bits_from_cr():
    # Output from Clock Recovery MM -> Float to Char (127)
    f = open("/var/tmp/symbols.b", "rb")

    # Skip initial bit where loop is locking up (hopefully)
    f.seek(1000000)

    bits = []
    lastpit = False
    while True:
        b = f.read(1)
        if b == "":
            break
        pit = ord(b) > 127

        if pit != lastpit:
            bits.append(1)
        else:
            bits.append(0)
        if len(bits) == 20000:
            break

        lastpit = pit

    f.close()

idealsize = 40e6 / 4321800

def get_samples():
    #name = "/var/tmp/digital.s16"
    name = "/n/stuff2/capture/laserdisc/out/efmtest-fawlty.preefm.s16"
    with open(name, "rb") as f:
        while True:
            w = f.read(2)
            if w == "":
                return
            yield struct.unpack("h", w)[0]

def get_3samples():
    v0 = 0
    v1 = 0
    for v2 in get_samples():
        yield (v0, v1, v2)
        v0 = v1
        v1 = v2

def get_crossings():
    time = 0
    pitp = False
    xtimep = 0
    for v0, v1, v2 in get_3samples():
        pit = v1 > 0
        if pit != pitp:
            # Interpolate the time of the zero-crossing from v0 and v2
            #t = -(v0 / ((v2 - v0) / 2)) - 1
            # Interpolate the time of the zero-crossing from v0 and v1
            t = -v0 / (v1 - v0)
            xtime = time + t

            pitsize = xtime - xtimep

            #print("flip %10f %10f %10d %10d %10d" % (xtime, t, v0, v1, v2))
            #print("flip %10f %10f" % (xtime, pitsize))
            yield pitsize

            pitp = pit
            xtimep = xtime

        time += 1

fo = open("/var/tmp/unefm.efm", "wb")
sizes = []
for i in get_crossings():
    sizes.append(i)
    if len(sizes) == 1000:

        ssizes = sorted(sizes)
        #print(ssizes)

        """
        print(idealsize, ssizes[140]/3, ssizes[1000-16]/10)

        print(numpy.histogram(sizes, bins=80))
        """

        # Initial rough guess based on where we'd expect the 3s to be...
        spacing = ssizes[140] / 3
        #spacing = ssizes[1000-16] / 10
        print("initial spacing=", spacing)

        guesses = []
        for size in ssizes:
            n = round(size / spacing)
            if n >= 3 and n <= 11:
                guesses.append(size / n)
        spacing = float(numpy.median(guesses))
        print("final spacing=", spacing)

        # Needs weightings - the clusters aren't the same size...
        #codes = [i * spacing for i in range(3, 12)]
        #centres, bins = scipy.cluster.vq.kmeans2(sizes, codes, minit='++')

        for i in range(len(sizes)):
            size = sizes[i]
            value = round(size / spacing)
            #value = bins[i] + 3
            fo.write(bytes([value]))
            print("%10f %10f %10d" % (size, size / spacing, value))

        print("hm", spacing)

        sizes = []

fo.close()

sys.exit(0)

bits = []
print(bits)

pos = 0
sync_header = [1] + ([0] * 10) + [1] + ([0] * 10) + [1, 0]
print(sync_header)
while bits[pos:pos+24] != sync_header:
    pos += 1
print(pos)

def dump(x):
    global pos
    print(bits[pos:pos+x])
    pos += x
dump(24)
dump(3)
dump(14)
dump(3)
for i in range(32):
    dump(14)
    dump(3)
dump(24)



