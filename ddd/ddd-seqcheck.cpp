// With DomesdayDuplicator modified to overwrite each transfer with a count
// value immediately after it is received, check that the resulting output is
// correct.

#include <iostream>
#include <cstdint>
#include <cstdlib>

constexpr int COUNT_EXPECTED = 1 << 17;

constexpr int FILEBUF_SIZE = 1 << 10;

int main() {
    // Buffer for reading from file
    uint16_t filebuf[FILEBUF_SIZE];
    uint64_t file_offset = 0;

    uint16_t last_value = 0;
    int value_count = 0;
    int state = 0;

    while (true) {
        // Read data into filebuf
        std::cin.read(reinterpret_cast<char *>(filebuf), sizeof filebuf);
        if (std::cin.eof()) break;

        // Process samples from filebuf
        for (int i = 0; i < FILEBUF_SIZE; i++) {
            const uint64_t pos = file_offset + i;
            const uint16_t value = filebuf[i] >> 6;

            if (state == 0) {
                // The first value
                state = 1;
            } else if (state == 1) {
                // Waiting for the value to change for the first time
                if (value != last_value) {
                    value_count = 1;
                    state = 2;
                }
            } else {
                // Normal operation -- check the count goes up correctly
                if (value != last_value) {
                    if (value != last_value + 1 && !(value == 0 && last_value == 510)) {
                        std::cout << "value stepped from " << last_value << " to " << value << " at " << pos << "\n";
                    }
                    if (value_count != COUNT_EXPECTED) {
                        std::cout << "value " << last_value << " count " << value_count << " (expected " << COUNT_EXPECTED << ") at " << pos << "\n";
                    }
                    value_count = 1;
                } else {
                    value_count++;
                }
            }

            last_value = value;
        }

        file_offset += FILEBUF_SIZE;
    }
}
