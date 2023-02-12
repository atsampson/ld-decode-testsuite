// Determine an optimal value for each bin's threshold, by analysing statistics
// produced by ld-chroma-decoder when decoding just the luma and just the
// chroma from a video.
// XXX This doesn't really work, unfortunately -- it produces thresholds that
// tend to be at one end or the other of the scale. The algorithm works but the
// "fitness function" isn't right...

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <limits>
#include <numeric>
#include <vector>

#if 1
// TransformPal3D
constexpr int BINS_X = 3;
constexpr int BINS_Y = 32;
constexpr int BINS_Z = 8;
constexpr int NUM_BINS = BINS_X * BINS_Y * BINS_Z;
#else
// TransformPal2D
constexpr int BINS_X = 5;
constexpr int BINS_Y = 16;
constexpr int BINS_Z = 1;
constexpr int NUM_BINS = BINS_X * BINS_Y * BINS_Z;
#endif

static inline float toDB(float ratio) {
    return std::abs(20.0f * std::log10(ratio));
}

// For each bin, the squares of the input and reflected values are recorded
using BinBuffer = std::array<float, NUM_BINS * 2>;

// For each bin, the best threshold value found so far
using BestThresholds = std::array<float, NUM_BINS>;

// Read stats from one filter operation into buffer.
// The values returned are the squares of the magnitudes (and may be zero).
// Return true on success, false on EOF.
bool readValues(std::ifstream &file, BinBuffer &buffer)
{
    file.read(reinterpret_cast<char *>(buffer.data()), buffer.size() * sizeof(*buffer.data()));
    if (file.eof()) return false;

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

void runTrials(int iteration, std::ifstream &compFile, std::ifstream &lumaFile, std::ifstream &chromaFile,
               BestThresholds &bestThresholds)
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
    compFile.clear();
    compFile.seekg(0, std::ios::beg);
    lumaFile.clear();
    lumaFile.seekg(0, std::ios::beg);
    chromaFile.clear();
    chromaFile.seekg(0, std::ios::beg);

    BinBuffer compBuf, lumaBuf, chromaBuf;
    while (true) {
        // Read corresponding stats from the input files
        if (!readValues(compFile, compBuf)) break;
        if (!readValues(lumaFile, lumaBuf)) break;
        if (!readValues(chromaFile, chromaBuf)) break;

        for (int bin = 0; bin < NUM_BINS; bin++) {
            // Get the squared magnitudes of both bins from the composite file
            const float compValSq = compBuf[bin * 2];
            const float compRefSq = compBuf[(bin * 2) + 1];

            // Get the magnitudes of both bins from the luma/chroma files
            const float lumaVal = std::sqrt(lumaBuf[bin * 2]);
            const float lumaRef = std::sqrt(lumaBuf[(bin * 2) + 1]);
            const float chromaVal = std::sqrt(chromaBuf[bin * 2]);
            const float chromaRef = std::sqrt(chromaBuf[(bin * 2) + 1]);

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

        double bestIncorrect = std::numeric_limits<double>::max();
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
            if (trial.incorrect < bestIncorrect) {
                bestThresholds[bin] = trial.threshold;
                bestIncorrect = trial.incorrect;
            }
        }
        printf("\n");
    }

    printf("Best thresholds found (dB):\n");
    for (int bin = 0, z = 0; z < BINS_Z; z++) {
        for (int y = 0; y < BINS_Y; y++) {
            for (int x = 0; x < BINS_X; x++, bin++) {
                printf("[%3d] = %8.4f, ", bin, toDB(bestThresholds[bin]));
            }
            printf("\n");
        }
        printf("\n");
    }

    printf("In threshold file form:\n");
    for (int bin = 0, z = 0; z < BINS_Z; z++) {
        for (int y = 0; y < BINS_Y; y++) {
            for (int x = 0; x < BINS_X; x++, bin++) {
                printf("%.4f ", bestThresholds[bin]);
            }
            printf("\n");
        }
        printf("\n");
    }

    fflush(stdout);
}

int main(int argc, char *argv[])
{
    if (argc < 4) {
        fprintf(stderr, "Usage: calibrate-bins BINSTATS-COMPOSITE BINSTATS-LUMA BINSTATS-CHROMA\n");
        return 1;
    }

    std::ifstream compFile(argv[1]);
    if (!compFile) {
        fprintf(stderr, "Cannot open %s\n", argv[1]);
        return 1;
    }
    std::ifstream lumaFile(argv[2]);
    if (!lumaFile) {
        fprintf(stderr, "Cannot open %s\n", argv[2]);
        return 1;
    }
    std::ifstream chromaFile(argv[3]);
    if (!chromaFile) {
        fprintf(stderr, "Cannot open %s\n", argv[3]);
        return 1;
    }
    printf("Analysing %s, %s and %s...\n\n", argv[1], argv[2], argv[3]);

    BestThresholds bestThresholds;
    std::fill(bestThresholds.begin(), bestThresholds.end(), 0.0);

    for (int i = 0; i < 4; i++) {
        runTrials(i, compFile, lumaFile, chromaFile, bestThresholds);
    }

    return 0;
}
