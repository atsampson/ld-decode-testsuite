// Very rough frequency count for the output of a Domesday Duplicator.
// I fed in a 1kHz sine wave; this counts spacing between zero-crossings and
// complains if any cycles are too far away from the median length.

#include <algorithm>
#include <iostream>
#include <cstdint>
#include <cstdlib>

constexpr int BUFSIZE = 256;
constexpr int AVGSIZE = 1001;

int main(int argc, char *argv[]) {
    int16_t buf[BUFSIZE];

    constexpr int16_t hyst = 3;
    bool up = false;
    uint64_t streampos = 0;
    uint64_t lastzc = 0;

    uint64_t avgbuf[AVGSIZE] = {0};
    int avgpos = 0;
    uint64_t avg = 0;
    bool avgok = false;

    uint64_t lastshown = 0;

    while (!std::cin.eof()) {
        std::cin.read(reinterpret_cast<char *>(buf), sizeof buf);

        for (int i = 0; i < BUFSIZE; i++) {
            const int16_t value = buf[i] >> 6;
            //std::cout << value << " " << up << "\n";
            if (up && value > hyst) {
                up = false;

                const uint64_t len = (streampos + i) - lastzc;
                lastzc = streampos + i;
                //std::cout << len << "\n";

                if (avgok && llabs(len - avg) > 1000) {
                    std::cout << "pos=" << (streampos+i) << " len=" << len << " avg=" << avg << "\n";
#if 0
                    for (int j = 0; j < i; j++) {
                        const uint64_t pos = streampos + j;
                        if (pos > lastshown) {
                            std::cout << "  [" << pos << "] = " << (buf[j] >> 6) << "\n";
                            lastshown = pos;
                        }
                    }
#endif
                }

                avgbuf[avgpos] = len;
                avgpos = (avgpos + 1) % AVGSIZE;

                if (avgpos == 0) {
                    std::sort(std::begin(avgbuf), std::end(avgbuf));
                    avg = avgbuf[AVGSIZE / 2];
                    std::cout << "avg=" << avg << "\n";
                    avgok = true;
                }
            } else if (!up && value < -hyst) {
                up = true;
            }
        }

        streampos += BUFSIZE;
    }
}
