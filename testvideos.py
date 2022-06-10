#!/usr/bin/python3
# Utilities for working with standard (and not-so-standard) test videos.
#
# Running this module as a script will generate all the encoded video files.

# XXX There's a lot of duplication between the ffmpeg commands...
# XXX mobcal looks quite different from the BBC copy

import logging
import os
import statistics
import subprocess
import sys

testsuite_dir = os.path.realpath(os.path.dirname(sys.argv[0]))
lddecode_dir = os.path.join(testsuite_dir, "..", "ld-decode")

cache_dir = os.path.join(testsuite_dir, "cache", "evaluate")
video_dir = os.path.join(cache_dir, "video")
tmp_dir = "/var/tmp/lddtest/evaluate"

class TestVideo:
    """A video testcase."""

    def __init__(self, name):
        self.name = name

        os.makedirs(video_dir, exist_ok=True)

        self.rgbname = os.path.join(video_dir, name + ".rgb")
        if not os.path.exists(self.rgbname):
            logging.info("Generating %s", self.rgbname)
            self.generate()

        self.tbcname = os.path.join(video_dir, name + ".tbc")
        if not os.path.exists(self.tbcname):
            logging.info("Encoding %s", self.tbcname)
            self.encode()

    def generate(self):
        """Generate the .rgb through whatever mechanism.
        Subclasses should override this."""

        raise NotImplementedError("generate")

    def encode(self):
        """Encode the .rgb into a .tbc."""

        # XXX assumes PAL
        subprocess.check_call([
            os.path.join(lddecode_dir, "tools", "ld-chroma-decoder", "encoder", "ld-chroma-encoder"),
            self.rgbname, self.tbcname,
            ])

class LAVTestVideo(TestVideo):
    """A video testcase generated from a libavfilter test source."""

    def __init__(self, name, source):
        self.source = source
        if "=" in source:
            self.source += ":"
        else:
            self.source += "="
        self.source += "duration=1:size=922x576:rate=25"
        super(LAVTestVideo, self).__init__(name)

    def generate(self):
        subprocess.check_call(["ffmpeg", "-loglevel", "error",
            "-f", "lavfi", "-i", self.source,
            "-filter:v", "pad=928:576:-1:-1",
            "-f", "rawvideo", "-pix_fmt", "rgb48", "-s", "928x576", "-y", self.rgbname,
            ])

class VQEGTestVideo(TestVideo):
    """A video testcase generated from one of the VQEG test sequences.
    These can be downloaded from <https://media.xiph.org/vqeg/TestSequences/>."""

    # XXX could download into the cache dir automatically
    vqeg_dir = "/n/stuff/tv/Test/vqeg"

    def __init__(self, name, yuvname):
        self.yuvname = os.path.join(self.vqeg_dir, yuvname)
        super(VQEGTestVideo, self).__init__(name)

    def generate(self):
        insize = "720x576"
        inrate = "25"
        filters = "scale=922:576,pad=928:576:-1:-1"
        if self.yuvname.endswith("__525.yuv"):
            # 525-line sequence -- pad it to 625-line size.
            # XXX For non-interlaced video, we could scale up to 625-line size instead.
            insize = "720x486"
            inrate = "29.97"
            # To keep the right aspect ratio: scale=648:486
            filters = "scale=922:486,pad=928:576:-1:-1"
        subprocess.check_call(["ffmpeg", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "uyvy422", "-s", insize, "-r", inrate,
            "-i", self.yuvname,
            "-filter:v", filters,
            "-f", "rawvideo", "-pix_fmt", "rgb48", "-s", "928x576", "-y", self.rgbname,
            ])

class LDVTestVideo(TestVideo):
    """A video testcase generated from one of the LDV test sequences produced by SVT.
    These can be downloaded from <https://media.xiph.org/ldv/pub/test_sequences/601/>."""

    # XXX could download into the cache dir automatically
    vqeg_dir = "/n/stuff/tv/Test/ldv"

    def __init__(self, name, yuvname):
        self.yuvname = os.path.join(self.vqeg_dir, yuvname)
        super(LDVTestVideo, self).__init__(name)

    def generate(self):
        subprocess.check_call(["ffmpeg", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", "720x576", "-r", "25",
            "-i", self.yuvname,
            "-filter:v", "scale=922:576,pad=928:576:-1:-1",
            "-f", "rawvideo", "-pix_fmt", "rgb48", "-s", "928x576", "-y", self.rgbname,
            ])

def parse_ffmpeg_stats(filename, want_key):
    """Read a stats file from ffmpeg's psnr or ssim filter.
    Return a list of float values with the given key."""

    values = []
    with open(filename) as f:
        for line in f.readlines():
            for field in line.rstrip().split():
                parts = field.split(":", 1)
                if len(parts) == 2 and parts[0] == want_key:
                    values.append(float(parts[1]))
    return values

def evaluate(testcase, decoder_args):
    """Decode testcase using ld-chroma-decoder with the given args, compare the
    results to the original video, and return (mean PSNR, mean SSIM)."""

    os.makedirs(tmp_dir, exist_ok=True)
    outprefix = os.path.join(tmp_dir, testcase.name + ".out")

    # Start ld-chroma-decoder with output to a pipe
    decoder_cmd = [
        os.path.join(lddecode_dir, "tools", "ld-chroma-decoder", "ld-chroma-decoder"),
        "--quiet",
        "--chroma-gain", "1.0",
        ] + decoder_args + [
        testcase.tbcname, # output to stdout
        ]
    decoder_proc = subprocess.Popen(decoder_cmd, stdout=subprocess.PIPE)

    # Start ffmpeg reading from the pipe.
    # Compute PSNR and SSIM between the input and output .rgb files.
    # The values returned may be "inf" if the output is identical to the input...
    psnrname = outprefix + ".psnr"
    ssimname = outprefix + ".ssim"
    ffmpeg_command = [
        "ffmpeg", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb48", "-s", "928x576", "-i", "-",
        "-f", "rawvideo", "-pix_fmt", "rgb48", "-s", "928x576", "-i", testcase.rgbname,
        "-lavfi", "[0:v][1:v]psnr=stats_file=%s; [0:v][1:v]ssim=stats_file=%s"
            % (psnrname, ssimname),
        "-f", "null", "-",
        ]
    ffmpeg_proc = subprocess.Popen(ffmpeg_command, stdin=decoder_proc.stdout)

    # Wait for the two processes to finish
    rc = decoder_proc.wait()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, decoder_cmd)
    rc = ffmpeg_proc.wait()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, ffmpeg_cmd)

    # Read the per-frame stats back from ffmpeg
    psnrs = parse_ffmpeg_stats(psnrname, "psnr_avg")
    psnr = statistics.mean(psnrs)
    ssims = parse_ffmpeg_stats(ssimname, "All")
    ssim = statistics.mean(ssims)

    return psnr, ssim

def get_testcases():
    """Ensure all the testcases have been generated, and return a dict of them."""

    testcases = {}
    for testcase in [
        LAVTestVideo("lavfi-magenta", "color=c=0xBF00BF"),
        LAVTestVideo("lavfi-testsrc", "testsrc"),
        LAVTestVideo("lavfi-pal75bars", "pal75bars"),

        # Names for these come from frtv_phase1_final_report.doc
        VQEGTestVideo("vqeg-tree", "src1_ref__625.yuv"),
        VQEGTestVideo("vqeg-barcelona", "src2_ref__625.yuv"),
        VQEGTestVideo("vqeg-harp", "src3_ref__625.yuv"),
        VQEGTestVideo("vqeg-movinggraphic", "src4_ref__625.yuv"),
        VQEGTestVideo("vqeg-canoavalsesia", "src5_ref__625.yuv"),
        VQEGTestVideo("vqeg-f1car", "src6_ref__625.yuv"),
        VQEGTestVideo("vqeg-fries", "src7_ref__625.yuv"),
        VQEGTestVideo("vqeg-horizontalscrolling", "src8_ref__625.yuv"),
        VQEGTestVideo("vqeg-rugby", "src9_ref__625.yuv"),
        VQEGTestVideo("vqeg-mobilecalendar", "src10_ref__625.yuv"),

        VQEGTestVideo("vqeg-balloonpops", "src13_ref__525.yuv"),
        VQEGTestVideo("vqeg-newyork", "src14_ref__525.yuv"),
        #VQEGTestVideo("vqeg-mobilecalendar525", "src15_ref__525.yuv"),
        VQEGTestVideo("vqeg-betespasbetes", "src16_ref__525.yuv"),
        VQEGTestVideo("vqeg-lepoint", "src17_ref__525.yuv"),
        VQEGTestVideo("vqeg-autumnleaves", "src18_ref__525.yuv"),
        VQEGTestVideo("vqeg-football", "src19_ref__525.yuv"),
        VQEGTestVideo("vqeg-sailboat", "src20_ref__525.yuv"),
        VQEGTestVideo("vqeg-susie", "src21_ref__525.yuv"),
        VQEGTestVideo("vqeg-tempete", "src22_ref__525.yuv"),

        LDVTestVideo("ldv-mobcal", "576i25_mobcal_ter.yuv"),
        LDVTestVideo("ldv-parkrun", "576i25_parkrun_ter.yuv"),
        LDVTestVideo("ldv-shields", "576i25_shields_ter.yuv"),
        LDVTestVideo("ldv-stockholm", "576i25_stockholm_ter.yuv"),
        ]:
        testcases[testcase.name] = testcase

    return testcases

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    get_testcases()
