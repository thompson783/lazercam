import copy
from string import find
from Tkinter import re
import math
import string
import pyclipper
import time

__author__ = 'Damien, Ben, Thompson'

SIZE = 1
# EPS = 10

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

    units = 0  # 0 is mm, 1 is in
    digits = 0
    fraction = 0

    """
    List of GerberLayer objects
    :type layers: list[GerberLayer]
    """
    layers = []

    # Mode assumed to be absolute



def load_file(filename):
    # Load Gerber from file
    file = open(filename, 'r')
    str = file.read().splitlines()
    file.close()

    return parse_gerber(str)


def parse_gerber(str):
    """
    Parse string data loaded from Gerber file
    :type str: string
    :rtype: [GerberData,list]
    """
    stt = time.time()

    gerber_data = GerberData()

    nlines = len(str)
    trackseg = -1
    padseg = -1
    regionseg = -1
    # edgeseg = -1
    xold = []
    yold = []
    line = 0
    tracksize = []
    # pcb_edge = []
    macros = []
    N_macros = 0
    apertures = [[] for i in range(1000)]
    appsize = [[] for i in range(1000)]
    interpMode = 1
    arcMode = 0
    regionMode = False

    nverts = 16  # TODO: changed to fixed arc length

    tracks = []
    regions = []
    pads = []

    isDark = True

    while line < nlines:
        if len(str[line]) == 0: continue
        if (find(str[line], "%FS") != -1):
            #
            # format statement
            #
            index = find(str[line], "X")
            gerber_data.digits = int(str[line][index + 1])
            gerber_data.fraction = int(str[line][index + 2])
            line += 1
            continue
        elif (find(str[line], "%AM") != -1):
            #
            # aperture macro
            #
            index = find(str[line], "%AM")
            index1 = find(str[line], "*")
            macros.append([])
            macros[-1] = str[line][index + 3:index1]
            N_macros += 1
            line += 1
            continue
        elif (find(str[line], "%MOMM*%") != -1):
            #
            # mm
            #
            gerber_data.units = 0
            line += 1
            continue
        elif (find(str[line], "%MOIN*%") != -1):
            #
            # inches
            #
            gerber_data.units = 1
            line += 1
            continue
        elif (find(str[line], "%LPD*%") != -1):
            #
            # New layer - DARK
            #

            print 'New layer - DARK'
            store_to_gd(gerber_data, tracks, pads, regions, apertures, tracksize, isDark)
            isDark = True
            regions = []
            pads = []
            tracks = []
            tracksize = []
            trackseg = -1
            padseg = -1
            regionseg = -1
            line += 1
            continue
        elif (find(str[line], "%LPC*%") != -1):
            #
            # New layer - CLEAR
            #

            print 'New layer - CLEAR'
            store_to_gd(gerber_data, tracks, pads, regions, apertures, tracksize, isDark)
            isDark = False
            regions = []
            pads = []
            tracks = []
            tracksize = []
            trackseg = -1
            padseg = -1
            regionseg = -1
            line += 1
            continue
        elif (find(str[line], "G01*") != -1):
            #
            # linear interpolation
            #
            interpMode = 1
            line += 1
            continue
        elif (find(str[line], "G02*") != -1):
            #
            # Set clockwise circular interpolation
            #
            interpMode = 2
            line += 1
            continue
        elif (find(str[line], "G03*") != -1):
            #
            # Set counterclockwise circular interpolation
            #
            interpMode = 3
            line += 1
            continue
        elif (find(str[line], "G04") != -1):
            #
            # Set counterclockwise circular interpolation
            #
            print "   Comment: ", str[line]
            line += 1
            continue
        elif (find(str[line], "G70*") != -1):
            #
            # set unit to inches - deprecated command
            #
            print "   Deprecated command found: G70 (command was parsed but should be removed)"
            gerber_data.units = 1
            line += 1
            continue
        elif (find(str[line], "G71*") != -1):
            #
            # set unit to mm - deprecated command
            #
            print "   Deprecated command found: G71 (command was parsed but should be removed)"
            gerber_data.units = 0
            line += 1
            continue
        elif (find(str[line], "G74*") != -1):
            #
            # Set single quadrant circular interpolation
            #
            arcMode = 1
            line += 1
            continue
        elif (find(str[line], "G75*") != -1):
            #
            # Set multi quadrant circular interpolation
            #
            arcMode = 2
            line += 1
            continue
        elif (find(str[line], "G90*") != -1):
            #
            # set absolute coordinate format - deprecated command
            #
            print "   G90 command ignored (deprecated)"
            line += 1
            continue
        elif (find(str[line], "G91*") != -1):
            #
            # set incremental coordinate format - deprecated command
            #
            print "   G91 command ignored (deprecated)"
            line += 1
            continue
        elif (find(str[line], "%ADD") != -1):
            #
            # aperture definition
            #
            index = find(str[line], "%ADD")
            parse = 0
            if (find(str[line], "C,") != -1):
                #
                # circle
                #
                vals = read_float_args_btw(str[line],"C,","*")
                aperture = int(str[line][index+4:find(str[line], "C,", index+4)])
                size = vals[0] * (10 ** (gerber_data.fraction))
                appsize[aperture] = size
                for i in range(nverts):
                    angle = i * 2.0 * math.pi / (nverts - 1.0)
                    x = (size / 2.0) * math.cos(angle)
                    y = (size / 2.0) * math.sin(angle)
                    apertures[aperture].append([x, y])
                if len(vals) == 2:
                    holesize = vals[1] * (10 ** (gerber_data.fraction))
                    add_hole(apertures[aperture], holesize, nverts)
                else:
                    holesize = -1
                print "   read aperture", aperture, ": circle diameter", size, ", hole size", holesize
                line += 1
                continue

            elif (find(str[line], "O,") != -1):
                #
                # obround
                #
                index = find(str[line], "O,")
                aperture = int(str[line][4:index])
                index1 = find(str[line], ",", index)
                index2 = find(str[line], "X", index)
                index3 = find(str[line], "*", index)
                width = float(str[line][index1 + 1:index2]) * (10 ** (gerber_data.fraction))
                height = float(str[line][index2 + 1:index3]) * (10 ** (gerber_data.fraction))

                if (width > height):
                    for i in range(nverts / 2):
                        angle = i * math.pi / (nverts / 2 - 1.0) + math.pi / 2.0
                        x = -(width - height) / 2.0 + (height / 2.0) * math.cos(angle)
                        y = (height / 2.0) * math.sin(angle)
                        apertures[aperture].append([x, y])
                    for i in range(nverts / 2):
                        angle = i * math.pi / (nverts / 2 - 1.0) - math.pi / 2.0
                        x = (width - height) / 2.0 + (height / 2.0) * math.cos(angle)
                        y = (height / 2.0) * math.sin(angle)
                        apertures[aperture].append([x, y])
                else:
                    for i in range(nverts / 2):
                        angle = i * math.pi / (nverts / 2 - 1.0) + math.pi
                        x = (width / 2.0) * math.cos(angle)
                        y = -(height - width) / 2.0 + (width / 2.0) * math.sin(angle)
                        apertures[aperture].append([x, y])
                    for i in range(nverts / 2):
                        angle = i * math.pi / (nverts / 2 - 1.0)
                        x = (width / 2.0) * math.cos(angle)
                        y = (height - width) / 2.0 + (width / 2.0) * math.sin(angle)
                        apertures[aperture].append([x, y])

                print "   read aperture", aperture, ": obround", width, "x", height
                line += 1
                continue

            elif (find(str[line], "R,") != -1):
                #
                # rectangle
                #

                index = find(str[line], "R,")
                aperture = int(str[line][4:index])
                index1 = find(str[line], ",", index)
                index2 = find(str[line], "X", index)
                index3 = find(str[line], "*", index)

                width = float(str[line][index1 + 1:index2]) * (10 ** (gerber_data.fraction)) / 2.0
                height = float(str[line][index2 + 1:index3]) * (10 ** (gerber_data.fraction)) / 2.0

                apertures[aperture].append([-width, -height])
                apertures[aperture].append([+width, -height])
                apertures[aperture].append([+width, +height])
                apertures[aperture].append([-width, +height])
                apertures[aperture].append([-width, -height])

                print "   read aperture", aperture, ": rectangle", width, "x", height
                line += 1
                continue
            elif (find(str[line], "P,") != -1):
                #
                # Regular polygon
                #
                # print "   read aperture", aperture, ": reg polygon", width, "x", height
                print "   ERROR: polygon not supported"
                line += 1
                continue



            for macro in range(N_macros):
                #
                # macros
                #
                index = find(str[line], macros[macro] + ',')
                if (index != -1):
                    #
                    # hack: assume macros can be approximated by
                    # a circle, and has a size parameter
                    #
                    aperture = int(str[line][4:index])
                    index1 = find(str[line], ",", index)
                    index2 = find(str[line], "*", index)
                    size = float(str[line][index1 + 1:index2]) * (10 ** (gerber_data.fraction))
                    appsize[aperture] = size
                    for i in range(nverts):
                        angle = i * 2.0 * math.pi / (nverts - 1.0)
                        x = (size / 2.0) * math.cos(angle)
                        y = (size / 2.0) * math.sin(angle)
                        apertures[aperture].append([x, y])
                    print "   WARNING: read aperture", aperture, ": macro (assuming circle) diameter", size
                    parse = 1
                    continue
                if (parse == 0):
                    print "   ERROR: aperture not implemented:", str[line]
                    line += 1
                    continue

                ##            index = find(str[line],"C,")
                ##            index1 = find(str[line],"*")
                ##            aperture = int(str[line][4:index])
                ##            size = float(str[line][index+2:index1])*(10**(fraction))
                ##            appsize[aperture] = size
                ##            for i in range(nverts):
                ##               angle = i*2.0*pi/(nverts-1.0)
                ##               x = (size/2.0)*cos(angle)
                ##               y = (size/2.0)*sin(angle)
                ##               apertures[aperture].append([x,y])
                ##
                ##            print "   read aperture",aperture,": circle diameter",size
                ##            line += 1

        elif (find(str[line], "D01*") != -1):
            #
            # interpolate operation
            #
            # First check if we need to change the interpolate mode
            if (find(str[line], "G01") != -1):
                interpMode = 1
            elif (find(str[line], "G02") != -1):
                interpMode = 2
            elif (find(str[line], "G03") != -1):
                interpMode = 3
            # Now do the interpolate operation
            if (interpMode == 1):
                #
                # linear interpolate
                #
                [xnew, ynew, iarc, jarc] = read_coord(str[line])

                # if ((abs(xnew - xold) > EPS) | (abs(ynew - yold) > EPS)):
                if regionMode:
                    regions[regionseg].append([xnew, ynew])

                else:
                    tracks[trackseg].append([xnew, ynew])

                xold = xnew
                yold = ynew
                line += 1
                continue

            elif (interpMode == 2):
                #
                # CW circular interpolate
                #
                # just ignore for now
                print "CW circular interpolate ignored"
                line += 1
                continue
            elif (interpMode == 3):
                #
                # CCW circular interpolate
                #
                [xnew, ynew, iarc, jarc] = read_coord(str[line])
                radius = math.sqrt(pow(iarc, 2) + pow(jarc, 2))
                centreX = xold + iarc
                centreY = yold + jarc
                startAngle = math.atan2(yold - centreY, xold - centreX)
                endAngle = math.atan2(ynew - centreY, xnew - centreX)

                if (startAngle < endAngle):
                    angleStep = (endAngle - startAngle) / (nverts - 1.0)
                else:
                    angleStep = (endAngle + 2.0 * math.pi - startAngle) / (nverts - 1.0)
                print ""
                print "   Plotting arc:"
                print "   arc centre (i,j) = ", iarc, ",", jarc
                print "   arc centre (x,y) = ", centreX, ",", centreY
                print "   arc radius = ", radius
                print "   start angle = ", startAngle
                print "   end angle = ", endAngle
                print "   angle step = ", angleStep

                # if ((abs(xnew - xold) > EPS) | (abs(ynew - yold) > EPS)):
                for i in range(nverts):
                    xarcseg = centreX + radius * math.cos(startAngle + angleStep * i)
                    yarcseg = centreY + radius * math.sin(startAngle + angleStep * i)
                    xarcseg = round(xarcseg)
                    yarcseg = round(yarcseg)
                    if regionMode:
                        regions[regionseg].append([xarcseg, yarcseg])
                    else:
                        tracks[trackseg].append([xarcseg, yarcseg])

                xold = xnew
                yold = ynew
                line += 1
                continue
            continue

        elif (find(str[line], "D02*") != -1):
            #
            # Move operation
            #
            [xold, yold, iarc, jarc] = read_coord(str[line])

            if regionMode:
                regions.append([])
                regionseg += 1
                regions[regionseg].append([xold, yold])
            else:
                tracks.append([])
                tracksize.append(aperture)
                trackseg += 1
                tracks[trackseg].append([xold, yold])

            line += 1
            continue

        elif (find(str[line], "D03*") != -1):
            #
            # Flash operation
            #
            if (find(str[line], "D03*") == 0):
                #
                # coordinates on preceeding line
                #
                [xnew, ynew] = [xold, yold]
            else:
                #
                # coordinates on this line
                #
                [xnew, ynew, iarc, jarc] = read_coord(str[line])
            line += 1
            pads.append([])
            padseg += 1

            for verts in apertures[aperture]:
                pads[padseg].append([xnew + verts[0], ynew + verts[1]])

            xold = xnew
            yold = ynew
            continue

        elif (find(str[line], "D") == 0):
            #
            # change aperture
            #
            index = find(str[line], '*')
            aperture = int(str[line][1:index])
            # size = apertures[aperture][SIZE]
            line += 1
            continue
        elif (find(str[line], "G54D") == 0):
            #
            # change aperture
            #
            index = find(str[line], '*')
            aperture = int(str[line][4:index])
            # size = apertures[aperture][SIZE]
            line += 1
            continue
        elif (find(str[line], "G36") == 0):
            #
            # region ON
            #

            regionMode = True
            line += 1
            continue

        elif (find(str[line], "G37") == 0):
            #
            # region OFF
            #

            regionMode = False
            line += 1
            continue

        elif (find(str[line], "M02") == 0):
            #
            # File End
            #

            print "End of file"
            break
        else:
            print "   not parsed:", str[line]
        line += 1

    print "Execution time: ",(time.time() - stt)
    store_to_gd(gerber_data, tracks, pads, regions, apertures, tracksize, isDark)
    return [gerber_data,tracks]


def read_coord(str):
    #
    # parse Gerber coordinates
    #
    # > modified to handle I and J coordinates
    # > Made robust to missing coordinates as per gerber standard
    #
    global gerbx, gerby
    xindex = find(str, "X")
    yindex = find(str, "Y")
    iindex = find(str, "I")
    jindex = find(str, "J")
    index = find(str, "D")
    # i and j are zero if not given
    # gerbx and gerby maintain their last values
    i = 0
    j = 0
    # Check for each of the coordinates and read out the following number
    if (xindex != -1):
        gerbx = int(re.search(r'[-+]?\d+', str[(xindex + 1):index]).group())
    if (yindex != -1):
        gerby = int(re.search(r'[-+]?\d+', str[(yindex + 1):index]).group())
    if (iindex != -1):
        i = int(re.search(r'[-+]?\d+', str[(iindex + 1):index]).group())
    if (jindex != -1):
        j = int(re.search(r'[-+]?\d+', str[(jindex + 1):index]).group())
    return [gerbx, gerby, i, j]


def store_to_gd(gerber_data, tracks, pads, regions, apertures, tracksize, isDark):
    # Stores the existing set of layer data as polygonal data points
    # This is the equivalent of rasterisation of the draw commands
    li = len(gerber_data.layers) / 3
    # Expand tracks from centrelines based on aperture
    track_outlines = []
    for seg in range(len(tracks)):
        for vert in range(len(tracks[seg]) - 1):
            xstart = tracks[seg][vert][0]
            xend = tracks[seg][vert + 1][0]
            ystart = tracks[seg][vert][1]
            yend = tracks[seg][vert + 1][1]
            singletrack = pyclipper.MinkowskiSum(apertures[tracksize[seg]], \
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

    mergedBounds = union_boundary(track_outlines + pads, regions)

    # Store data into layers.
    gerber_data.layers.append(GerberLayer(isDark, str(li) + "_Tracks", track_outlines, type=GerberLayer.TYPE_TRACK))
    gerber_data.layers.append(GerberLayer(isDark, str(li) + "_Boundaries", mergedBounds, False, False, "blue", GerberLayer.TYPE_BOUNDARY))
    # gerber_data.layers.append(GerberLayer(isDark, str(li) + "_Boundaries", track_outlines + pads, False, False, "blue"))
    gerber_data.layers.append(GerberLayer(isDark, str(li) + "_Regions", regions, type=GerberLayer.TYPE_REGION))
    gerber_data.layers.append(GerberLayer(isDark, str(li) + "_Pads", pads, type=GerberLayer.TYPE_PAD, color="#009000"))
    # test_clockwise(mergedBounds)


def union(paths, union_type=pyclipper.PFT_NONZERO):
    #
    #
    # performs union on list, or list of lists
    #
    #

    c = pyclipper.Pyclipper()

    polyclip = paths

    # for path in range(len(polyclip)):
    #    c.AddPaths(polyclip[path], pyclipper.PT_SUBJECT, True)
    c.AddPaths(polyclip, pyclipper.PT_SUBJECT, True)
    polyclip = c.Execute(pyclipper.CT_UNION, union_type, union_type)
    c.Clear()

    return polyclip


def union_boundary(boundarys, regions):
    # global boundary, intersections
    #
    # union intersecting polygons on boundary
    #

    if boundarys != []:
        boundary = union(boundarys, pyclipper.PFT_NONZERO)
        paths = boundary
    else:
        paths = []

    if (len(regions) > 0):
        region = union(regions, pyclipper.PFT_NONZERO)
        paths.extend(region)
        boundary = union(paths, pyclipper.PFT_NONZERO)
    # regions[0] = []

    boundary = pyclipper.CleanPolygons(boundary)
    # boundary = pyclipper.SimplifyPolygons(boundary)
    for segs in boundary:
        if len(segs) == 0:
            boundary.remove([])
            break

    return boundary


def test_clockwise(paths):
    """
    Prints whether each polygon is clockwise or anticlockwise
    """
    for seg in range(len(paths)):
        if len(paths[seg]) == 0: continue
        sum1 = 0
        for vert in range(len(paths[seg])-1):
            sum1 += (paths[seg][vert][0] - paths[seg][vert+1][0]) * \
                (paths[seg][vert][1] + paths[seg][vert+1][1])
        print "Poly ",seg," is test = ",sum1


def is_clockwise(polygon):
    """
    Determine whether the polygon is clockwise or anticlockwise
    """
    if len(polygon) == 0: return True
    sum1 = 0
    for vert in range(len(polygon)-1):
        sum1 += (polygon[vert][0]*polygon[vert+1][1] - polygon[vert+1][0]) * polygon[vert][1]
        #  X1*y2 - x2*y1
    return sum1 > 0


def replace_holes_with_seams(paths):
    """
    Removes holes by creating seams
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


def seperate_holes_and_fills(paths):
    """
    Removes holes by creating seams
    """
    holes = []
    fills = []
    for seg in range(len(paths)):
        if is_clockwise(paths[seg]):
            fills.append(paths[seg])
        else:
            holes.append(paths[seg])
    return [fills, holes]


def add_hole(polygon, diameter, nverts):
    for i in range(nverts):
        angle = -(i * 2.0 * math.pi / (nverts - 1.0))  # Reverse angle to 'subtract' from parent
        x = (diameter / 2.0) * math.cos(angle)
        y = (diameter / 2.0) * math.sin(angle)
        polygon.append([x, y])


def read_float_args(t, sep="X"):
    """
    Splits a string up and parses them into floats
    :type t: str
    :type sep: str
    :rtype: [float]
    """
    strs = t.split(sep)
    retval = []
    for s in strs: retval.append(float(s))
    return retval

def read_float_args_btw(t, start_marker, end_marker, sep="X"):
    """
    Splits a string up and parses them into floats
    Specify markers to look between
    :type t: str
    :type start_marker: str
    :type end_marker: str
    :type sep: str
    :rtype: [float]
    """
    st = t.index(start_marker)
    end = t.index(end_marker)
    return read_float_args(t[st+len(start_marker):end],sep)

# test_clockwise([[[0,0],[0,1],[1,1],[1,0],[0,0]],[[0,0],[1,0],[1,1],[0,1],[0,0]]])
# print "test 1",is_clockwise([[0,0],[0,1],[1,1],[1,0],[0,0]])
# print "test 2",is_clockwise([[0,0],[1,0],[1,1],[0,1],[0,0]])