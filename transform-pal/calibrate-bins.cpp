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

// For each bin, the best threshold value found so far
using BestThresholds = std::array<float, NUM_BINS>;

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
        : threshold(_threshold), correct(0.0), incorrect(0.0)
    {
    }

    // Threshold to test
    float threshold;

    // Correct energy for this bin (chroma treated as chroma, luma as luma)
    double correct;
    // Incorrect energy for this bin (chroma treated as luma, luma as chroma)
    double incorrect;
};

void runTrials(int iteration, std::ifstream &lumaFile, std::ifstream &chromaFile, BestThresholds &bestThresholds)
{
    printf("--- Iteration %d ---\n\n", iteration);

    // We extract another digit's worth of precision on each iteration
    const float stepSize = std::pow(10, -(iteration + 1));

    // Generate the set of threshold values to try for each bin
    std::array<std::vector<Trial>, NUM_BINS> trials;
    for (int bin = 0; bin < NUM_BINS; bin++) {
        for (int i = -9; i <= 9; i++) {
            const float threshold = bestThresholds[bin] + (i * stepSize);
            if (threshold >= 0.0 && threshold <= 1.0) trials[bin].emplace_back(threshold);
        }
    }

    // Rewind the input files
    lumaFile.clear();
    lumaFile.seekg(0, std::ios::beg);
    chromaFile.clear();
    chromaFile.seekg(0, std::ios::beg);

    BinBuffer lumaBuf, chromaBuf;
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

            // The real code uses squared values
            const float compValSq = compVal * compVal;
            const float compRefSq = compRef * compRef;

            // Simulate the threshold algorithm for each trial threshold value
            for (Trial &trial: trials[bin]) {
                const float thresholdSq = trial.threshold * trial.threshold;
                if (compValSq < (compRefSq * thresholdSq) || compRefSq < (compValSq * thresholdSq)) {
                    // Treat this bin's contents as luma
                    trial.correct += static_cast<double>(lumaVal + lumaRef);
                    trial.incorrect += static_cast<double>(chromaVal + chromaRef);
                } else {
                    // Treat this bin's contents as chroma
                    trial.correct += static_cast<double>(chromaVal + chromaRef);
                    trial.incorrect += static_cast<double>(lumaVal + lumaRef);
                }
            }
        }
    }

    constexpr int BAR_WIDTH = 40;
    char bar[BAR_WIDTH + 1];

    // Summarise the results of the trials
    for (int bin = 0; bin < NUM_BINS; bin++) {
        printf("Bin %d:\n", bin);
        printf("%8s %8s %15s %15s %5s\n", "Thr", "dB", "Correct", "Incorrect", "Corr%");

        double bestPercent = -1.0;
        for (const Trial &trial: trials[bin]) {
            double percent = (100 * trial.correct) / (trial.correct + trial.incorrect);

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

            printf("%8.4f %8.4f %15.0f %15.0f %5.1f %s\n",
                   trial.threshold, toDB(trial.threshold),
                   trial.correct, trial.incorrect, percent, bar);

            // Is this better than one we've seen already?
            // (Preferring lower threshold values where otherwise equal.)
            if (percent > bestPercent) {
                bestThresholds[bin] = trial.threshold;
                bestPercent = percent;
            }
        }
        printf("\n");
    }

    printf("Best thresholds found (dB):\n");
    for (int bin = 0, y = 0; y < BINS_Y; y++) {
        for (int x = 0; x < BINS_X; x++, bin++) {
            printf("[%3d] = %8.4f, ", bin, toDB(bestThresholds[bin]));
        }
        printf("\n");
    }
    printf("\n");

    printf("In threshold file form:\n");
    for (int bin = 0, y = 0; y < BINS_Y; y++) {
        for (int x = 0; x < BINS_X; x++, bin++) {
            printf("%.4f ", bestThresholds[bin]);
        }
        printf("\n");
    }
    printf("\n");

    fflush(stdout);
}

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

    BestThresholds bestThresholds;
    std::fill(bestThresholds.begin(), bestThresholds.end(), 0.0);

    for (int i = 0; i < 4; i++) {
        runTrials(i, lumaFile, chromaFile, bestThresholds);
    }

    return 0;
}
