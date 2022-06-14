// Use a composite video signal as a test signal for a Domesday Duplicator,
// by detecting sync pulses and checking they're coming at the right rate.
// (Because if you're using a DDD, it's probably connected to something which
// has a video output too...)

#include <algorithm>
#include <iostream>
#include <cstdint>
#include <cstdlib>

// The DDD's input is AC-coupled with a fairly small capacitor, so the black
// level drifts quickly. However, we know there there should be at least one
// sync pulse every line -- so the minimum value we see during the period of a
// line will be more or less the sync tip.

constexpr double SAMPLE_RATE = 40000000;
constexpr double LINE_FREQ = 15625; // PAL

constexpr int LINE_SAMPLES = static_cast<int>(SAMPLE_RATE / LINE_FREQ);
constexpr int HALF_LINE_SAMPLES = LINE_SAMPLES / 2;

constexpr int FIELD_1_SAMPLES = 313 * LINE_SAMPLES;
constexpr int FIELD_2_SAMPLES = 312 * LINE_SAMPLES;

constexpr int NUM_CHUNKS = 16;
constexpr int CHUNK_SIZE = static_cast<int>(1.2 * (SAMPLE_RATE / LINE_FREQ)) / NUM_CHUNKS;
constexpr int BUF_SIZE = NUM_CHUNKS * CHUNK_SIZE;

enum GapType {
    INITIAL,
    SHORT,
    LONG,
    UNKNOWN
};

int main(int argc, char *argv[]) {
    // Ring buffer of samples
    int16_t buf[BUF_SIZE];

    uint64_t file_offset = 0;
    int cur_chunk = 0;
    bool ring_full = false;

    int16_t min_value = 0;
    uint64_t last_down = 0;

    bool up = false;

    GapType last_gap = INITIAL;

    uint64_t last_field = 0;
    bool seen_field = false;
    int last_field_num = 0;

    while (true) {
        const int buf_offset = CHUNK_SIZE * cur_chunk;

        if (ring_full) {
            // Discard the oldest chunk. Was the maximum value in it?
            for (int i = 0; i < CHUNK_SIZE; i++) {
                const int16_t value = buf[buf_offset + i] >> 6;
                if (value == min_value) {
                    // This was (or was equal to) the previous minimum value.
                    // Scan the other chunks to find the new minimum value.
                    min_value = 0;
                    for (int j = (buf_offset + CHUNK_SIZE) % BUF_SIZE; j != buf_offset; j = (j + 1) % BUF_SIZE) {
                        const int16_t value = buf[j] >> 6;
                        if (value < min_value) min_value = value;
                    }
//                    std::cout << "rescan for min = " << min_value << "\n";
                    break;
                }
            }
        }

        // Read the next chunk into the ring buffer
        std::cin.read(reinterpret_cast<char *>(&buf[buf_offset]), CHUNK_SIZE * sizeof(int16_t));
        if (std::cin.eof()) break;

        // Update the ring pointer and check if we've filled the whole ring
        cur_chunk = (cur_chunk + 1) % NUM_CHUNKS;
        if (cur_chunk == 0) ring_full = true;

//        std::cout << "read chunk " << cur_chunk << "/" << NUM_CHUNKS << ", min = " << min_value << "\n";

        // Process samples in the new chunk
        for (int i = 0; i < CHUNK_SIZE; i++) {
            const int16_t value = buf[buf_offset + i] >> 6;
//            std::cout << value << " ";

            if (value < min_value) min_value = value;

            // Detect sync edges, with some hysteresis
            const int16_t up_limit = min_value + 100; // XXX magic numbers
            const int16_t down_limit = min_value + 50;
            if (up && value > up_limit) {
                up = false;
//                std::cout << "up edge at " << file_offset + i << "\n";
            } else if (!up && value < down_limit) {
                up = true;

                const uint64_t pos = file_offset + i;
                const uint64_t len = pos - last_down;
                last_down = pos;
//                std::cout << "down edge at " << pos << " len " << len << "\n";

                GapType gap;
                if (abs(len - LINE_SAMPLES) < 5) {
                    gap = LONG;
                } else if (abs(len - HALF_LINE_SAMPLES) < 5) {
                    gap = SHORT;
                } else {
                    gap = UNKNOWN;
                }

                if (gap == UNKNOWN && last_gap != SHORT) {
                    // We can't really tell during the equalisation pulses as
                    // the baseline drifts too high, but if it wasn't preceded
                    // by a short gap...
                    std::cout << "unexpected down-edge spacing " << len << " at " << pos << "\n";
                }
                if (gap == SHORT && last_gap == LONG) {
                    // First short gap in a field.
                    const uint64_t field_len = pos - last_field;
                    last_field = pos;

                    // Check we have the right alternating sequence of field lengths.
                    if (!seen_field) {
                        // Start of the file -- no complete field yet
                        seen_field = true;
                        last_field_num = 0;
                    } else if (abs(field_len - FIELD_1_SAMPLES) < 500) {
                        if (last_field_num == 1) {
                            std::cout << "duplicate field 1 at " << pos << "\n";
                        }
                        last_field_num = 1;
                    } else if (abs(field_len - FIELD_2_SAMPLES) < 500) {
                        if (last_field_num == 2) {
                            std::cout << "duplicate field 2 at " << pos << "\n";
                        }
                        last_field_num = 2;
                    } else {
                        std::cout << "unexpected field len " << field_len << " (expected " << FIELD_1_SAMPLES << " or " << FIELD_2_SAMPLES << ") at " << pos << "\n";
                        last_field_num = 0;
                    }
                }

                last_gap = gap;
            }
        }
//        std::cout << "\n";

        file_offset += CHUNK_SIZE;
    }
}
