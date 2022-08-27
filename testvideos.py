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

# System parameters for interpolating into commands.
PARAMS = {
    "NTSC": {
        # XXX This is wrong in ld-chroma-encoder
        "size": "758x486", # should be "760x488",
        "active": "758x486", # should "758x488",
        "rate": "30000/1001",
    },
    "PAL": {
        "size": "928x576",
        "active": "922x576",
        "rate": "25",
    },
}
for params in PARAMS.values():
    params["pad"] = params["size"].replace("x", ":")
    params["scale"] = params["active"].replace("x", ":")

# Common args for ffmpeg.
FFMPEG = [
    "ffmpeg",
    "-loglevel", "error",
    "-sws_flags", "lanczos",
    ]

class TestVideo:
    """A video testcase."""

    def __init__(self, name, system):
        self.name = name
        self.system = system

    def check(self):
        os.makedirs(video_dir, exist_ok=True)

        self.rgbname = os.path.join(video_dir, self.name + ".rgb")
        if not os.path.exists(self.rgbname):
            logging.info("Generating %s", self.rgbname)
            self.generate()

        self.tbcname = os.path.join(video_dir, self.name + ".tbc")
        if not os.path.exists(self.tbcname):
            logging.info("Encoding %s", self.tbcname)
            self.encode()

        # This doesn't follow the vhs-decode convention, because
        # it's for cases where we want to decode the two files
        # individually.
        self.lumatbcname = os.path.join(video_dir, self.name + ".luma.tbc")
        self.chromatbcname = os.path.join(video_dir, self.name + ".chroma.tbc")
        if not (os.path.exists(self.lumatbcname) and os.path.exists(self.chromatbcname)):
            logging.info("Split-encoding %s", self.tbcname)
            self.split_encode()

    def generate(self):
        """Generate the .rgb through whatever mechanism.
        Subclasses should override this."""

        raise NotImplementedError("generate")

    def encode(self):
        """Encode the .rgb into a .tbc."""

        subprocess.check_call([
            os.path.join(lddecode_dir, "tools", "ld-chroma-decoder", "encoder", "ld-chroma-encoder"),
            "--system", self.system,
            self.rgbname, self.tbcname,
            ])

    def split_encode(self):
        """Encode the .rgb into luma and chroma .tbcs."""

        subprocess.check_call([
            os.path.join(lddecode_dir, "tools", "ld-chroma-decoder", "encoder", "ld-chroma-encoder"),
            "--system", self.system,
            self.rgbname, self.lumatbcname, self.chromatbcname,
            ])
        # Symlink the .json for ease of separate decoding.
        subprocess.check_call([
            "ln", "-sf",
            self.lumatbcname + ".json",
            self.chromatbcname + ".json",
            ])

class LAVTestVideo(TestVideo):
    """A video testcase generated from a libavfilter test source."""

    def __init__(self, name, source, system):
        self.source = source
        if "=" in source:
            self.source += ":"
        else:
            self.source += "="
        params = PARAMS[system]
        self.source += "duration=1:size=%s:rate=%s" \
                       % (params["size"], params["rate"])
        super(LAVTestVideo, self).__init__(name, system)

    def generate(self):
        params = PARAMS[self.system]
        subprocess.check_call(FFMPEG + [
            "-f", "lavfi", "-i", self.source,
            "-filter:v", "pad=%s:-1:-1" % params["pad"],
            "-f", "rawvideo", "-pix_fmt", "rgb48",
            "-s", params["size"], "-y", self.rgbname,
            ])

class VQEGTestVideo(TestVideo):
    """A video testcase generated from one of the VQEG test sequences.
    These can be downloaded from <https://media.xiph.org/vqeg/TestSequences/>."""

    # XXX could download into the cache dir automatically
    vqeg_dir = "/n/stuff/tv/Test/vqeg"

    def __init__(self, name, yuvname):
        self.yuvname = os.path.join(self.vqeg_dir, yuvname)
        system = "PAL" if self.yuvname.endswith("__625.yuv") else "NTSC"
        super(VQEGTestVideo, self).__init__(name, system)

    def generate(self):
        if self.yuvname.endswith("__625.yuv"):
            insize = "720x576"
        else:
            insize = "720x486"

        params = PARAMS[self.system]
        filters = "scale=%s,pad=%s:-1:-1" % (params["scale"], params["pad"])
        subprocess.check_call(FFMPEG + [
            "-f", "rawvideo", "-pix_fmt", "uyvy422",
            "-s", insize, "-r", params["rate"],
            "-i", self.yuvname,
            "-filter:v", filters,
            "-f", "rawvideo", "-pix_fmt", "rgb48",
            "-s", params["size"], "-y", self.rgbname,
            ])

class LDVTestVideo(TestVideo):
    """A video testcase generated from one of the LDV test sequences produced by SVT.
    These can be downloaded from <https://media.xiph.org/ldv/pub/test_sequences/601/>."""

    # XXX could download into the cache dir automatically
    ldv_dir = "/n/stuff/tv/Test/ldv"

    def __init__(self, name, yuvname):
        self.yuvname = os.path.join(self.ldv_dir, yuvname)
        super(LDVTestVideo, self).__init__(name, "PAL")

    def generate(self):
        params = PARAMS[self.system]
        filters = "scale=%s,pad=%s:-1:-1" % (params["scale"], params["pad"])
        subprocess.check_call(FFMPEG + [
            "-f", "rawvideo", "-pix_fmt", "yuv420p",
            "-s", "720x576", "-r", params["rate"],
            "-i", self.yuvname,
            "-filter:v", filters,
            "-f", "rawvideo", "-pix_fmt", "rgb48",
            "-s", params["size"], "-y", self.rgbname,
            ])

class SVTTestVideo(TestVideo):
    """A video testcase generated from one of the 2160p MultiFormat test sequences produced by SVT.
    These can be downloaded from <https://media.xiph.org/video/derf/y4m/>."""

    # XXX these are all 16:9 aspect ratio
    # XXX could download into the cache dir automatically
    ldv_dir = "/n/stuff/tv/Test/svt"

    def __init__(self, name, yuvname):
        self.yuvname = os.path.join(self.ldv_dir, yuvname)
        super(SVTTestVideo, self).__init__(name, "PAL")

    def generate(self):
        params = PARAMS[self.system]
        filters = "scale=%s,pad=%s:-1:-1" % (params["scale"], params["pad"])
        subprocess.check_call(FFMPEG + [
            "-f", "yuv4mpegpipe", "-r", params["rate"],
            "-i", self.yuvname,
            "-filter:v", filters,
            "-f", "rawvideo", "-pix_fmt", "rgb48",
            "-s", params["size"], "-y", self.rgbname,
            ])

class BBCTestVideo(TestVideo):
    """A video testcase generated from a BBC 576i component test video.
    These are not publically available (as far as I know)."""

    sn_dir = "/n/stuff2/capture/laserdisc/BBC/StephenNeal-captures"

    def __init__(self, name, movname):
        self.movname = os.path.join(self.sn_dir, movname)
        super(BBCTestVideo, self).__init__(name, "PAL")

    def generate(self):
        params = PARAMS[self.system]
        filters = "scale=%s,pad=%s:-1:-1" % (params["scale"], params["pad"])
        subprocess.check_call(FFMPEG + [
            "-i", self.movname,
            "-filter:v", filters,
            "-f", "rawvideo", "-pix_fmt", "rgb48",
            "-s", params["size"], "-y", self.rgbname,
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
    params = PARAMS[testcase.system]

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
    ffmpeg_command = FFMPEG + [
        "-f", "rawvideo", "-pix_fmt", "rgb48",
        "-s", params["size"], "-i", "-",
        "-f", "rawvideo", "-pix_fmt", "rgb48",
        "-s", params["size"], "-i", testcase.rgbname,
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
        LAVTestVideo("lavfi-magenta-625", "color=c=0xBF00BF", "PAL"),
        LAVTestVideo("lavfi-magenta-525", "color=c=0xBF00BF", "NTSC"),
        LAVTestVideo("lavfi-testsrc-625", "testsrc", "PAL"),
        LAVTestVideo("lavfi-testsrc-525", "testsrc", "NTSC"),
        LAVTestVideo("lavfi-pal75bars", "pal75bars", "PAL"),
        LAVTestVideo("lavfi-smptebars", "smptebars", "NTSC"),

        # Names for these come from frtv_phase1_final_report.doc
        VQEGTestVideo("vqeg-tree-625", "src1_ref__625.yuv"),
        VQEGTestVideo("vqeg-barcelona-625", "src2_ref__625.yuv"),
        VQEGTestVideo("vqeg-harp-625", "src3_ref__625.yuv"),
        VQEGTestVideo("vqeg-movinggraphic-625", "src4_ref__625.yuv"),
        VQEGTestVideo("vqeg-canoavalsesia-625", "src5_ref__625.yuv"),
        VQEGTestVideo("vqeg-f1car-625", "src6_ref__625.yuv"),
        VQEGTestVideo("vqeg-fries-625", "src7_ref__625.yuv"),
        VQEGTestVideo("vqeg-horizontalscrolling-625", "src8_ref__625.yuv"),
        VQEGTestVideo("vqeg-rugby-625", "src9_ref__625.yuv"),
        VQEGTestVideo("vqeg-mobilecalendar-625", "src10_ref__625.yuv"),

        VQEGTestVideo("vqeg-balloonpops-525", "src13_ref__525.yuv"),
        VQEGTestVideo("vqeg-newyork-525", "src14_ref__525.yuv"),
        VQEGTestVideo("vqeg-mobilecalendar-525", "src15_ref__525.yuv"),
        VQEGTestVideo("vqeg-betespasbetes-525", "src16_ref__525.yuv"),
        VQEGTestVideo("vqeg-lepoint-525", "src17_ref__525.yuv"),
        VQEGTestVideo("vqeg-autumnleaves-525", "src18_ref__525.yuv"),
        VQEGTestVideo("vqeg-football-525", "src19_ref__525.yuv"),
        VQEGTestVideo("vqeg-sailboat-525", "src20_ref__525.yuv"),
        VQEGTestVideo("vqeg-susie-525", "src21_ref__525.yuv"),
        VQEGTestVideo("vqeg-tempete-525", "src22_ref__525.yuv"),

        LDVTestVideo("ldv-mobcal", "576i25_mobcal_ter.yuv"),
        LDVTestVideo("ldv-parkrun", "576i25_parkrun_ter.yuv"),
        LDVTestVideo("ldv-shields", "576i25_shields_ter.yuv"),
        LDVTestVideo("ldv-stockholm", "576i25_stockholm_ter.yuv"),

        SVTTestVideo("svt-crowdrun", "crowd_run_2160p50.y4m"),
        SVTTestVideo("svt-duckstakeoff", "ducks_take_off_2160p50.y4m"),
        SVTTestVideo("svt-intotree", "in_to_tree_2160p50.y4m"),
        SVTTestVideo("svt-oldtowncross", "old_town_cross_2160p50.y4m"),
        SVTTestVideo("svt-parkjoy", "park_joy_2160p50.y4m"),

        BBCTestVideo("bbc-carousel", "carousel_component.short.mov"),
        BBCTestVideo("bbc-dick", "dick_component.short.mov"),
        BBCTestVideo("bbc-swingingbars", "hv_swinging_bars_component.short.mov"),
        BBCTestVideo("bbc-mobcal", "mobcal_component.short.mov"),
        BBCTestVideo("bbc-newpat", "newpat_component.short.mov"),
        BBCTestVideo("bbc-wheel", "wheel_component.short.mov"),
        BBCTestVideo("bbc-xccouple", "xc_couple_component.short.mov"),
        ]:
        testcases[testcase.name] = testcase

    return testcases

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Generate all the files for the testcases
    testcases = get_testcases()
    for name, testcase in sorted(testcases.items()):
        testcase.check()
