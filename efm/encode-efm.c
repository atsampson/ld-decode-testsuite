/* Given a .efm stream, produce a stream of 40 MHz 16-bit signed samples
 * (without any filtering or preemphasis).
 *
 * This does the opposite of ld-ldstoefm -- you should be able to pipe its
 * output into ld-ldstoefm and get the input back (once the PLL has locked up).
 */

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

int main() {
    /* The current sample value */
    int16_t value = 10000;
    /* The timestamp for the sample we're about to output */
    double now = 0.0;
    /* The timestamp for the next 0/1 transition */
    double next = 0.0;

    while (true) {
        int count = getchar();
        if (count == EOF)
            break;

        next += count / 4321800.0;

        while (now < next) {
            fwrite(&value, sizeof value, 1, stdout);
            now += 1 / 40.0e6;
        }

        value = -value;
    }

    return 0;
}
