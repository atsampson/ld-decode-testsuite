#!/usr/bin/python3
# Decode VBI information from a .tbc.json file.

def getbcd(bcd):
    """Read a BCD-encoded number.
    Raises ValueError if any of the digits aren't valid BCD."""
    if bcd == 0:
        return 0
    else:
        digit = bcd & 0xF
        if digit > 9:
            raise ValueError("Non-decimal BCD digit")
        return (10 * getbcd(bcd >> 4)) + digit

def isbcd(bcd):
    """Return True if bcd only contains digits 0-9."""
    try:
        getbcd(bcd)
        return True
    except ValueError:
        return False

class FieldInfo:
    """Information about a field, extracted from the VBI data."""

    def __init__(self, fieldjson):
        # The data values we're extracting
        self.status = None
        self.disctype = None
        self.minutes = None
        self.seconds = None
        self.frames = None
        self.picno = None
        self.stopcode = None
        self.chapter = None

        self.parse_fm(fieldjson)
        self.parse_vbi(fieldjson)

    def __str__(self):
        bits = [
            self.status,
            self.disctype,
            str(self.minutes) + "m" if (self.minutes is not None) else None,
            str(self.seconds) + "s" if (self.seconds is not None) else None,
            str(self.frames) + "f" if (self.frames is not None) else None,
            self.picno,
            "stop" if (self.stopcode is not None) else None,
            "ch" + str(self.chapter) if (self.chapter is not None) else None,
            ]
        return " ".join([str(bit) for bit in bits if bit is not None])

    def parse_fm(self, fieldjson):
        """Extract data from the FM code."""

        ntsc = fieldjson.get("ntsc")
        if ntsc is None:
            return
        if not ntsc.get("isFmCodeDataValid", False):
            return
        fm_data = ntsc.get("fmCodeData")
        if fm_data is None:
            return

        # ld-process-vbi returns just the 20 data bits, in their original
        # order, so we need to reverse them
        value = 0
        for i in range(20):
            value |= ((fm_data >> i) & 1) << (19 - i)

        if (value & 0xF) == 0xA:
            # Lead in
            self.status = "leadin"
        elif (value & 0xF) == 0xC:
            # Lead out
            self.status = "leadout"
        elif (value & 0xF) in (0xB, 0xD) and isbcd(value & 0xFFFF0):
            # CLV mins/secs (0xB for the first 100 frames of the disc)
            self.status = "picture"
            self.disctype = "clv"
            self.minutes = getbcd((value >> 12) & 0xFF)
            self.seconds = getbcd((value >> 4) & 0xFF)
        elif isbcd(value):
            # CAV picture number
            self.status = "picture"
            self.disctype = "cav"
            self.picno = getbcd(value)
        else:
            #print("unknown FM", hex(value))
            pass

    def parse_vbi(self, fieldjson):
        """Extract data from the biphase code."""

        vbi = fieldjson.get("vbi")
        if vbi is None:
            return
        vbi_data = vbi.get("vbiData")
        if vbi_data is None:
            return

        for value in vbi_data:
            if value == 0:
                # No code
                pass
            elif value == 0x88FFFF:
                # Lead in
                self.status = "leadin"
            elif value == 0x80EEEE:
                # Lead out
                self.status = "leadout"
            elif value == 0x82CFFF:
                # Stop code (stop on the *previous* field)
                self.stopcode = True
            elif value == 0x87FFFF:
                # CLV
                self.disctype = "clv"
            elif (value & 0xF0FF00) == 0xF0DD00 and isbcd(value & 0x0F00FF):
                # CLV hours/mins
                self.status = "picture"
                self.disctype = "clv"
                self.minutes = (60 * getbcd((value >> 16) & 0xF)) + getbcd(value & 0x0000FF)
            elif (value & 0xF0F000) == 0x80E000 and ((value >> 16) & 0xF) >= 0xA and isbcd(value & 0x000FFF):
                # CLV sec/frame
                self.status = "picture"
                self.disctype = "clv"
                self.seconds = (10 * (((value >> 16) & 0xF) - 0xA)) + getbcd((value >> 8) & 0xF)
                self.frames = getbcd(value & 0xFF)
            elif (value & 0xF00000) == 0xF00000 and isbcd(value & 0x07FFFF):
                # CAV picture number
                # Top bit duplicates stop code on early discs
                self.status = "picture"
                self.disctype = "cav"
                self.picno = getbcd(value & 0x7FFFF)
            elif (value & 0xF00FFF) == 0x800DDD and isbcd(value & 0x07F000):
                # Chapter number
                # Top bit is 0 for 400 tracks at start of chapter
                self.chapter = getbcd((value >> 12) & 0x7F)
            elif (value & 0xFFF000) in (0x8DC000, 0x8BA000):
                # XXX Programme status code
                # DC = CX on, BA = CX off
                # Other bits indicate audio channel configuration
                pass
            elif (value & 0xF0F000) == 0x80D000:
                # XXX User code in lead in/out
                pass
            else:
                #print("unknown VBI", hex(value))
                pass
