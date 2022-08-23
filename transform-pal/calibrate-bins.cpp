// Determine an optimal value for each bin's threshold, by analysing statistics
// produced by ld-chroma-decoder when decoding just the luma and just the
// chroma from a video.

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <numeric>
#include <vector>

// TransformPal2D
constexpr int BINS_X = 5;
constexpr int BINS_Y = 16;
constexpr int NUM_BINS = BINS_X * BINS_Y;

static inline float toDB(float ratio) {
    return std::abs(20.0f * std::log10(ratio));
}

// For each bin, the squares of the input and reflected values are recorded
using BinBuffer = std::array<float, NUM_BINS * 2>;

// Read stats from one filter operation into buffer.
// The values returned are always greater than zero.
// Return true on success, false on EOF.
bool readValues(std::ifstream &file, BinBuffer &buffer)
{
    file.read(reinterpret_cast<char *>(buffer.data()), buffer.size() * sizeof(*buffer.data()));
    if (file.eof()) return false;

    for (float &f: buffer) {
        // Get the magnitude of this bin
        f = std::sqrt(f);

        // Avoid division by zero later, by clamping to a small value
        if (f < 1e-9f) f = 1e-9f;
    }

    return true;
}

struct Trial
{
    Trial(float _threshold)
        : threshold(_threshold)
    {
        std::fill(correct.begin(), correct.end(), 0.0);
        std::fill(incorrect.begin(), incorrect.end(), 0.0);
    }

    // Threshold to test
    float threshold;

    // Correct energy for each bin (chroma treated as chroma, luma as luma)
    std::array<double, NUM_BINS> correct;
    // Incorrect energy for each bin (chroma treated as luma, luma as chroma)
    std::array<double, NUM_BINS> incorrect;
};

int main(int argc, char *argv[])
{
    if (argc < 3) {
        fprintf(stderr, "Usage: calibrate-bins BINSTATS-LUMA BINSTATS-CHROMA\n");
        return 1;
    }

    std::ifstream lumaFile(argv[1]);
    if (!lumaFile) {
        fprintf(stderr, "Cannot open %s\n", argv[1]);
        return 1;
    }
    std::ifstream chromaFile(argv[2]);
    if (!chromaFile) {
        fprintf(stderr, "Cannot open %s\n", argv[2]);
        return 1;
    }
    printf("Analysing %s and %s...\n\n", argv[1], argv[2]); 

    BinBuffer lumaBuf, chromaBuf;

    // Generate the set of threshold values to try
    std::vector<Trial> trials;
    for (float f = 0.0; f < 12.0; f += 0.25) {
        trials.emplace_back(f);        
    }

    while (true) {
        // Read corresponding stats from the two input files
        if (!readValues(lumaFile, lumaBuf)) break;
        if (!readValues(chromaFile, chromaBuf)) break;

        for (int bin = 0; bin < NUM_BINS; bin++) {
            // Get the contents of both bins from both files
            const float lumaVal = lumaBuf[bin * 2];
            const float lumaRef = lumaBuf[(bin * 2) + 1];
            const float chromaVal = chromaBuf[bin * 2];
            const float chromaRef = chromaBuf[(bin * 2) + 1];

            // Sum the luma/chroma values, giving the composite values for the two bins
            const float compVal = lumaVal + chromaRef;
            const float compRef = lumaRef + chromaRef;

            // Compute imbalance in dB, as seen by the composite decoder
            const float db = toDB(compVal / compRef);

            // Simulate the threshold algorithm for each trial value
            for (Trial &trial: trials) {
                // <= rather than < to simulate the symmetric bins correctly
                if (db <= trial.threshold) {
                    // Treat this bin's contents as chroma
                    trial.correct[bin] += static_cast<double>(chromaVal + chromaRef);
                    trial.incorrect[bin] += static_cast<double>(lumaVal + lumaRef);
                } else {
                    // Treat this bin's contents as luma
                    trial.correct[bin] += static_cast<double>(lumaVal + lumaRef);
                    trial.incorrect[bin] += static_cast<double>(chromaVal + chromaRef);
                }
            }
        }
    }

    std::array<float, NUM_BINS> bestThresholds;

    constexpr int BAR_WIDTH = 40;
    char bar[BAR_WIDTH + 1];

    // Summarise the results of the trials
    for (int bin = 0; bin < NUM_BINS; bin++) {
        printf("Bin %d:\n", bin);
        printf("%5s %15s %15s %5s\n", "Thr", "Correct", "Incorrect", "Corr%");

        double bestPercent = -1.0;
        for (const Trial &trial: trials) {
            double correct = trial.correct[bin];
            double incorrect = trial.incorrect[bin];
            double percent = (100 * correct) / (correct + incorrect);

            // Show the percentage as a bar
            int scaled = static_cast<int>((percent * BAR_WIDTH) / 100);
            int j = 0;
            while (j < scaled) {
                bar[j++] = '-';
            }
            while (j < BAR_WIDTH) {
                bar[j++] = ' ';
            }
            bar[j] = '\0';

            printf("%5.2f %15.0f %15.0f %5.1f %s\n", trial.threshold, correct, incorrect, percent, bar);

            // Is this better than one we've seen already?
            // (Preferring lower threshold values where otherwise equal.)
            if (percent > bestPercent) {
                bestThresholds[bin] = trial.threshold;
                bestPercent = percent;
            }
        }
        printf("\n");
    }

    printf("Best thresholds found:\n");
    for (int bin = 0, y = 0; y < BINS_Y; y++) {
        for (int x = 0; x < BINS_X; x++, bin++) {
            printf("[%3d] = %5.2f, ", bin, bestThresholds[bin]);
        }
        printf("\n");
    }
    printf("\n");

    printf("In threshold file form:\n");
    for (int bin = 0, y = 0; y < BINS_Y; y++) {
        for (int x = 0; x < BINS_X; x++, bin++) {
            printf("%.3f ", 1.0 - std::pow(10.0f, bestThresholds[bin] / -20.0f));
        }
        printf("\n");
    }
    printf("\n");

    return 0;
}
