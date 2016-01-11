import math
import string
import pyclipper
import time
from GerberReader import GerberLayer, GerberData

__author__ = 'Thompson'

"""
Employs recursive descent parsing to parse a Gerber data file.
This methodology is more flexible to bad formatting of data file
This is a fully compliant parser.
"""

""" Maximum arc length when drawing arc segments """
MAX_ARC_LENGTH = 750
""" Minimum number of segs per 360 degrees """
MIN_SEG = 17

""" Set to True to print warnings to console """
PrintWarnings = True
""" Set to True to print errors to console """
PrintErrors = True
""" Set to True to print deprecated uses to console """
PrintDeprecatedUses = False

class ParseData:
    """
    :type str: str
    :type pos: int
    :type buffer: str
    """
    def __init__(self, str):
        self.str = str.replace('\n','').replace('\r','')
        self.strlen = len(self.str)
        self.gd = GerberData()
        self.pos = -1

        self.gd = GerberData()
        self.trackData = []

        self.isDark = True
        self.x = 0
        self.y = 0
        self.i = 0
        self.j = 0
        self.xold = 0
        self.yold = 0

        self.tracks = []
        self.regions = []
        self.pads = []
        self.trackseg = -1
        self.padseg = -1
        self.regionseg = -1
        self.aperture = -1
        self.tracksize = []
        self.macros = []
        self.macrosName = []
        self.macroParams = []
        self.N_macros = 0
        self.apertures = [[] for i in range(50)]
        self.interpMode = 1
        self.arcMode = 0
        self.regionMode = False

        self.errors = 0
        self.warnings = 0
        self.deps = 0

    def parseUntil(self, marker):
        st = self.pos
        while self.pos < self.strlen and self.str[self.pos] != marker:
            self.pos += 1
        return self.str[st:self.pos]

    def findNextChar(self):
        """
        :return index of next non-whitespace character or -1 if end of expression
        :rtype str
        """
        if self.pos == -2: return -2
        self.pos += 1
        if self.pos >= self.strlen:
            self.pos = -2
            return -2
        return self.str[self.pos]
        # if self.pos == -2: return -2
        # while True:
        #     self.pos += 1
        #     if self.pos >= self.strlen:
        #         self.pos = -2
        #         return -2
        #     if not self.str[self.pos].isspace():
        #         return self.str[self.pos]

    def getChar(self):
        """
        :rtype str
        """
        return self.str[self.pos] if self.pos >= 0 else self.pos

    def parseSign(self):
        tmp = self.getChar()
        if tmp == '-':
            self.pos += 1
            return -self.parseInt()
        else:
            if tmp == '+': self.pos += 1
            return self.parseInt()

    def parseInt(self):
        oldp = self.pos
        while True:
            tmp = self.getChar()
            if not tmp.isdigit():
                return int(self.str[oldp:self.pos])
            if self.findNextChar() == -2:
                return int(self.str[oldp:self.pos])

    def parseFloat(self):
        val = self.parseSign()
        tmp = self.getChar()
        if tmp == '.':
            if self.findNextChar() == -2: return val
            op = self.pos
            frac = self.parseInt()
            val += frac*(10**(op - self.pos))
        # if tmp == 'E' or tmp == 'e':
        #     self.findNextChar()
        #     val *= 10 ** self.parseInt()
        return val

    def store_to_gd(self):
        # Stores the existing set of layer data as polygonal data points
        # This is the equivalent of rasterisation of the draw commands
        li = len(self.gd.layers) / 3
        # Expand tracks from centrelines based on aperture
        track_outlines = []
        for seg in range(len(self.tracks)):
            for vert in range(len(self.tracks[seg]) - 1):
                xstart = self.tracks[seg][vert][0]
                xend = self.tracks[seg][vert + 1][0]
                ystart = self.tracks[seg][vert][1]
                yend = self.tracks[seg][vert + 1][1]
                singletrack = pyclipper.MinkowskiSum(self.apertures[self.tracksize[seg]], \
                                                     [[xstart, ystart], [xend, yend]], -1)
                if len(singletrack) > 1:
                    biggest = []
                    myarea = 0
                    for mypath in singletrack:
                        newarea = pyclipper.Area(mypath)
                        if newarea > myarea:
                            biggest = mypath
                            myarea = newarea
                    singletrack = [[]]
                    singletrack[0] = (biggest)
                track_outlines.extend(singletrack)

        mergedBounds = self.union_boundary(track_outlines + self.pads, self.regions)

        self.trackData.extend(self.tracks)

        # Store data into layers.
        self.gd.layers.append(GerberLayer(self.isDark, str(li) + "_Tracks", track_outlines, type=GerberLayer.TYPE_TRACK))
        self.gd.layers.append(GerberLayer(self.isDark, str(li) + "_Boundaries", mergedBounds, False, False, "blue", GerberLayer.TYPE_BOUNDARY))
        self.gd.layers.append(GerberLayer(self.isDark, str(li) + "_Regions", self.regions, type=GerberLayer.TYPE_REGION))
        self.gd.layers.append(GerberLayer(self.isDark, str(li) + "_Pads", self.pads, type=GerberLayer.TYPE_PAD, color="#009000"))

        # clear cache
        self.regions = []
        self.pads = []
        self.tracks = []
        self.tracksize = []
        self.trackseg = -1
        self.padseg = -1
        self.regionseg = -1

    def union(self, paths, union_type=pyclipper.PFT_NONZERO):
        # performs union on list, or list of lists

        c = pyclipper.Pyclipper()

        polyclip = paths

        # for path in range(len(polyclip)):
        #    c.AddPaths(polyclip[path], pyclipper.PT_SUBJECT, True)
        c.AddPaths(polyclip, pyclipper.PT_SUBJECT, True)
        polyclip = c.Execute(pyclipper.CT_UNION, union_type, union_type)
        c.Clear()

        return polyclip

    def union_boundary(self, boundarys, regions):
        # union intersecting polygons on boundary

        if boundarys:
            boundary = self.union(boundarys, pyclipper.PFT_NONZERO)
            paths = boundary
        else:
            boundary = []
            paths = []

        if regions:
            region = self.union(regions, pyclipper.PFT_NONZERO)
            paths.extend(region)
            boundary = self.union(paths, pyclipper.PFT_NONZERO)

        if boundary:
            boundary = pyclipper.CleanPolygons(boundary)
            # boundary = pyclipper.SimplifyPolygons(boundary)
            for segs in boundary:
                if len(segs) == 0:
                    boundary.remove([])
                    break

        return boundary

    def warn(self, msg):
        self.warnings += 1
        if PrintWarnings: print("  WARNING: " + msg + "   (pos = " + str(self.pos) + ")")

    def error(self, msg):
        self.errors += 1
        if PrintErrors: print("  ERROR: " + msg + "   (pos = " + str(self.pos) + ") " + self.str[max(0,self.pos - 20):self.pos])

    def error_line(self, msg, marker='*'):
        self.errors += 1
        if PrintErrors: print("  WARNING: " + msg + "Ignoring data: " + self.parseUntil(marker))

    def check_char(self, chr='*'):
        if self.getChar() == chr:
            self.pos += 1
        else:
            self.error("Command missing '" + chr + "' symbol")

    def dep(self, msg):
        self.deps += 1
        if PrintDeprecatedUses: print("  DEPRECATED COMMAND: " + msg + "   (pos = " + str(self.pos) + ")")



def add_circle(ptlist, diameter, isCW=True):
    steps = max(int(diameter/(2.0*MAX_ARC_LENGTH)), MIN_SEG)
    angleStep = 2.0 * math.pi / (steps - 1) * (-1 if isCW else 1)
    print "  Circle ", steps, ", ", angleStep
    for i in range(steps):
        angle = i*angleStep
        x = (diameter / 2.0) * math.cos(angle)
        y = (diameter / 2.0) * math.sin(angle)
        ptlist.append([x, y])

def add_arc(ptlist, r, centreX, centreY, startAngle, endAngle, isCW):
    endAngle -= startAngle  # convert to delta
    if endAngle < 0: endAngle += 2*math.pi  # make it positive
    if isCW == (endAngle > 0):  # requires outer arc
        endAngle -= 2*math.pi
    # calc steps such that arc length < MAX_ARC_LENGTH and min seg per 360 deg is maintained
    steps = int(abs(endAngle)*max(r/MAX_ARC_LENGTH, MIN_SEG/(2*math.pi)))
    angleStep = endAngle / (steps - 1.0)

    print "  Arc at (X,Y) = ", centreX, ", ", centreY
    print "   start angle = ", (180*startAngle/math.pi)
    print "   delta angle = ", (180*endAngle/math.pi)
    print "   angle step = ", (180*angleStep/math.pi), " steps=", steps

    for i in range(steps):
        xarcseg = centreX + r * math.cos(startAngle + angleStep * i)
        yarcseg = centreY + r * math.sin(startAngle + angleStep * i)
        xarcseg = round(xarcseg)
        yarcseg = round(yarcseg)
        ptlist.append([xarcseg, yarcseg])

def load_file(filename):
    """
    Parse gerber file from file path
    :rtype filename: str
    :rtype: [GerberData, list]
    """
    file = open(filename, 'r')
    str = file.read()
    file.close()

    return parse(str)


def parse(str):
    """
    Parses Gerber data file
    :return GerberData object and tracks list
    :type lines: str
    :rtype [GerberData,list]
    """

    pd = ParseData(str)
    return _parse0(pd)


def _parse0(pd):
    """
    :type pd: ParseData
    """
    stt = time.time()
    pd.pos = 0
    while True:
        if pd.pos == -2 or pd.pos >= pd.strlen:
            pd.warn("File was not terminated with 'M02*' command")
            break
        tmp = pd.getChar()
        if tmp == 'D':  # Draw, move, flash or set aperture command
            pd.pos += 1
            cd = pd.parseInt()
            if cd == 0 or (3 < cd < 10) or cd >= len(pd.apertures):
                pd.error_line("Invalid aperture code D" + str(cd) + ". ")
            if cd == 1:  # interpolate
                if pd.interpMode == 1:  # linear interpolation
                    if pd.regionMode:
                        pd.regions[pd.regionseg].append([pd.x, pd.y])
                    else:
                        pd.tracks[pd.trackseg].append([pd.x, pd.y])
                elif pd.arcMode == 0:  # Single Quadrant Mode
                    if pd.i < 0:
                        pd.warn("Negative sign for offset i was ignored for SINGLE QUADRANT mode")
                        pd.i *= -1
                    if pd.j < 0:
                        pd.warn("Negative sign for offset j was ignored for SINGLE QUADRANT mode")
                        pd.j *= -1

                    pd.warn("Single quadrant mode not implemented yet")
                else:  # Multi Quadrant Mode
                    # Implementation note:
                    # Draws a circle that passes through the start and end point with radius of distance
                    # from offset centre point to start point (i.e. the offset centre point will
                    # be moved such that the distance to the and end point become equal to the distance
                    # to the start point)
                    r = pow(pd.i, 2) + pow(pd.j, 2)

                    # The line that perpendicular bisects the line joining A (start) and B (end) is where
                    # the centre point will lie. The distance from centre point to A and B is r (circle radius)
                    # The distance from the line connecting AB to centre point is thus sqrt(r^2-L^2)
                    # Where L is the distance between midpoint and A or B.
                    # To optimise, square root is not taken until the end and 2L is distance between A and B
                    # and is the value that the normal must be divided by to normalise to length 1

                    # Mid Point
                    mx = (pd.xold + pd.x)/2
                    my = (pd.yold + pd.y)/2
                    # Normal
                    ny = pd.x - pd.xold
                    nx = pd.yold - pd.y
                    tmp = nx*nx + ny*ny  # size of vector squared
                    tmp = math.sqrt(float(r)/tmp - 0.25)  # normalise normal and scale by radius
                    if abs(pd.i - nx*tmp) + abs(pd.j - ny*tmp) > abs(pd.i + nx*tmp) + abs(pd.j + ny*tmp):
                        # pick the side the offset point lies on
                        tmp *= -1
                    centreX = mx + nx*tmp
                    centreY = my + ny*tmp
                    add_arc(pd.regions[pd.regionseg] if pd.regionMode else pd.tracks[pd.trackseg],
                               math.sqrt(r), centreX, centreY,
                               math.atan2(pd.yold - centreY, pd.xold - centreX),
                               math.atan2(pd.y - centreY, pd.x - centreX), pd.interpMode == 2)
                # Consume offset
                pd.i = 0
                pd.j = 0
            elif cd == 2:  # move
                if pd.regionMode:  # Finish current region and creates a new one
                    pd.regions.append([])
                    pd.regionseg += 1
                    # pd.regions.append([])
                    pd.regions[pd.regionseg].append([pd.x, pd.y])
                else:  # Finish current track and creates a new one
                    pd.tracksize.append(pd.aperture)
                    pd.trackseg += 1
                    pd.tracks.append([[pd.x, pd.y]])
            else:
                if pd.regionMode:
                    pd.error("Command D" + str(cd) + " is not allowed in region mode")
                if cd == 3:  # flash aperture
                    pd.padseg += 1
                    pd.pads.append([])
                    for verts in pd.apertures[pd.aperture]:
                        pd.pads[pd.padseg].append([pd.x + verts[0], pd.y + verts[1]])
                else:  # Set aperture
                    pd.aperture = cd
            pd.check_char('*')
        elif tmp == 'G':
            pd.pos += 1
            cd = pd.parseInt()
            if 0 < cd < 4:  # Linear interpolation
                pd.interpMode = cd
                if pd.getChar() != '*':
                    pd.dep("Use of G" + str(cd) + " in a data block is deprecated")
                    continue
            elif cd == 4:  # Comment
                print " Comment G04: ", pd.parseUntil('*')
            elif cd == 36:  # Region mode ON
                pd.regionMode = True
            elif cd == 37:  # Region mode OFF
                pd.regionMode = False
            elif cd == 54:
                if pd.getChar() != 'D':
                    pd.error("Command G54 wasn't followed by valid aperture Dnn. This command is also deprecated and should be removed")
                else:
                    pd.pos += 1
                    cd = pd.parseInt()
                    if cd < 10 or cd >= len(pd.apertures):
                        pd.error("Invalid aperture index D" + str(cd) + " in deprecated commands G70.")
                    else:
                        pd.aperture = cd
                        pd.dep("Deprecated command found: G54 (command was parsed but should be removed)")
            elif cd == 70:  # Set mode to INCH
                pd.gd.units = 1
                pd.dep("Deprecated command found: G70 (command was parsed but should be removed)")
            elif cd == 71:  # Set mode to MM
                pd.gd.units = 0
                pd.dep("Deprecated command found: G71 (command was parsed but should be removed)")
            elif cd == 74:  # Set arc mode to SINGLE QUADRANT
                pd.arcMode = 0
            elif cd == 75:  # Set arc mode to MULTI QUADRANT
                pd.arcMode = 1
            elif cd == 90:  # set absolute coordinate format - deprecated command
                pd.dep("Deprecated command found: G90 (command was IGNORED)")
            elif cd == 91:  # set incremental coordinate format - deprecated command
                pd.dep("Deprecated command found: G91 (command was IGNORED)")
            else:
                pd.error_line("Unknown code: G" + str(cd) + ". ")
            pd.check_char('*')
        elif tmp == 'M':
            pd.pos += 1
            cd = pd.parseInt()
            if cd == 2:
                pd.check_char('*')
                if pd.regionMode:
                    pd.warn("End of file reached while in region mode")
                if pd.findNextChar() != -2:
                    pd.warn("Unparsed data: " + pd.str[pd.pos:-1])
                break
            else:
                pd.error_line("Invalid code: M" + str(cd) + ". ")
            pd.check_char('*')
            # continue
        elif tmp == 'X':
            pd.pos += 1
            pd.xold = pd.x
            pd.x = pd.parseSign()
        elif tmp == 'Y':
            pd.pos += 1
            pd.yold = pd.y
            pd.y = pd.parseSign()
        elif tmp == 'I':
            pd.pos += 1
            pd.i = pd.parseSign()
        elif tmp == 'J':
            pd.pos += 1
            pd.j = pd.parseSign()
        elif tmp == '%':  # Extended command codes are surrounded by %
            cmd = pd.str[pd.pos+1:pd.pos+3]
            pd.pos += 2
            if cmd == "FS":  # File format
                op = string.find(pd.str,'X',pd.pos)
                # if pd.findNextChar() != 'L' or pd.findNextChar() != 'A' or pd.findNextChar() != 'X':
                #     pd.error("FS command was not followed by LA")
                #     pd.pos = op
                # else:
                #     if not pd.findNextChar().isdigit() or not pd.findNextChar().isdigit():
                #         pd.error("FSLAX command must be followed by two digits. Command was ignored")
                #     else:
                #         pd.gd.fraction = int(pd.getChar())
                #         if pd.findNextChar() != 'Y':
                #             pd.error_line("FSLAXnn command was not followed by Ynn. ")
                #         else:
                #             print("  Ignored remainder of FSLA: " + pd.parseUntil('*'))
                pd.gd.fraction = int(pd.str[op + 2]) # we only care about the fractional digit
                pd.parseUntil('*')
            elif cmd == "MO":  # Set unit
                tmp = pd.findNextChar()
                if tmp == 'M':
                    pd.pos += 2
                    # if pd.findNextChar() != 'M':
                    #     pd.error("Unit sepcified invalid. It was set to MM")
                    # else:
                    #     pd.findNextChar()
                    pd.gd.units = 0
                elif tmp == 'I':
                    pd.pos += 2
                    # if pd.findNextChar() != 'N':
                    #     pd.error("Unit sepcified invalid. It was set to INCH")
                    # else:
                    #     pd.findNextChar()
                    pd.gd.units = 1
                else:
                    pd.error_line("Invalid unit specifier. ")
            elif cmd == "AD":  # Add aperture
                if pd.str[pd.pos + 1] != 'D':
                    pd.error("Aperture index must be specified after AD command")
                    continue
                pd.pos += 2
                pd.aperture = pd.parseInt()
                while len(pd.apertures) <= pd.aperture: pd.apertures.append([])
                holesize = -1
                if pd.str[pd.pos + 1] == ',':
                    tmp = pd.str[pd.pos]
                    pd.pos += 2
                    if tmp == 'C':  # Circle
                        size = pd.parseFloat() * 10 ** pd.gd.fraction
                        add_circle(pd.apertures[pd.aperture], size, False)
                        if pd.getChar() == 'X':
                            pd.pos += 1
                            holesize = pd.parseFloat() * 10 ** pd.gd.fraction
                            add_circle(pd.apertures[pd.aperture], holesize, True)
                        print "   read aperture", pd.aperture, ": circle diameter", size, ", hole size", holesize
                    elif tmp == 'R':  # Rectangle
                        w = pd.parseFloat() * 10 ** pd.gd.fraction / 2.0
                        pd.check_char('X')
                        h = pd.parseFloat() * 10 ** pd.gd.fraction / 2.0
                        pd.apertures[pd.aperture].extend([[-w, -h], [w, -h], [w, h], [-w, h], [-w, -h]])
                        if pd.getChar() == 'X':
                            pd.pos += 1
                            holesize = pd.parseFloat() * 10 ** pd.gd.fraction
                            add_circle(pd.apertures[pd.aperture], holesize, True)
                        print "   read aperture", pd.aperture, ": rectangle W", w, ", H", h, ", hole size", holesize
                    elif tmp == 'O':  # Rectangle capped with semicircles
                        w = pd.parseFloat() * 10 ** pd.gd.fraction
                        pd.check_char('X')
                        h = pd.parseFloat() * 10 ** pd.gd.fraction

                        NVERTS = 16
                        if w > h:
                            for i in range(NVERTS / 2):
                                angle = i * math.pi / (NVERTS / 2 - 1.0) + math.pi / 2.0
                                x = -(w - h) / 2.0 + (h / 2.0) * math.cos(angle)
                                y = (h / 2.0) * math.sin(angle)
                                pd.apertures[pd.aperture].append([x, y])
                            for i in range(NVERTS / 2):
                                angle = i * math.pi / (NVERTS / 2 - 1.0) - math.pi / 2.0
                                x = (w - h) / 2.0 + (h / 2.0) * math.cos(angle)
                                y = (h / 2.0) * math.sin(angle)
                                pd.apertures[pd.aperture].append([x, y])
                        else:
                            for i in range(NVERTS / 2):
                                angle = i * math.pi / (NVERTS / 2 - 1.0) + math.pi
                                x = (w / 2.0) * math.cos(angle)
                                y = -(h - w) / 2.0 + (w / 2.0) * math.sin(angle)
                                pd.apertures[pd.aperture].append([x, y])
                            for i in range(NVERTS / 2):
                                angle = i * math.pi / (NVERTS / 2 - 1.0)
                                x = (w / 2.0) * math.cos(angle)
                                y = (h - w) / 2.0 + (w / 2.0) * math.sin(angle)
                                pd.apertures[pd.aperture].append([x, y])

                        if pd.getChar() == 'X':
                            holesize = pd.parseFloat() * 10 ** pd.gd.fraction
                            add_circle(pd.apertures[pd.aperture], holesize, True)
                        print "   read aperture", pd.aperture, ": o-rectangle ", w, " x ", h, ", hole size", holesize
                    elif tmp == 'P':  # Regular polygon
                        size = pd.parseFloat() * 10 ** pd.gd.fraction

                        pd.check_char('X')
                        n = pd.parseFloat()
                        rot = 0
                        if pd.getChar() == 'X':
                            pd.pos += 1
                            rot = pd.parseFloat()
                        for i in range(n):
                            angle = -(i * 2.0 * math.pi / (n - 1.0))
                            x = (size / 2.0) * math.cos(angle + rot)
                            y = (size / 2.0) * math.sin(angle + rot)
                            pd.apertures[pd.aperture].append([x, y])

                        if pd.getChar() == 'X':
                            pd.pos += 1
                            holesize = pd.parseFloat() * 10 ** pd.gd.fraction
                            add_circle(pd.apertures[pd.aperture], holesize, True)
                        print "   read aperture", pd.aperture, ": polygon n", n, " diameter ", size, ", rot ", rot, " hole size", holesize
                    else:
                        pd.error("Unknown aperture shape " + tmp)
                else:  # Macro
                    # parseMacro(pd, tmp)
                    pd.error("Use of macros not supported yet")
            elif cmd == "AM":  # Create aperture macro
                pd.macrosName.append(pd.parseUntil('*'))  # Parse name of macro
                tmp = pd.findNextChar()
                tmplines = []
                while tmp != '%':  # Store macro commands (only parsed when added)
                    tmplines.append(pd.parseUntil("*"))
                    tmp = pd.findNextChar()
                    if tmp == -2:
                        # This is required to prevent infinite loop
                        pd.check_char('%')
                pd.macros.append(tmplines)
                pd.N_macros += 1
                pd.pos += 1
                continue
            elif cmd == "SR":  # Set and repeat

                pass
            elif cmd == "LP":  # Create new layer
                tmp = pd.findNextChar()
                if tmp == 'D':
                    pd.store_to_gd()
                    pd.pos += 1
                    pd.isDark = True
                elif tmp == 'C':
                    pd.store_to_gd()
                    pd.pos += 1
                    pd.isDark = False
                else:
                    pd.error("Command LP must be followed by C or D but found " + tmp)
            else:
                pd.error_line("Unknown command code " + tmp + ". ", '*')
            pd.check_char('*')
            pd.check_char('%')
    print "Execution time: ",(time.time() - stt)
    # Finalise parsing
    pd.store_to_gd()
    print " Parsing completed with ", pd.warnings, " warnings, ", pd.deps, " deprecated commands and ", pd.errors, " errors"
    return [pd.gd, pd.trackData]


def parseMacro(pd):
    """
    Parses macro - complicated by variables and expressions so we're writing a
    parser within a parser
    :type pd: ParseData
    """
    pd.findNextChar()
    mn = pd.parseUntil('*')
    tmp = string.find(mn,',')
    if tmp != -2: # macro has params
        pd.pos -= len(mn) + tmp
        mn = mn[0:tmp]
        pd.findNextChar()
    for nm in pd.macrosName:
        if mn == nm:
            # TODO: add macro data to aperture
            break





