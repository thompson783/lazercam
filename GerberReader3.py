import math
import string
import pyclipper
import time

__author__ = 'Thompson'

"""
Employs recursive descent parsing to parse a Gerber data file.
This methodology is more flexible to bad formatting of data file
This is a fully compliant parser.
"""

# Alternative is a MIN_SEG_360_R which is like MIN_SEG_360 but also dependent on radius
# Larger r should have slightly higher segment counts
""" Maximum arc length when drawing arc segments in mm. The unit must be in MM and NOT INCHES """
MAX_ARC_LENGTH = 0.25
""" Minimum number of segs per 360 degrees. THIS MUST BE >= 1 """
MIN_SEG_PER_360 = 16
""" Absolute minimum number of segments no matter the arc angle. THIS MUST BE >= 1 """
MIN_SEG = 1

""" Set to True to print warnings to console """
PrintWarnings = True
""" Set to True to print errors to console """
PrintErrors = True
""" Set to True to print deprecated uses to console """
PrintDeprecatedUses = False


class GerberLayer:
    """Holds the data of a single layer"""

    TYPE_OTHER = 0
    TYPE_TRACK = 1
    TYPE_BOUNDARY = 2
    TYPE_REGION = 3
    TYPE_PAD = 4
    TYPE_PCBEDGE = 5
    TYPE_MERGEDCOPPER = 6

    isDark = True           # Whether this is an additive layer (true) or clear layer (false)
    name = ""               # Name of layer
    points = []             # List of polygons where
                            #   polygon is a list of vertices where
                            #   vertex is [x,y] point
    visible = True          # False to hide the layer
    filled = True           # False means outline
    color = "dark green"    # default is green
    type = 0                # layer type

    def __init__(self, isDark, name, points=None, visible=True, filled=True, color="dark green", type=TYPE_OTHER):
        self.isDark = isDark
        self.name = name
        self.visible = visible
        self.filled = filled
        self.color = color
        self.type = type
        self.points = [] if points is None else points


class GerberData:
    """ Holds the data for a Gerber file """

    def __init__(self):
        self.layers = []
        """ :type layers: list[GerberLayer]"""

    units = 0       # 0 is mm, 1 is in
    digits = 0      # not used
    fraction = 0    # number of dec. places to shift each data point

    """ Bounds WITH pcb edge """
    xmin = 0
    xmax = 0
    ymin = 0
    ymax = 0

    """ Bounds WITHOUT pcb edge """
    xmin2 = 0
    xmax2 = 0
    ymin2 = 0
    ymax2 = 0

    originx = 0
    originy = 0

    """
    List of GerberLayer objects
    :type layers: list[GerberLayer]
    """
    layers = []

    # Mode assumed to be absolute


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
        self.layerSet = 0
        self.fscl = 1
        self.vars = {}

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
        self.pos = self.str.find(marker, self.pos)
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
        return self.str[self.pos]

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
            self.pos += 1
            if self.pos >= self.strlen:
                self.pos = -2
                return int(self.str[oldp:])

    def parseFloat(self, scaled=True):
        val = self.parseSign()
        tmp = self.getChar()
        if tmp == '.':
            self.pos += 1
            if self.pos >= self.strlen:
                self.pos = -2
                return val
            op = self.pos
            val += self.parseInt()*(10**(op - self.pos))
        return val * self.fscl if scaled else val

    def parseFloatScaled(self, str):
        """
        Parses string in scaled format of gerber_data file. Performs variable substitution if needed.
        :param str: string to parse
        :return: scaled float value
        """
        if str.find('$') != -1:
            return self.parseEvalExpression(str)
        else:
            return float(str) * self.fscl

    def store_to_gd(self):
        # Stores the existing set of layer data as polygonal data points
        # This is the equivalent of rasterisation of the draw commands
        # Expand tracks from centrelines based on aperture
        track_outlines = []
        tracks = self.tracks
        apertures = self.apertures
        tracksize = self.tracksize

        for ii in range(len(self.tracks)):
            tmp = tracks[ii]
            prev = tmp[-1]
            for jj in range(len(tmp) - 2, -1, -1):
                if tmp[jj] == prev:
                    del tmp[jj]
                else:
                    prev = tmp[jj]

        for seg in range(len(tracks)):
            aperture = apertures[tracksize[seg]]
            itr = iter(tracks[seg])
            start = next(itr)
            for end in itr:
                singletrack = pyclipper.MinkowskiSum(aperture, [start, end], -1)
                if len(singletrack) > 1:
                    biggest = []
                    myarea = 0
                    for mypath in singletrack:
                        newarea = pyclipper.Area(mypath)
                        if newarea > myarea:
                            biggest = mypath
                            myarea = newarea
                    singletrack = [[]]
                    singletrack[0] = biggest
                track_outlines.extend(singletrack)
                start = end

        mergedBounds = union_boundary(track_outlines + self.pads, self.regions)
        self.pads = union(self.pads)
        track_outlines = union(track_outlines)
        closeOffPolys(self.pads)
        closeOffPolys(track_outlines)
        closeOffPolys(mergedBounds)

        self.trackData.extend(self.tracks)

        # Store data into layers.
        prefix = str(self.layerSet)
        self.layerSet += 1

        # # Option 1: Discard empty layers
        # if len(track_outlines) != 0: self.gd.layers.append(GerberLayer(self.isDark, prefix + "_Tracks", track_outlines, type=GerberLayer.TYPE_TRACK))
        # if len(self.regions) != 0: self.gd.layers.append(GerberLayer(self.isDark, prefix + "_Regions", self.regions, type=GerberLayer.TYPE_REGION))
        # if len(self.pads) != 0: self.gd.layers.append(GerberLayer(self.isDark, prefix + "_Pads", self.pads, type=GerberLayer.TYPE_PAD, color="#009000"))
        # if len(mergedBounds) != 0: self.gd.layers.append(GerberLayer(self.isDark, prefix + "_Boundaries", mergedBounds, False, False, "blue", GerberLayer.TYPE_BOUNDARY))

        # Option 2: Retain layers even if empty
        self.gd.layers.append(GerberLayer(self.isDark, prefix + "_Tracks", track_outlines, type=GerberLayer.TYPE_TRACK))
        self.gd.layers.append(GerberLayer(self.isDark, prefix + "_Regions", self.regions, type=GerberLayer.TYPE_REGION))
        self.gd.layers.append(GerberLayer(self.isDark, prefix + "_Pads", self.pads, type=GerberLayer.TYPE_PAD, color="#009000"))
        self.gd.layers.append(GerberLayer(self.isDark, prefix + "_Boundaries", mergedBounds, False, False, "blue", GerberLayer.TYPE_BOUNDARY))

        # clear cache
        self.regions = []
        self.pads = []
        self.tracks = []
        self.tracksize = []
        self.trackseg = -1
        self.padseg = -1
        self.regionseg = -1

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

    def getMaxArcLength(self):
        maxLenScalar = MAX_ARC_LENGTH * self.fscl
        if self.gd.units == 1: maxLenScalar /= 25.4
        return int(maxLenScalar)

    def add_circle(self, ptlist, diameter, isCW=True):
        steps = max(int(diameter/(2*self.getMaxArcLength())), MIN_SEG_PER_360) + 1
        angleStep = 2.0 * math.pi / (steps - 1) * (-1 if isCW else 1)
        # print "  Circle: # of segs = ", steps, "dia", diameter
        for i in range(steps):
            angle = i*angleStep
            x = (diameter / 2.0) * math.cos(angle)
            y = (diameter / 2.0) * math.sin(angle)
            ptlist.append([x, y])

    def add_arc2(self, ptlist, centreX, centreY, startX, startY, endX, endY, isCW=True):
        startX -= centreX
        startY -= centreY
        endX -= centreX
        endY -= centreY
        r1 = math.sqrt(startX**2 + startY**2)
        dr = math.sqrt(endX**2 + endY**2) - r1

        startAngle = math.atan2(startY, startX)
        deltaAngle = math.atan2(endY, endX) - startAngle

        if deltaAngle < 0: deltaAngle += 2*math.pi  # make it positive
        if isCW == (deltaAngle > 0):  # requires outer arc
            deltaAngle -= 2*math.pi

        self.add_arc3(ptlist, centreX, centreY, r1, startAngle, deltaAngle, dr)

    def add_arc3(self, ptlist, centreX, centreY, r, startAngle, deltaAngle, dr=0.0):
        # steps is chosen such that minimum arc segments (overall and fraction) are held.
        # More steps are added if arc length will be larger than MAX_ARC_LENGTH
        steps = max(MIN_SEG, int(abs(deltaAngle)*max(max(r, r+dr)/self.getMaxArcLength(),
                                                     MIN_SEG_PER_360/(2*math.pi)))) + 1
        dr /= (steps - 1)
        deltaAngle /= (steps - 1)

        # print "  ARC: ", centreX, ",", centreY, "  angle: ", (180*startAngle/(2*math.pi)), \
        #     " deltaAngle: ", (180*deltaAngle/(2*math.pi)), " r ", r, ", ", "  steps ", steps
        # print "arc length ", r*deltaAngle/self.fscl, "  steps ", steps, "  angle ", deltaAngle*180/(2*math.pi)

        for i in range(steps):
            xarcseg = centreX + (r + i*dr)*math.cos(startAngle + i*deltaAngle)
            yarcseg = centreY + (r + i*dr)*math.sin(startAngle + i*deltaAngle)
            ptlist.append([xarcseg, yarcseg])

    def assignVariables(self, s):
        ss = s.split('X')
        for i in range(len(ss)):
            self.vars['$' + str(i + 1)] = float(ss[i]) * self.fscl
        # for i in self.vars: print "assign", i, self.vars[i]

    def parseAssignExpression(self, s):
        pos = s.find('=')
        self.vars[s[:pos]] = self.parseEvalExpression(s[pos+1:])
        # print "set", s[:pos], self.vars[s[:pos]]
        pass

    def parseEvalExpression(self, s):
        """
        :type s: str
        """
        pos = 0
        slen = len(s)
        ns = ""
        while pos < slen:
            tmp = s[pos]
            if tmp == '$':
                # Replace with variable value - variable names consists of $ symbol followed by digits
                varlen = 1
                while pos + varlen < slen and s[pos+varlen].isdigit(): varlen += 1
                # print 'var', s[pos:pos + varlen]
                ns += str(self.vars.get(s[pos:pos + varlen], 0))
                pos += varlen
            elif tmp == 'x':
                # Use multiplication symbol '*' not 'x'
                ns += '*'
                pos += 1
            elif tmp == '-' or tmp == '+' or tmp == '/' or tmp == '(' or tmp == ')' or \
                            tmp == '.' or tmp.isdigit():
                ns += s[pos]
                pos += 1
            else:
                # We filter out invalid characters to prevent user from inputting in bad text that
                # could crash python
                self.error("Expression contains invalid characters '" + tmp + "' from string: " + s)
                return 0

        return eval(ns)


def union(paths, union_type=pyclipper.PFT_NONZERO):
    # performs union on list, or list of lists
    if len(paths) != 0:
        c = pyclipper.Pyclipper()
        c.AddPaths(paths, pyclipper.PT_SUBJECT, True)
        paths = c.Execute(pyclipper.CT_UNION, union_type, union_type)
        c.Clear()
    return paths
    # return pyclipper.SimplifyPolygons(paths, union_type)


def union_boundary(boundarys, regions):
    # union intersecting polygons on boundary

    if boundarys:
        boundary = union(boundarys, pyclipper.PFT_NONZERO)
        paths = boundary
    else:
        boundary = []
        paths = []

    if regions != []:
        region = union(regions, pyclipper.PFT_NONZERO)
        paths.extend(region)
        boundary = union(paths, pyclipper.PFT_NONZERO)

    if boundary:
        boundary = pyclipper.CleanPolygons(boundary)
        # boundary = pyclipper.SimplifyPolygons(boundary)
        # for segs in boundary:  # commented out as this should never occur
        #     if len(segs) == 0:
        #         boundary.remove([])
        #         break

    return boundary


def closeOffPolys(paths):
    for i in range(len(paths)-1, -1, -1):  # iterate backwards as we're modifying the list in situ
        tmp = paths[i]
        if len(tmp) == 0:
            # remove empty lists
            del paths[i]
            # pass
        else:
            # close off the polygon
            tmp.append(tmp[0])


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
                    # the specifications for single quadrant mode is barbaric in that it is very difficult to
                    # implement consistently and yet they spout how inherently unstable multi quadrant mode is.
                    # Single quadrant mode is less stable because there are multiple solutions depending on where
                    # the centre is located because we're meant to pick the signs such that:
                    # - CW/CCW mode is respected and that
                    # - 0<arcAngle<90 degrees is maintained
                    # It is possible for multiple combination of signs to meet the conditions above

                    # We'll actually keep the signs. Use them as defaults.
                    # I.e. if conditions aren't met, we twiddle signs such that they do
                    # # discard sign data when it should really be used...
                    # if pd.i < 0:
                    #     pd.warn("Negative sign for offset i was ignored for SINGLE QUADRANT mode")
                    #     pd.i *= -1
                    # if pd.j < 0:
                    #     pd.warn("Negative sign for offset j was ignored for SINGLE QUADRANT mode")
                    #     pd.j *= -1

                    # brute force try the signs (4 possible cases forming a rectangle of width 2i and
                    # height of 2j around the starting point) to see which one fulfils all the condition
                    sbreak = False
                    for m in range(2):
                        centreX = pd.xold + pd.i*(1 if m == 0 else -1)
                        for n in range(2):
                            centreY = pd.yold + pd.j*(1 if n == 0 else -1)
                            startAngle = math.atan2(pd.yold - centreY, pd.xold - centreX)
                            deltaAngle = math.atan2(pd.y - centreY, pd.x - centreX) - startAngle
                            if deltaAngle > math.pi:
                                deltaAngle = 2*math.pi - deltaAngle
                            elif deltaAngle < -math.pi:
                                deltaAngle += 2*math.pi
                            r = math.sqrt((pd.xold - centreX)**2 + (pd.yold - centreY)**2)
                            dr = math.sqrt((pd.x - centreX)**2 + (pd.y - centreY)**2) - r
                            if abs(deltaAngle) < math.pi/1.95:
                                if (pd.interpMode == 2) == (deltaAngle < 0):  # correct CW/CCW mode
                                    pd.add_arc3(pd.regions[pd.regionseg] if pd.regionMode else pd.tracks[pd.trackseg],
                                             centreX, centreY, r, startAngle, deltaAngle, dr)
                                    sbreak = True
                                    break
                        if sbreak: break
                    if not sbreak:
                        pd.error("Single quadrant arc coordinates do not specify a valid arc configuration")
                else:  # Multi Quadrant Mode
                    # Implementation note:
                    # Draws a circle that passes through the start and end point with radius of distance
                    # from offset centre point to start point (i.e. the offset centre point will
                    # be moved such that the distance to the and end point become equal to the distance
                    # to the start point)
                    # r = pow(pd.i, 2) + pow(pd.j, 2)

                    # The line that perpendicular bisects the line joining A (start) and B (end) is where
                    # the centre point will lie. The distance from centre point to A and B is r (circle radius)
                    # The distance from the line connecting AB to centre point is thus sqrt(r^2-L^2)
                    # Where L is the distance between midpoint and A or B.
                    # To optimise, square root is not taken until the end and 2L is distance between A and B
                    # and is the value that the normal must be divided by to normalise to length 1

                    pd.add_arc2(pd.regions[pd.regionseg] if pd.regionMode else pd.tracks[pd.trackseg],
                             pd.xold + pd.i, pd.yold + pd.j,
                             pd.xold, pd.yold, pd.x, pd.y, pd.interpMode == 2)

                    # # Mid Point - OLD METHOD
                    # mx = (pd.xold + pd.x)/2
                    # my = (pd.yold + pd.y)/2
                    # # Normal
                    # ny = pd.x - pd.xold
                    # nx = pd.yold - pd.y
                    # tmp = nx*nx + ny*ny  # size of vector squared
                    # tmp = math.sqrt(float(r)/tmp - 0.25)  # normalise normal and scale by radius
                    # if abs(pd.i - nx*tmp) + abs(pd.j - ny*tmp) > abs(pd.i + nx*tmp) + abs(pd.j + ny*tmp):
                    #     # pick the side the offset point lies on
                    #     tmp *= -1
                    # centreX = mx + nx*tmp
                    # centreY = my + ny*tmp
                    # add_arc(pd.regions[pd.regionseg] if pd.regionMode else pd.tracks[pd.trackseg],
                    #            math.sqrt(r), centreX, centreY,
                    #            math.atan2(pd.yold - centreY, pd.xold - centreX),
                    #            math.atan2(pd.y - centreY, pd.x - centreX), pd.interpMode == 2)
                # Consume offset
                pd.i = 0
                pd.j = 0
            elif cd == 2:  # move
                if pd.regionMode:  # Finish current region and creates a new one
                    pd.regions.append([])
                    pd.regionseg += 1
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
                # print " Comment G04: ", pd.parseUntil('*')  # prints comment to console
                pd.parseUntil('*')  # does not print comment to console
            elif cd == 36:  # Region mode ON
                pd.regionMode = True
            elif cd == 37:  # Region mode OFF
                pd.regionMode = False
            elif cd == 54:
                if pd.getChar() != 'D':
                    pd.error("Command G54 wasn't followed by valid aperture Dnn. This command is also "
                             "deprecated and should be removed")
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
                if pd.pos < pd.strlen:
                    if pd.pos + 30 < pd.strlen:
                        pd.warn("Unparsed data: " + pd.str[pd.pos:pd.pos+30] + "...")
                    else:
                        pd.warn("Unparsed data: " + pd.str[pd.pos:])
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
            pd.pos += 3
            if cmd == "FS":  # File format
                op = string.find(pd.str,'X',pd.pos)
                # Removed a lot of the checks to increase robustness.
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
                pd.fscl = 10 ** pd.gd.fraction
                pd.parseUntil('*')
            elif cmd == "MO":  # Set unit
                tmp = pd.str[pd.pos]
                if tmp == 'M':
                    pd.pos += 2  # skip over MM
                    # if pd.findNextChar() != 'M':
                    #     pd.error("Unit sepcified invalid. It was set to MM")
                    # else:
                    #     pd.findNextChar()
                    pd.gd.units = 0
                elif tmp == 'I':
                    pd.pos += 2  # skip over IN
                    # if pd.findNextChar() != 'N':
                    #     pd.error("Unit sepcified invalid. It was set to INCH")
                    # else:
                    #     pd.findNextChar()
                    pd.gd.units = 1
                else:
                    pd.error_line("Invalid unit specifier " + pd.parseUntil('*'))
            elif cmd == "AD":  # Add aperture
                # IMPORTANT: All apertures must be in the CCW or POSITIVE direction
                if pd.str[pd.pos] != 'D':
                    pd.error("Aperture index must be specified after AD command")
                    continue
                pd.pos += 1
                pd.aperture = pd.parseInt()
                while len(pd.apertures) <= pd.aperture:
                    pd.apertures.append([])
                if len(pd.apertures[pd.aperture]) != 0:
                    pd.warn("Aperture " + str(pd.aperture) + " is added more than once. The existing aperture "
                                                             "has been overwritten")
                    pd.apertures[pd.aperture] = []
                holesize = -1
                if pd.str[pd.pos + 1] == ',':  # single letter macro names are treated as built in apertures
                    tmp = pd.str[pd.pos]
                    pd.pos += 2
                    if tmp == 'C':  # Circle
                        size = pd.parseFloat()
                        pd.add_circle(pd.apertures[pd.aperture], size, False)
                        if pd.getChar() == 'X':
                            pd.pos += 1
                            holesize = pd.parseFloat()
                            pd.add_circle(pd.apertures[pd.aperture], holesize, True)
                        print "   read aperture", pd.aperture, ": circle diameter", size, ", hole size", holesize
                    elif tmp == 'R':  # Rectangle
                        w = pd.parseFloat() / 2.0
                        pd.check_char('X')
                        h = pd.parseFloat() / 2.0
                        pd.apertures[pd.aperture].extend([[-w, -h], [w, -h], [w, h], [-w, h], [-w, -h]])
                        if pd.getChar() == 'X':
                            pd.pos += 1
                            holesize = pd.parseFloat()
                            pd.add_circle(pd.apertures[pd.aperture], holesize, True)
                        print "   read aperture", pd.aperture, ": rectangle W", w, ", H", h, ", hole size", holesize
                    elif tmp == 'O':  # Rectangle capped with semicircles
                        w = pd.parseFloat() / 2.0
                        pd.check_char('X')
                        h = pd.parseFloat() / 2.0

                        if w > h:  # round the top and bottom sides
                            pd.add_arc3(pd.apertures[pd.aperture],  w - h, 0, h, -math.pi/2, math.pi)
                            pd.add_arc3(pd.apertures[pd.aperture], -w + h, 0, h,  math.pi/2, math.pi)
                            pd.apertures[pd.aperture].append([w - h, -h])
                        else:  # round the left and right sides
                            pd.add_arc3(pd.apertures[pd.aperture], 0,  h - w, w,       0, math.pi)
                            pd.add_arc3(pd.apertures[pd.aperture], 0, -h + w, w, math.pi, math.pi)
                            pd.apertures[pd.aperture].append([w, h - w])

                        if pd.getChar() == 'X':
                            pd.pos += 1
                            holesize = pd.parseFloat()
                            pd.add_circle(pd.apertures[pd.aperture], holesize, True)
                        print "   read aperture", pd.aperture, ": o-rectangle ", w, " x ", h, ", hole size", holesize
                    elif tmp == 'P':  # Regular polygon
                        size = pd.parseFloat() / 2.0
                        pd.check_char('X')
                        n = pd.parseInt()
                        rot = 0
                        if pd.getChar() == 'X':
                            pd.pos += 1
                            rot = pd.parseFloat(False)
                        for i in range(n):
                            angle = i * -2.0 * math.pi / (n - 1.0)
                            x = size * math.cos(angle + rot)
                            y = size * math.sin(angle + rot)
                            pd.apertures[pd.aperture].append([x, y])

                        if pd.getChar() == 'X':
                            pd.pos += 1
                            holesize = pd.parseFloat()
                            pd.add_circle(pd.apertures[pd.aperture], holesize, True)
                        print "   read aperture", pd.aperture, ": polygon n", n, " diameter ", size, ", rot ", rot, \
                            " hole size", holesize
                    else:
                        pd.error("Unknown aperture shape " + tmp)
                else:  # Macro
                    tmp = pd.parseUntil('*')
                    colpos = tmp.find(',')
                    if colpos == -1:
                        mindex = pd.macrosName.index(tmp)
                        print "   read aperture", pd.aperture, ", name = ",tmp," (", mindex, "), params=nil"
                    else:
                        mindex = pd.macrosName.index(tmp[:colpos])
                        pd.assignVariables(tmp[colpos+1:])
                        print "   read aperture", pd.aperture, ", name = ",tmp[:colpos]," (", mindex, "), params=",tmp[colpos+1:]

                    for line in pd.macros[mindex]:
                        if line[0] == '$':
                            # variable set
                            pd.parseAssignExpression(line)
                            continue
                        elif line[0] == '0':
                            # macro comment - ignore
                            continue

                        vals = line.split(',')
                        prim = int(vals[0])
                        if prim == 1:  # circle primitive specified using start and end point
                            isAdd = vals[1] == "1"
                            if not isAdd and len(pd.apertures[pd.aperture]) == 0: continue  # subtracting from nothing

                            tmp = []
                            rot = 0 if len(vals) < 6 else float(vals[5])
                            r = pd.parseFloatScaled(vals[2]) / 2.0
                            centreX = pd.parseFloatScaled(vals[3])
                            centreY = pd.parseFloatScaled(vals[4])
                            if rot != 0: centreX, centreY = rotPoint([centreX, centreY], rot)
                            pd.add_arc3(tmp, centreX, centreY, r, 0, math.pi*2)
                            mergePolys(pd.apertures[pd.aperture], tmp, isAdd)
                        elif prim == 20:  # line primitive - start and end point
                            isAdd = vals[1] == "1"
                            if not isAdd and len(pd.apertures[pd.aperture]) == 0: continue  # subtracting from nothing
                            w = pd.parseFloatScaled(vals[2])
                            x1 = pd.parseFloatScaled(vals[3])
                            y1 = pd.parseFloatScaled(vals[4])
                            x2 = pd.parseFloatScaled(vals[5])
                            y2 = pd.parseFloatScaled(vals[6])
                            rot = float(vals[7])
                            dx = x2 - x1
                            dy = y2 - y1
                            mag = w / math.sqrt(dx*dx + dy*dy) / 2.0
                            dx *= mag
                            dy *= mag
                            tmp = [[x1 + dy, y1 - dx], [x2 + dy, y2 - dx], [x2 - dy, y2 + dx], [x1 - dy, y1 + dx]]
                            if rot != 0: rotPoints(tmp, rot)
                            tmp.append(tmp[0])
                            mergePolys(pd.apertures[pd.aperture], tmp, isAdd)
                        elif prim == 21:  # line primitive - centre, w and h
                            isAdd = vals[1] == "1"
                            if not isAdd and len(pd.apertures[pd.aperture]) == 0: continue  # subtracting from nothing
                            w = pd.parseFloatScaled(vals[2]) / 2.0
                            h = pd.parseFloatScaled(vals[3]) / 2.0
                            centreX = pd.parseFloatScaled(vals[4])
                            centreY = pd.parseFloatScaled(vals[5])
                            rot = float(vals[6])
                            tmp = [[centreX + w, centreY + h], [centreX - w, centreY + h],
                                   [centreX - w, centreY - h], [centreX + w, centreY - h]]
                            if rot != 0: rotPoints(tmp, rot)
                            tmp.append(tmp[0])  # close off polygon
                            mergePolys(pd.apertures[pd.aperture], tmp, isAdd)
                        elif prim == 22:  # line primitive - bottom left, w and h
                            # This primitive isn't explicitly explained in gerber specs but reversed engineered
                            # from the examples.
                            isAdd = vals[1] == "1"
                            if not isAdd and len(pd.apertures[pd.aperture]) == 0: continue  # subtracting from nothing
                            w = pd.parseFloatScaled(vals[2])
                            h = pd.parseFloatScaled(vals[3])
                            tx = pd.parseFloatScaled(vals[4])
                            ty = pd.parseFloatScaled(vals[5])
                            rot = float(vals[6])
                            tmp = [[tx + w, ty + h], [tx, ty + h], [tx, ty], [tx + w, ty]]
                            if rot != 0: rotPoints(tmp, rot)
                            tmp.append(tmp[0])  # close off polygon
                            mergePolys(pd.apertures[pd.aperture], tmp, isAdd)
                        elif prim == 4:  # outline primitive
                            isAdd = vals[1] == "1"
                            if not isAdd and len(pd.apertures[pd.aperture]) == 0: continue  # subtracting from nothing
                            n = int(vals[2])
                            rot = float(vals[-1])
                            if len(vals) != (n+1)*2 + 4 and len(vals) != (n+1)*2 + 3:
                                pd.error("Invalid number of arguments in polygon primitive.")
                            else:
                                tmp = [[pd.parseFloatScaled(vals[3]), pd.parseFloatScaled(vals[4])]]
                                for x in (range(1, n)):
                                    tmp.append([pd.parseFloatScaled(vals[x*2 + 3]), pd.parseFloatScaled(vals[x*2 + 4])])

                                # We require all aperture polygons to be CCW. Since outline is a user supplied
                                # value, the data may not conform to this so we need to reverse the list if
                                # the data is supplied in CW direction.
                                if not pyclipper.Orientation(tmp): tmp.reverse()

                                # Note: we ignore the last point if n+1 points was specified. The last point is
                                # redundant as it just loops back to start and we add the closing point regardless
                                # of whether it was provided or not. It also ensures that if the supplied data does
                                # not conform with specifications, it is effectively fixed silently.
                                if rot != 0: rotPoints(tmp, rot)
                                tmp.append(tmp[0])  # close off polygon
                                mergePolys(pd.apertures[pd.aperture], tmp, isAdd)
                        elif prim == 5:  # polygon primitive
                            isAdd = vals[1] == "1"
                            if not isAdd and len(pd.apertures[pd.aperture]) == 0: continue  # subtracting from nothing
                            n = int(vals[2])
                            centreX = pd.parseFloatScaled(vals[3])
                            centreY = pd.parseFloatScaled(vals[4])
                            r = pd.parseFloatScaled(vals[5]) / 2.0
                            rot = float(vals[6])
                            if rot != 0 and (centreX != 0 or centreY != 0):
                                pd.warn("Rotation can only be used on polygon primitive if it is centred at (0,0). "
                                        "The rotation was applied as if the polygon was rotated first and then "
                                        "translated to specified centre coordinates")

                            tmp = []
                            stepAngle = -2.0 * math.pi / (n - 1.0)
                            for i in range(n):
                                angle = i*stepAngle
                                x = r * math.cos(angle + rot) + centreX
                                y = r * math.sin(angle + rot) + centreY
                                tmp.append([x, y])
                            mergePolys(pd.apertures[pd.aperture], tmp, isAdd)
                        elif prim == 6:  # moire primitive
                            pd.error("Moire primitive is not implemented yet")
                            continue
                        elif prim == 7:  # thermal primitive
                            pd.error("Thermal primitive is not implemented yet")
                            continue
                        else:
                            pd.error("Unknown macro primitive: " + str(prim))
                            continue
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
                # Close and apply step and repeat block (if any)


                if pd.getChar() != '*':
                    # Start step and repeat block
                    xrep = int(pd.parseUntil('Y'))
                    yrep = int(pd.parseUntil('I'))
                    xinc = float(pd.parseUntil('J'))
                    yinc = float(pd.parseUntil('*'))
                pd.error("Step repeat not yet implemented")
                pass
            elif cmd == "LP":  # Create new layer
                tmp = pd.getChar()
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
        else:
            pd.error("Unknown command code " + tmp + ". Rest of file was not parsed")
            break
    print "Execution time: ", (time.time() - stt)
    # Finalise parsing
    pd.store_to_gd()
    print " Parsing completed with ", pd.warnings, " warnings, ", pd.deps, " deprecated commands and ", pd.errors, " errors"
    return [pd.gd, pd.trackData]

def replace_holes_with_seams(paths):
    """
    Removes holes and merge isolated polygons into one by adding seams
    The input is a list of polygons, the output is a list of polygon with only one polygon
    I.e. output is list[1][?][2]
    """
    # st_time = time.time()
    if len(paths) == 0: return paths
    tmppath = list(paths[0])
    for seg in range(1,len(paths)):
        if len(paths[seg]) == 0: continue
        # Add a seam to remove the hole
        # Ideally, we only do this if polygon is inside another polygon
        # Testing for this is probably expensive so we'll cheat and add a
        # seam from every polygon to another polygon.

        # # Ideally, we should use the closest available point but execution
        # # is marginally slower and visually when filled, the result are the same
        # #  Use Manhattan distance because squaring adds neg improvements
        # tmpx = paths[seg][0][0]
        # tmpy = paths[seg][0][1]
        # closest_i = 0
        # closest_d = abs(tmpx - tmppath[0][0]) + abs(tmpy - tmppath[0][1])
        # for vert in range(1,len(tmppath)):
        #     d = abs(tmpx - tmppath[vert][0]) + abs(tmpy - tmppath[vert][1])
        #     if d < closest_d:
        #         closest_d = d
        #         closest_i = vert
        # insPoint = closest_i # len(tmppath)
        # tmp = list(paths[seg]) # the hole data
        # tmp.append(tmp[0]) # Close the hole
        # tmp.append(tmppath[insPoint - 1]) # Join back onto insert point
        # tmppath[insPoint:insPoint] = tmp # Insert the hole data

        tmp = tmppath[-1]
        tmppath.extend(list(paths[seg])) # use of list() is to copy data and leave old one intact
        tmppath.append(paths[seg][0])
        tmppath.append(tmp)

    # print "ex time ",(time.time() - st_time)
    return [tmppath]


def mergePolys(poly1, poly2, isAdd=True):
    """
    Add poly2 into poly1. Note that the polygons must be single (i.e. must be a single sequence
    of points. If the polygon are composed of isolated regions and/or holes, you must convert them to
    one polygon by adding seams. replace_holes_with_seams(paths)[0] will do this for you.
    IMPORTANT: The results are stored in poly1, nothing is returned by this function
    :param poly1: list of [x,y] points, i.e. list[?][2]
    :param poly2: list of [x,y] points, i.e. list[?][2]
    :param isAdd: true ot merge, false to subtract poly2 from poly1
    """
    if isAdd:
        if len(poly1) == 0:
            poly1.extend(poly2)
        else:
            tmp = poly1[-1]
            poly1.extend(poly2)
            poly1.append(tmp)  # return to end position
    else:
        c = pyclipper.Pyclipper()
        c.AddPaths([poly1], pyclipper.PT_SUBJECT)
        c.AddPaths([poly2], pyclipper.PT_CLIP)
        result = c.Execute(pyclipper.CT_DIFFERENCE, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
        c.Clear()
        result = replace_holes_with_seams(result)[0]  # convert to one polygon
        result.append(result[0])  # close off polygon

        # store result in list1 without changing reference
        del poly1[:]  # clear list
        poly1.extend(result)  # add the merged results


def rotPoint(pt, rot):
    """
    Rotate a point about origin and stores the results IN PLACE (i.e. if you need the original
    point unmodified, wrap pt with list)
    :param pt: [x,y] pair
    :param rot: angle of rotation in DEGREES
    :return: pt supplied with updated coorindates
    """
    rot *= math.pi/180  # convert to radians
    tsin = math.sin(rot)
    tcos = math.cos(rot)
    cx = pt[0]*tcos - pt[1]*tsin
    pt[1] = pt[0]*tsin + pt[1]*tcos
    pt[0] = cx  # we can't calculate this in place because we need x,y intact
    return pt

def rotPoints(pts, rot):
    """
    Rotate points about origin and stores the results IN PLACE
    You'll need to deep copy the array for this operation if you
    need the original list unmodified.
    :param pts: list of [x,y] points (list[?][2])
    :param rot: angle of rotation in DEGREES
    """
    rot *= math.pi/180  # convert to radians
    tsin = math.sin(rot)
    tcos = math.cos(rot)
    for pt in pts:
        cx = pt[0]*tcos - pt[1]*tsin
        pt[1] = pt[0]*tsin + pt[1]*tcos
        pt[0] = cx  # we can't calculate this in place because we need x,y intact
