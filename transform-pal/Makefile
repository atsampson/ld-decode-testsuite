all: \
	calibrate-bins \
	report-bins

%: %.cpp
	g++ -Wall -g -march=native -O3 -o $@ $<
