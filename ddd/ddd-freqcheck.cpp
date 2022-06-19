// Use a composite video signal as a test signal for a Domesday Duplicator,
// by detecting sync pulses and checking they're coming at the right rate.
//
// The input from this should be the default PAL blue screen from the
// LD-V4300D that it produces when stopped without a disc, with the DDD gain
// switches set to minimum (1111).

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

constexpr int FIELD_1_SAMPLES = 313 * LINE_SAMPLES; // PAL
constexpr int FIELD_2_SAMPLES = 312 * LINE_SAMPLES; // PAL

constexpr int FILEBUF_SIZE = FIELD_1_SAMPLES + FIELD_2_SAMPLES;

// We want a bit more than a line's worth of history.
constexpr int RINGBUF_SIZE = (11 * LINE_SAMPLES) / 10;

enum GapType {
    INITIAL,
    SHORT,
    LONG,
    UNKNOWN
};

int main() {
    // Buffer for reading from file
    int16_t filebuf[FILEBUF_SIZE];
    uint64_t file_offset = 0;

    // Ring buffer for history of samples, so we can keep a running minimum
    int16_t ringbuf[RINGBUF_SIZE];
    int ring_pos = 0;
    bool ring_full = false;
    int16_t min_value = 0;

    bool up = false;
    uint64_t last_down = 0;
    GapType last_gap = INITIAL;

    uint64_t last_field = 0;
    bool seen_field = false;
    int last_field_num = 0;

    while (true) {
        // Read data into filebuf
        std::cin.read(reinterpret_cast<char *>(filebuf), sizeof filebuf);
        if (std::cin.eof()) break;
//        std::cout << "read chunk min_value " << min_value << "\n";

        // Process samples from filebuf
        for (int i = 0; i < FILEBUF_SIZE; i++) {
            const uint64_t pos = file_offset + i;
            const int16_t value = filebuf[i] >> 6;
//            std::cout << value << " ";

            if (ring_full) {
                // We are replacing the oldest sample in ringbuf;
                // was it the current minimum?
                if (ringbuf[ring_pos] == min_value) {
                    // Yes -- scan the buffer to find the new minimum.
                    // (This might look expensive, but in practice we only need
                    // to do it 1-2 times per line.)
                    min_value = 0;
                    for (int j = (ring_pos + 1) % RINGBUF_SIZE; j != ring_pos; j = (j + 1) % RINGBUF_SIZE) {
                        if (ringbuf[j] < min_value) min_value = ringbuf[j];
                    }
//                    std::cout << "rescan for min = " << min_value << "\n";
                }
            }

            // Store the new value in ringbuf
            ringbuf[ring_pos] = value;
            ring_pos = (ring_pos + 1) % RINGBUF_SIZE;
            if (ring_pos == 0) ring_full = true;

            // Update minimum
            if (value < min_value) min_value = value;

            // Detect sync edges, with some hysteresis
            const int16_t down_limit = min_value + 100; // magic numbers
            const int16_t up_limit = down_limit + 20;
//            std::cout << value << "(" << down_limit << ") ";
            if (up && value > up_limit) {
                up = false;
//                std::cout << "up edge at " << file_offset + i << "\n";
            } else if (!up && value < down_limit) {
                up = true;

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
//                std::cout << "len " << len << " gap " << gap << " value " << value << " down_limit " << down_limit << "\n";

                if (gap == UNKNOWN && last_gap == LONG) {
                    // We can't really tell during the equalisation pulses as
                    // the baseline drifts too high, but if the last valid gap
                    // wasn't a short one...
                    std::cout << "unexpected down-edge spacing " << len << " (expected " << LINE_SAMPLES << " or " << HALF_LINE_SAMPLES << ") at " << pos << "\n";
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
//                        std::cout << "field 1\n";
                        last_field_num = 1;
                    } else if (abs(field_len - FIELD_2_SAMPLES) < 500) {
                        if (last_field_num == 2) {
                            std::cout << "duplicate field 2 at " << pos << "\n";
                        }
//                        std::cout << "field 2\n";
                        last_field_num = 2;
                    } else {
                        std::cout << "unexpected field len " << field_len << " (expected " << FIELD_1_SAMPLES << " or " << FIELD_2_SAMPLES << ") at " << pos << "\n";
                        last_field_num = 0;
                    }
                }

                last_gap = gap;
            }

            // Complain if we haven't seen a field in a while.
            if (seen_field && (pos - last_field) > (2 * FIELD_1_SAMPLES)) {
                std::cout << "no field seen at " << pos << "\n";
            }
        }
//        std::cout << "\n";

        file_offset += FILEBUF_SIZE;
    }
}
