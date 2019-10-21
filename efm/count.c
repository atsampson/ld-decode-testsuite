/* Convert the output of GNU Radio's Clock Recovery MM block (written out as
 * chars) to .efm format. */

#include <stdio.h>

int main() {
    int count = 0;
    int last = 0;
    while (1) {
        int c = getchar();
        if (c == EOF)
            break;

        int this = c < 128;
        if (this != last) {
            if (count >= 3 && count <= 11) {
                putchar(count);
            }
            count = 0;
        }

        count++;
        last = this;
    }
}
