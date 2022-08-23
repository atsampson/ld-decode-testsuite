// Read statistics produced by ld-chroma-decoder with the binstats patch,
// and show some general stats plus a histogram for each bin.

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <numeric>

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

// Histogram bin sizes for imbalance levels
constexpr int NUM_LEVELS = 20;
constexpr int DB_PER_LEVEL = 1;

class Histogram
{
public:
    Histogram()
    {
        std::fill(levels.begin(), levels.end(), 0);
    }

    void add(float value)
    {
        int intValue = std::clamp(static_cast<int>(value) / DB_PER_LEVEL, 0, NUM_LEVELS - 1);
        levels[intValue]++;
    }

    uint64_t max()
    {
        return *std::max_element(levels.begin(), levels.end());
    }

    void show(uint64_t max)
    {
        uint64_t sum = std::accumulate(levels.begin(), levels.end(), 0);
        if (sum == 0) sum = 1;

        constexpr int BAR_WIDTH = 40;
        char bar[BAR_WIDTH + 1];

        for (int i = NUM_LEVELS - 1; i >= 0; i--) {
            // Draw the histogram bar
            int scaled = static_cast<int>((levels[i] * BAR_WIDTH) / max);
            int j = 0;
            while (j < scaled) {
                bar[j++] = '-';
            }
            while (j < BAR_WIDTH) {
                bar[j++] = ' ';
            }
            bar[j] = '\0';

            int percent = static_cast<int>((levels[i] * 100) / sum);
            printf("%3d dB : %s %3d%%\n", i * DB_PER_LEVEL, bar, percent);
        }
    }

private:
    std::array<uint64_t, NUM_LEVELS> levels;
};

static inline float toDB(float ratio) {
    return std::abs(20.0f * std::log10(ratio));
}

int main(int argc, char *argv[])
{
    if (argc < 2) {
        fprintf(stderr, "Usage: report-bins BINSTATS\n");
        return 1;
    }

    std::ifstream inputFile(argv[1]);
    if (!inputFile) {
        fprintf(stderr, "Cannot open %s\n", argv[1]);
        return 1;
    }
    printf("Analysing %s...\n\n", argv[1]); 

    // For each bin, the squares of the input and reflected values are recorded
    std::array<float, NUM_BINS * 2> binBuffer;

    // Mean amplitude per bin
    std::array<float, NUM_BINS> amps;
    std::fill(amps.begin(), amps.end(), 0.0f);

    // Histogram of dB imbalance per bin
    std::array<Histogram, NUM_BINS> histograms;

    int64_t numSamples = 0;
    while (true) {
        inputFile.read(reinterpret_cast<char *>(binBuffer.data()), binBuffer.size() * sizeof(*binBuffer.data()));
        if (inputFile.eof()) break;

        for (float &f: binBuffer) {
            f = std::sqrt(f);

            // Avoid zero values by clamping them to a very small value
            if (f < 1e-9f) f = 1e-9f;
        }

        // Accumulate mean amplitude
        for (int i = 0; i < NUM_BINS; i++) {
            amps[i] += binBuffer[i * 2] + binBuffer[(i * 2) + 1];
        }

        for (int i = 0; i < NUM_BINS; i++) {
            // Skip the symmetric bins (where the pairs are always equal)
            if (i == 24 || i == 64) continue;

            // Compute bin imbalance in dB
            const float db = toDB(binBuffer[i * 2] / binBuffer[(i * 2) + 1]);

            histograms[i].add(db);
        }

        numSamples++;
    }

    // Compute mean amplitude
    for (float &f: amps) {
        f /= numSamples * 2;
    }

    for (float f = 0.1; f < 1.05; f += 0.1) {
        printf("Threshold %3.1f = %5.1f dB\n", f, toDB(f));
    }
    printf("\n");

    printf("Mean amplitude per bin:\n");
    int bin = 0;
    for (int z = 0; z < BINS_Z; z++) {
        for (int y = 0; y < BINS_Y; y++) {
            for (int x = 0; x < BINS_X; x++) {
                printf(" %3d:%9.1f", bin, amps[bin]);
                bin++;
            }
            printf("\n");
        }
        printf("\n");
    }

    std::array<uint64_t, NUM_BINS> binMaxCounts;
    for (int i = 0; i < NUM_BINS; i++) {
        binMaxCounts[i] = histograms[i].max();
    }
    uint64_t maxCount = *std::max_element(binMaxCounts.begin(), binMaxCounts.end());

    bin = 0;
    for (int z = 0; z < BINS_Z; z++) {
        for (int y = 0; y < BINS_Y; y++) {
            for (int x = 0; x < BINS_X; x++) {
                printf("Bin %d (%d, %d):\n", bin, x, y);
                histograms[bin].show(maxCount);
                printf("\n");
                bin++;
            }
        }
        printf("\n");
    }

    return 0;
}
