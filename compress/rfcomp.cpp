// Experiments in compressing DDD RF samples.

#include <cmath>
#include <cstdio>
#include <cstdint>
#include <unistd.h>

static constexpr int SHIFT_BITS = 6;
static constexpr int CHUNK_SIZE = 32;

static constexpr float SAMPLE_RATE = 40.0e6;

int do_decode(FILE *fin, FILE *fout) {
    return 0;
}

int do_encode(FILE *fin, FILE *fout) {
    float total_in_bits = 0.0, total_out_bits = 0.0;
    while (true) {
        int16_t values[CHUNK_SIZE];
        int count = fread(values, sizeof(int16_t), CHUNK_SIZE, fin);
        if (count == 0) {
            if (feof(fin)) {
                if (total_in_bits > 0) {
                    fprintf(stderr, "total in_bits=%f out_bits=%f ratio=%f\n", total_in_bits, total_out_bits, total_out_bits / total_in_bits);
                }
                break;
            } else { 
                fprintf(stderr, "Read error\n");
                return 1;
            }
        }

        for (int i = 0; i < count; i++) {
            if (values[i] & ((1 << SHIFT_BITS) - 1)) {
                fprintf(stderr, "Low bits not zero: %x\n", values[i]);
                return 1;
            }
            values[i] >>= SHIFT_BITS;
        }

        // Get the amplitude of the signal.
        float rms = 0.0;
        for (int i = 0; i < count; i++) {
            rms += values[i] * values[i];
        }
        rms = sqrtf(rms / count);
        int16_t model_amp = rms * M_SQRT2;
        fprintf(stderr, "model_amp=%6d\n", model_amp);

        // For a LaserDisc sample, the strongest component will be the video
        // signal, which is FM-encoded:
        // PAL: sync=6.76MHz, black=7.1MHz, white=7.9MHz
        // NTSC: sync=7.6MHz, black=8.1MHz, white=8.1MHz
        // We model this as a sine wave, with 256 choices of frequency and
        // phase (i.e. encode as 8 bits for each).
        static constexpr float MIN_FREQ = 6.7e6;
        static constexpr float MAX_FREQ = 8.15e6;
        static constexpr float FREQ_STEP = (MAX_FREQ - MIN_FREQ) / 256;

        static constexpr float MIN_PHASE = 0.0;
        static constexpr float MAX_PHASE = 2.0 * M_PI;
        static constexpr float PHASE_STEP = (MAX_PHASE - MIN_PHASE) / 256;

        // Search to find the best model values.
        // This is horribly inefficient! Could detect the frequency instead by
        // heterodyning it down and counting zero-crossings, then
        // product-detect the phase? (Maybe with a bit of optimisation after...)
        float best_f = -1.0, best_t = -1.0;
        int32_t best_max_diff = INT32_MAX;

        int16_t model[CHUNK_SIZE];
        for (float f = MIN_FREQ; f < MAX_FREQ; f += FREQ_STEP) {
            for (float t = MIN_PHASE; t < MAX_PHASE; t += PHASE_STEP) {
                //fprintf(stderr, "== f=%f t=%f\n", f, t);
                for (int i = 0; i < CHUNK_SIZE; i++) {
                    const float theta = ((M_PI * 2.0 * i * f) / SAMPLE_RATE) + t;
                    model[i] = sin(theta) * model_amp;
                    //fprintf(stderr, "%05d theta=%2.5f orig=%6d model=%6d\n", i, theta, values[i], model[i]);
                }

/*
                float rms_diff = 0.0;
                for (int i = 0; i < count; i++) {
                    const float diff = model[i] - values[i];
                    rms_diff += diff * diff;
                }
                rms_diff = sqrtf(rms_diff / count);
                fprintf(stderr, "f=%f t=%f rms_diff=%f\n", f, t, rms_diff);
*/

                int32_t max_diff = 0;
                for (int i = 0; i < count; i++) {
                    int32_t diff = int32_t(values[i]) - model[i];
                    if (diff < 0) diff = -diff;
                    if (diff > max_diff) max_diff = diff;
                }
                if (max_diff < best_max_diff) {
                    //fprintf(stderr, "f=%f t=%f max_diff=%d\n", f, t, max_diff);
                    best_f = f;
                    best_t = t;
                    best_max_diff = max_diff;
                }
            }
        }
        fprintf(stderr, "f=%f t=%f max_diff=%d\n", best_f, best_t, best_max_diff);

        int bits_per_sample = 0;
        while (best_max_diff >= (1 << bits_per_sample)) bits_per_sample++;
        // XXX Plus one more for the sign?

        const int in_bits = (16 - SHIFT_BITS) * count;
        // f, t, amp, bps, data
        const int out_bits = 8 + 8 + (16 - SHIFT_BITS) + 4 + (bits_per_sample * count);
        fprintf(stderr, "bps=%d in_bits=%d out_bits=%d ratio=%f\n", bits_per_sample, in_bits, out_bits, float(out_bits) / in_bits);
        total_in_bits += in_bits;
        total_out_bits += out_bits;
    }

    return 1;
}

int main(int argc, char *argv[]) {
    bool decode = false;
    while (true) {
        int c = getopt(argc, argv, "d");
        if (c == -1) break;

        switch (c) {
        case 'd':
            decode = true;
            break;
        default:
            fprintf(stderr, "Usage: rfcomp [-d]\n");
            return 1;
        }
    }

    if (decode) {
        return do_decode(stdin, stdout);
    } else {
        return do_encode(stdin, stdout);
    }
}
