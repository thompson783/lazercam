from tkFileDialog import askopenfilename, asksaveasfilename
import math
from Tkinter import *
from string import find

import pyclipper

import GerberReader
from GerberReader3 import GerberLayer
from GerberReader3 import load_file
import LayerEditor

__author__ = 'Damien, Ben, Thompson'

# Plots polygon data

VERSION = "v5.1"
DATE = "28/10/15"

HUGE = 1e10
DPI = 25400


class UIParams:
    xmin = 0.0
    xmax = 0.0
    ymin = 0.0
    ymax = 0.0
    zmin = -1.0
    zmax = 0.0

    scale = 1
    panx = 0
    pany = 0


def read_pcb():
    global vertices, faces, boundarys, toolpaths, contours, slices, \
        uiparams, noise_flag, tracks, gerber_data

    definedFileTypes = [('gerber', '.gbl .gtl .gbr .cmp'), \
                        ('drill files', '.drl .dbd'), ('all files', '.*')]
    filename = askopenfilename(filetypes=definedFileTypes)

    if ((find(filename, ".cmp") != -1) | (find(filename, ".CMP") != -1) \
                | (find(filename, ".gtl") != -1) | (find(filename, ".GTL") != -1) \
                | (find(filename, ".gbl") != -1) | (find(filename, ".GBL") != -1)):
        print "reading Gerber file", filename

    uiparams.scale = 1
    uiparams.panx = 0
    uiparams.pany = 0
    contours = []
    toolpaths = []

    infilepcb.set('')
    infileedge.set('')
    infiledrill.set('')

    if (find(filename, ".") != -1):
        index2 = find(filename, ".")
        if (find(filename, "/") != -1):
            index1 = find(filename, "/")
            while (find(filename[index1 + 1:index2], "/") != -1):
                index1 = index1 + 1 + find(filename[index1 + 1:index2], "/")
            infilepcb.set(filename[index1 + 1:index2])

    [gerber_data,tracks] = load_file(filename)

    status.set("Gerber read ok")
    read(0)



def read_edge():
    global vertices, faces, boundarys, toolpaths, contours, slices, \
        uiparams, noise_flag, tracks, gerber_data
    #
    # read edge file
    #
    definedFileTypes = [('gerber', '.gbl .gtl .gbr .cmp'), \
                        ('drill files', '.drl .dbd'), ('all files', '.*')]
    filename = askopenfilename(filetypes=definedFileTypes)

    if ((find(filename, ".gbr") != -1) | (find(filename, ".GBR") != -1)):
        print "reading PCB edge file", filename

        # Load data in SEPARATE data object
        [gerber_data2,edges] = load_file(filename)
        brdoutline = []
        brdseg = -1

        while len(edges) > 0:
            brdoutline.append([])
            brdseg += 1
            brdoutline[brdseg].extend(edges[0])
            edges.remove(edges[0])
            startpnt = brdoutline[brdseg][0]
            endpnt = brdoutline[brdseg][len(brdoutline[brdseg]) - 1]

            while (abs(startpnt[0] - endpnt[0]) > 10) | (abs(startpnt[1] - endpnt[1]) > 10):
                for seg in edges:
                    if abs(seg[0][0] - endpnt[0]) < 10:
                        if abs(seg[0][1] - endpnt[1]) < 10:
                            brdoutline[brdseg].extend(seg)
                            edges.remove(seg)
                            endpnt = brdoutline[brdseg][len(brdoutline[brdseg]) - 1]
                            continue
                    if abs(seg[len(seg) - 1][0] - endpnt[0]) < 10:
                        if abs(seg[len(seg) - 1][1] - endpnt[1]) < 10:
                            edges.remove(seg)
                            seg = seg[::-1]
                            brdoutline[brdseg].extend(seg)
                            endpnt = brdoutline[brdseg][len(brdoutline[brdseg]) - 1]

        pcb_edges = brdoutline
        pcb_edges = pyclipper.CleanPolygons(pcb_edges)

        # Remove existing edge
        layers = list(gerber_data.layers)
        for gl in layers:
            if gl.type == GerberLayer.TYPE_PCBEDGE: gerber_data.layers.remove(gl)

        # Add edge data to existing data
        gerber_data.layers.append(GerberReader.GerberLayer(True, "PCB Edge", pcb_edges, True, False, "blue", GerberLayer.TYPE_PCBEDGE))

        toolpaths = []

        if (find(filename, ".") != -1):
            index2 = find(filename, ".")
            if (find(filename, "/") != -1):
                index1 = find(filename, "/")
                while (find(filename[index1 + 1:index2], "/") != -1):
                    index1 = index1 + 1 + find(filename[index1 + 1:index2], "/")
                infileedge.set(filename[index1 + 1:index2])

        read(0)


def read(event):
    global vertices, faces, toolpaths, contours, slices, \
        uiparams, noise_flag, pcb_edges, boundarys

    uiparams.xmin = HUGE
    uiparams.xmax = -HUGE
    uiparams.ymin = HUGE
    uiparams.ymax = -HUGE
    uiparams.zmin = HUGE
    uiparams.zmax = -HUGE

    sum1 = 0
    sumReg = 0
    sumBound = 0
    sumTracks = 0
    sumPads = 0

    pcb_edges = []
    cbounds = pyclipper.Pyclipper()
    boundarys = []

    layers = list(gerber_data.layers);
    for gl in layers:
        if gl.type == GerberLayer.TYPE_PCBEDGE:
            gerber_data.layers.remove(gl)
            pcb_edges.extend(gl.points)
            for segment in gl.points:
                sum1 += len(segment)
                for vertex in segment:
                    x = vertex[0] * (10 ** (-gerber_data.fraction))
                    y = vertex[1] * (10 ** (-gerber_data.fraction))
                    if (x < uiparams.xmin): uiparams.xmin = x
                    if (x > uiparams.xmax): uiparams.xmax = x
                    if (y < uiparams.ymin): uiparams.ymin = y
                    if (y > uiparams.ymax): uiparams.ymax = y
            continue
        if gl.type == GerberLayer.TYPE_REGION:
            sumReg += len(gl.points)
            # regions.extend(gl.points)
            continue
        if gl.type == GerberLayer.TYPE_TRACK:
            sumTracks += len(gl.points)
            continue
        if gl.type == GerberLayer.TYPE_PAD:
            sumPads += len(gl.points)
            continue
        if gl.type == GerberLayer.TYPE_BOUNDARY:
            if gl.isDark:
                boundarys.extend(gl.points)
            else:
                cbounds.AddPaths(boundarys, pyclipper.PT_SUBJECT)
                cbounds.AddPaths(gl.points, pyclipper.PT_CLIP)
                boundarys = cbounds.Execute(pyclipper.CT_DIFFERENCE, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
                cbounds.Clear()
            sumBound += len(gl.points)
            for segment in gl.points:
                sum1 += len(segment)
                for vertex in segment:
                    x = vertex[0] * (10 ** (-gerber_data.fraction))
                    y = vertex[1] * (10 ** (-gerber_data.fraction))
                    if (x < uiparams.xmin): uiparams.xmin = x
                    if (x > uiparams.xmax): uiparams.xmax = x
                    if (y < uiparams.ymin): uiparams.ymin = y
                    if (y > uiparams.ymax): uiparams.ymax = y
            continue
        if gl.type == GerberLayer.TYPE_MERGEDCOPPER:
            gerber_data.layers.remove(gl)
            continue

    print "   fraction = ",gerber_data.fraction
    print "   found", sumBound, "polygons,", sum1, "vertices"
    print "   found", sumReg, "pours"
    print "   found", sumTracks, "tracks"
    print "   found", sumPads, "pads"
    print "   found", len(pcb_edges), "edge segments"
    print "   xmin: %0.3g " % uiparams.xmin, "xmax: %0.3g " % uiparams.xmax, "dx: %0.3g " % (
        uiparams.xmax - uiparams.xmin)
    print "   ymin: %0.3g " % uiparams.ymin, "ymax: %0.3g " % uiparams.ymax, "dy: %0.3g " % (
        uiparams.ymax - uiparams.ymin)

    outer_offset = 0.01

    if len(pcb_edges) == 0:
        pcb_edge = []
        uiparams.xmax += outer_offset
        uiparams.ymax += outer_offset
        uiparams.xmin -= outer_offset
        uiparams.ymin -= outer_offset
        pcb_edge.append([uiparams.xmax / (10 ** (-gerber_data.fraction)), uiparams.ymax / (10 ** (-gerber_data.fraction))])
        pcb_edge.append([uiparams.xmax / (10 ** (-gerber_data.fraction)), uiparams.ymin / (10 ** (-gerber_data.fraction))])
        pcb_edge.append([uiparams.xmin / (10 ** (-gerber_data.fraction)), uiparams.ymin / (10 ** (-gerber_data.fraction))])
        pcb_edge.append([uiparams.xmin / (10 ** (-gerber_data.fraction)), uiparams.ymax / (10 ** (-gerber_data.fraction))])
        pcb_edges.extend(pcb_edge)
        pcb_edges = [pcb_edges]

    tmpb = GerberReader.replace_holes_with_seams(boundarys)
    gerber_data.layers.append(GerberReader.GerberLayer(True, "PCB Edge", pcb_edges, True, False, "blue", GerberLayer.TYPE_PCBEDGE))
    gerber_data.layers.append(GerberReader.GerberLayer(True, "Merged Copper", tmpb, False, color="brown", type=GerberLayer.TYPE_MERGEDCOPPER))
    # the boundary data with seams in it is for rendering purposes only.

    camselect(event)
    plot()
    autoscale(0)

    LayerEditor.createTable2(layerGeo, gerber_data, plot)


def autoscale(event):
    global uiparams, fixed_size
    #
    # fit window to object
    #
    xyscale = float(sxyscale.get())
    sxmin.set("0")
    symin.set("0")

    # scale canvas contents to fit
    zoomScale = 0.8*min(c.winfo_width()/(DPI*(uiparams.xmax-uiparams.xmin)), \
                        c.winfo_height()/(DPI*(uiparams.ymax-uiparams.ymin)))/uiparams.scale

    uiparams.scale *= zoomScale
    scalelabel.set("Scale %6.5f" % uiparams.scale)
    c.scale("PlotObjects", 0, 0, zoomScale, zoomScale)

    sreg = getScrollBounds()
    c.configure(scrollregion=sreg)
    uiparams.panx = int((sreg[0] + sreg[2] - c.winfo_width())/2)
    uiparams.pany = int((sreg[1] + sreg[3] - c.winfo_height())/2)
    c.scan_dragto(-uiparams.panx, -uiparams.pany, 1)  # stops working after panning by user???
    print "  init x,y  ",uiparams.panx,"  ",uiparams.pany

    # if ((uiparams.ymax - uiparams.ymin) > (uiparams.xmax - uiparams.xmin)):
    #     sxysize.set(str(xyscale * (round(uiparams.ymax - uiparams.ymin, 2))))
    # else:
    #     sxysize.set(str(xyscale * (round(uiparams.xmax - uiparams.xmin, 2))))
    #
    # fixed_size = True
    # # plot_delete(event)
    # plot(event)


def fixedscale(event):
    global uiparams, fixed_size
    #
    # show object at original scale and location
    #
    fixed_size = False
    camselect(event)
    xyscale = float(sxyscale.get())
    sxmin.set(str(uiparams.xmin * xyscale))
    symin.set(str(uiparams.ymin * xyscale))
    # plot_delete(event)
    plot()


def getScrollBounds():
    sreg = c.bbox("PlotObjects")
    w = 16
    h = 16
    return (sreg[0] - w, sreg[1] - h, sreg[2] + w, sreg[3] + h)


def plot():
    global vertices, faces, boundarys, toolpaths, \
        uiparams, regions, showregion, gerber_data
    #
    # scale and plot object and toolpath
    # > updated to plot a closed path
    #
    print "plotting"
    xysize = float(sxysize.get())
    # zsize = float(szsize.get())
    xyscale = float(sxyscale.get())
    # zscale = float(szscale.get())
    ##   xoff = float(sxmin.get()) - xmin*xyscale
    ##   yoff = float(symin.get()) - ymin*xyscale
    ##   zoff = float(szmax.get()) - zmax*zscale
    if placeaxis == 1:
        xoff = float(sxmin.get()) - uiparams.xmin * xyscale
        yoff = float(symin.get()) - uiparams.ymin * xyscale
    elif placeaxis == 2:
        xoff = float(sxmin.get()) - uiparams.xmin * xyscale
        yoff = float(symin.get()) - uiparams.ymax * xyscale
    elif placeaxis == 3:
        xoff = float(sxmin.get()) - uiparams.xmax * xyscale
        yoff = float(symin.get()) - uiparams.ymax * xyscale
    elif placeaxis == 4:
        xoff = float(sxmin.get()) - uiparams.xmax * xyscale
        yoff = float(symin.get()) - uiparams.ymin * xyscale
    else:
        xoff_export = float(sxmin.get()) - (uiparams.xmin + (uiparams.xmax - uiparams.xmin) / 2) * xyscale
        yoff_export = float(symin.get()) - (uiparams.ymin + (uiparams.ymax - uiparams.ymin) / 2) * xyscale
        xoff = xoff_export + float(sxysize.get()) / 2
        yoff = yoff_export + float(sxysize.get()) / 2

    sdxy.set("  dx:%6.3f  dy:%6.3f" % ((uiparams.xmax - uiparams.xmin) * xyscale, \
                                       (uiparams.ymax - uiparams.ymin) * xyscale))

    # Clear the plots
    c.delete(ALL)

    for tmp in gerber_data.layers:
        if not tmp.visible.get(): continue
        for seg in tmp.points:
            if len(seg) > 0:
                path_plot = []
                for vertex in seg:
                    xplot = int((vertex[0] * (10 ** (-gerber_data.fraction)) * xyscale + xoff) * DPI)
                    path_plot.append(xplot)
                    yplot = -int((vertex[1] * (10 ** (-gerber_data.fraction)) * xyscale + yoff) * DPI)
                    path_plot.append(yplot)
                path_plot.append(path_plot[0])  # close the polygon
                path_plot.append(path_plot[1])
                col = tmp.color.get() if tmp.isDark else "light blue"
                if tmp.filled.get():
                    c.create_polygon(path_plot, tags=(tmp.name.get(), "PlotObjects"), fill=col, activefill="yellow")
                else:
                    c.create_line(path_plot, tags=(tmp.name.get(), "PlotObjects"), fill=col, activefill="yellow")
        print("   Drawn layer: " + tmp.name.get() + ",  # of poly: " + str(len(tmp.points)))

    if showcuts.get() == 0:
        linewidth = 0
    else:
        linewidth = math.ceil(((float(sdia.get()))) * DPI * uiparams.scale)

    if showtoolpath.get() == 1:
        for seg in range(len(toolpaths)):
            if len(toolpaths[seg]) > 0:
                path_plot = []
                for vertex in range(len(toolpaths[seg])):
                    xplot = int((toolpaths[seg][vertex][0] * (10 ** (-gerber_data.fraction)) * xyscale + xoff) * DPI)
                    path_plot.append(xplot)
                    yplot = -int((toolpaths[seg][vertex][1] * (10 ** (-gerber_data.fraction)) * xyscale + yoff) * DPI)
                    path_plot.append(yplot)
                c.create_line(path_plot, tags=("plot_path", "PlotObjects"), fill="red", width=linewidth, capstyle="round")

    # Draw origin
    c.create_line([(-20, 0), (20, 0)], tags=("plot_origin", "CanvasObjects"), fill="orange", width=3)
    c.create_line([(0, -20), (0, 20)], tags=("plot_origin", "CanvasObjects"), fill="orange", width=3)
    c.create_oval(-10, -10, 10, 10, tags=("plot_origin", "CanvasObjects"), outline="orange", width=3)

    c.scale("PlotObjects", 0, 0, uiparams.scale, uiparams.scale)
    print "   done"

def plot_delete(event):
    global toolpaths, contours
    #
    # scale and plot boundary, delete toolpath
    #
    toolpaths = []
    contours = []

    print "deleted toolpath"
    plot()


def offset_poly(path, toolrad):
    c_osp = pyclipper.PyclipperOffset()
    c_osp.AddPaths(path, pyclipper.JT_SQUARE, pyclipper.ET_CLOSEDPOLYGON)
    polyclip = c_osp.Execute(toolrad)

    polyclip = pyclipper.CleanPolygons(polyclip)

    c_osp.Clear()
    return polyclip


def contour(event):
    global boundarys, toolpaths, contours
    #
    # contour boundary to find toolpath
    #
    print "contouring boundary ..."
    xyscale = float(sxyscale.get())
    N_contour = int(sncontour.get())
    overlap = float(sundercut.get())

    toolpaths = []

    for n in range(1, N_contour + 1):
        if n == 1:
            toolrad = (n) * ((float(sdia.get()) / 2.0) / xyscale) * (10 ** gerber_data.fraction)
        else:
            toolrad += ((float(sdia.get()) / 2.0) * overlap / xyscale) * (10 ** gerber_data.fraction)
        contours = offset_poly(boundarys, toolrad)
        toolpaths.extend(contours)

    toolpaths.extend(pcb_edges)
    # contours[0].extend(pcb_edge)
    for seg in toolpaths:
        if (len(seg) > 0):
            seg.append(seg[0])

    plot()

    print "   done"
    status.set("Contour done")


def raster(event):
    global contours, boundarys, toolpaths, uiparams
    #
    # raster interiors
    #
    print "rastering interior ..."
    xyscale = float(sxyscale.get())
    tooldia = (float(sdia.get()) / xyscale) * (10 ** gerber_data.fraction)
    #
    # 2D raster
    #
    if (contours == []):
        edgepath = boundarys
        delta = tooldia / 2.0
    else:
        edgepath = contours
        delta = 0  # tooldia/4.0
    rasterpath = raster_area(edgepath, delta, uiparams.ymin * (10 ** gerber_data.fraction), uiparams.ymax * (10 ** gerber_data.fraction), \
                             uiparams.xmin * (10 ** gerber_data.fraction), uiparams.xmax * (10 ** gerber_data.fraction))
    # toolpaths[0].extend(pyclipper.PolyTreeToPaths(rasterpath))
    toolpaths.extend(rasterpath)

    plot()
    print "   done"
    status.set("Raster done")


def raster_area(edgepath, delta, ymin1, ymax1, xmin1, xmax1):
    #
    # raster a 2D region
    #
    # find row-edge intersections
    #
    xyscale = float(sxyscale.get())
    overlap = float(soverlap.get())
    tooldia = (float(sdia.get()) / xyscale) * (10 ** gerber_data.fraction)
    rastlines = []
    starty = ymin1
    endy = ymax1
    startx = round(xmax1, 2)
    endx = round(xmin1, 2)
    numrows = int(math.floor((endy - starty) / (tooldia * overlap)))
    crast = pyclipper.Pyclipper()
    edgepath = offset_poly(edgepath, delta)
    result = []

    for row in range(numrows + 1):
        rastlines.append([])
        rastlines[row].append([startx, round((starty + row * (tooldia * overlap)), 4)])
        rastlines[row].append([endx, round((starty + row * (tooldia * overlap)), 4)])
        startx, endx = endx, startx

    crast.AddPaths(pcb_edges, pyclipper.PT_CLIP,True)
    crast.AddPaths(rastlines, pyclipper.PT_SUBJECT, False)
    rastlines = crast.Execute2(pyclipper.CT_INTERSECTION, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)

    crast.Clear()
    rastlines = pyclipper.PolyTreeToPaths(rastlines)

    ##
    crast.AddPaths(edgepath, pyclipper.PT_CLIP, True)
    crast.AddPaths(rastlines, pyclipper.PT_SUBJECT, False)
    rastlines = crast.Execute2(pyclipper.CT_DIFFERENCE, pyclipper.PFT_POSITIVE, pyclipper.PFT_POSITIVE)

    crast.Clear()

    rastlines = pyclipper.PolyTreeToPaths(rastlines)
    # polyclip.sort(key=lambda x: (x[0][1],x[0][0]))
    # polyclip.sort(key=lambda x: x[0][1])
    # polyclip.sort(key=lambda x: x[0][0])
    rastltor = []
    rastrtol = []
    for segs in rastlines:
        if (segs[0][0] < segs[1][0]):
            rastltor.append(segs)
        else:
            rastrtol.append(segs)
    rastltor.sort(key=lambda x: (x[0][1], x[0][0]))
    rastrtol.sort(key=lambda x: (x[0][1], -x[0][0]))

    result.extend(rastltor)
    result.extend(rastrtol)
    result.sort(key=lambda x: x[0][1])

    return result


def write_G():
    global boundarys, toolpaths, uiparams
    #
    # G code output
    #
    xyscale = float(sxyscale.get())
    zscale = float(sxyscale.get())
    feed = float(sfeed.get())
    xoff = float(sxmin.get()) - uiparams.xmin * xyscale
    yoff = float(symin.get()) - uiparams.ymin * xyscale
    cool = icool.get()
    text = outfile.get()
    file = open(text, 'w')
    # file.write("%\n")
    file.write("G20\n")
    file.write("T" + stool.get() + "M06\n")  # tool
    file.write("G90 G54\n")  # absolute positioning with respect to set origin
    file.write("F%0.3f\n" % feed)  # feed rate
    file.write("S" + sspindle.get() + "\n")  # spindle speed
    if (cool == TRUE): file.write("M08\n")  # coolant on
    file.write("G0 Z" + szup.get() + "\n")  # move up before starting spindle
    file.write("M3\n")  # spindle on clockwise
    nsegment = 0

    if (toolpaths == []):
        path = boundarys
    else:
        path = toolpaths
    if (szdown.get() == " "):
        raise StandardError("This line has an error")
        # zdown = zoff + zmin + (layer-0.50)*dlayer
    else:
        zdown = float(szdown.get())
    for segment in range(len(path)):
        nsegment += 1
        vertex = 0
        x = path[segment][vertex][0] * xyscale * (10 ** -gerber_data.fraction) + xoff
        y = path[segment][vertex][1] * xyscale * (10 ** -gerber_data.fraction) + yoff
        file.write("G0 X%0.4f " % x + "Y%0.4f " % y + "Z" + szup.get() + "\n")  # rapid motion
        file.write("G1 Z%0.4f " % zdown + "\n")  # linear motion
        for vertex in range(1, len(path[segment])):
            x = path[segment][vertex][0] * xyscale * (10 ** -gerber_data.fraction) + xoff
            y = path[segment][vertex][1] * xyscale * (10 ** -gerber_data.fraction) + yoff
            file.write("G1 X%0.4f " % x + "Y%0.4f" % y + "\n")
        file.write("Z" + szup.get() + "\n")
    # for layer in range((len(boundarys) - 1), -1, -1):
        # if (toolpaths[layer] == []):
        #     path = boundarys[layer]
        # else:
        #     path = toolpaths[layer]
        # if (szdown.get() == " "):
        #     raise StandardError("This line has an error")
        #     # zdown = zoff + zmin + (layer-0.50)*dlayer
        # else:
        #     zdown = float(szdown.get())
        # for segment in range(len(path)):
        #     nsegment += 1
        #     vertex = 0
        #     x = path[segment][vertex][0] * xyscale * (10 ** -gerber_data.fraction) + xoff
        #     y = path[segment][vertex][1] * xyscale * (10 ** -gerber_data.fraction) + yoff
        #     file.write("G0 X%0.4f " % x + "Y%0.4f " % y + "Z" + szup.get() + "\n")  # rapid motion
        #     file.write("G1 Z%0.4f " % zdown + "\n")  # linear motion
        #     for vertex in range(1, len(path[segment])):
        #         x = path[segment][vertex][0] * xyscale * (10 ** -gerber_data.fraction) + xoff
        #         y = path[segment][vertex][1] * xyscale * (10 ** -gerber_data.fraction) + yoff
        #         file.write("G1 X%0.4f " % x + "Y%0.4f" % y + "\n")
        #     file.write("Z" + szup.get() + "\n")
    file.write("G0 Z" + szup.get() + "\n")  # move up before stopping spindle
    file.write("M5\n")  # spindle stop
    if (cool == TRUE): file.write("M09\n")  # coolant off
    file.write("M30\n")  # program end and reset
    # file.write("%\n")
    file.close()
    print "wrote", nsegment, "G code toolpath segments to", text
    status.set("wrote " + str(nsegment) + " G code toolpath segments to " + str(text))


def write_l():
    global boundarys, toolpaths, uiparams
    #
    # LaZoR Mk1 code output
    #
    print uiparams.xmax, "  ", uiparams.xmin
    print uiparams.ymax, "  ", uiparams.ymin
    xyscale = float(sxyscale.get())
    zscale = float(sxyscale.get())
    # dlayer = float(sthickness.get())/zscale
    feed = float(sfeed.get())
    xoff = float(sxmin.get()) - uiparams.xmin * xyscale
    yoff = float(symin.get()) - uiparams.ymin * xyscale
    cool = icool.get()
    text = outfile.get()
    file = open(text, 'w')
    # file.write("%\n")
    # file.write("O1234\n")
    # file.write("T"+stool.get()+"M06\n") # tool
    file.write("G90G54\n")  # absolute positioning with respect to set origin
    # file.write("F%0.3f\n"%feed) # feed rate
    file.write("S" + sspindle.get() / 100 + "\n")  # spindle speed
    # if (cool == TRUE): file.write("M08\n") # coolant on
    # file.write("G00Z"+szup.get()+"\n") # move up before starting spindle
    # file.write("M03\n") # spindle on clockwise
    nsegment = 0
    for layer in range((len(boundarys) - 1), -1, -1):
        if (toolpaths[layer] == []):
            path = boundarys[layer]
        else:
            path = toolpaths[layer]
        ##      if (szdown.get() == " "):
        ##         zdown = zoff + zmin + (layer-0.50)*dlayer
        ##      else:
        ##         zdown = float(szdown.get())
        for segment in range(len(path)):
            ##         if (len(path[segment])==0):
            ##            continue
            nsegment += 1
            vertex = 0
            x = path[segment][vertex][0] * xyscale * (10 ** -gerber_data.fraction) + xoff
            y = path[segment][vertex][1] * xyscale * (10 ** -gerber_data.fraction) + yoff

            file.write("G00X%0.4f" % x + "Y%0.4f" % y + "\n")  # rapid motion
            # file.write("G01Z%0.4f"%zdown+"\n") # linear motion
            file.write("M03\n")
            for vertex in range(1, len(path[segment])):
                x = path[segment][vertex][0] * xyscale * (10 ** -gerber_data.fraction) + xoff
                y = path[segment][vertex][1] * xyscale * (10 ** -gerber_data.fraction) + yoff
                file.write("G01X%0.4f" % x + "Y%0.4f" % y + "F%0.3f\n" % feed + "\n")

            # file.write("Z"+szup.get()+"\n")
            file.write("M05\n")
    # file.write("G00Z"+szup.get()+"\n") # move up before stopping spindle
    file.write("M05\n")  # spindle stop
    if (cool == TRUE): file.write("M09\n")  # coolant off
    file.write("M30\n")  # program end and reset
    # file.write("%\n")
    file.close()
    print "wrote", nsegment, "G code toolpath segments to", text
    status.set("wrote " + str(nsegment) + " G code toolpath segments to " + str(text))


#
# *********** GUI event handlers ********************
#

def write():
    global uiparams
    #
    # write toolpath
    #
    text = outfile.get()
    if (find(text, ".g") != -1):
        write_G()
    elif (find(text, ".l") != -1):
        write_l()
    else:
        print "unsupported output file format"
        return
    xyscale = float(sxyscale.get())
    xoff = float(sxmin.get()) - uiparams.xmin * xyscale
    yoff = float(symin.get()) - uiparams.ymin * xyscale
    print "   xmin: %0.3g " % (uiparams.xmin * xyscale + xoff), \
        "xmax: %0.3g " % (uiparams.xmax * xyscale + xoff), \
        "dx: %0.3g " % ((uiparams.xmax - uiparams.xmin) * xyscale)
    print "   ymin: %0.3g " % (uiparams.ymin * xyscale + yoff), \
        "ymax: %0.3g " % (uiparams.ymax * xyscale + yoff), \
        "dy: %0.3g " % ((uiparams.ymax - uiparams.ymin) * xyscale)


def delframes():
    #
    # delete all CAM frames
    #
    ##   camframe.pack_forget()
    # cutframe.pack_forget()
    # imgframe.pack_forget()
    toolframe.pack_forget()
    feedframe.pack_forget()
    ##   zcoordframe.pack_forget()
    z2Dframe.pack_forget()
    # zsliceframe.pack_forget()
    gframe.pack_forget()
    outframe.pack_forget()
    # laserframe.pack_forget()
    # excimerframe.pack_forget()
    # autofocusframe.pack_forget()
    # jetframe.pack_forget()
    # out3Dframe.pack_forget()


##   leftframe.grid_forget
##   boardGeo.grid_forget
##   devframe.grid_forget

def camselect(event):
    global faces, xysize, zsize, fixed_size
    #
    # pack appropriate CAM GUI options based on output file
    #
    xyscale = float(sxyscale.get())
    zscale = float(szscale.get())
    outtext = outfile.get()
    if (find(outtext, ".g") != -1):
        delframes()
        ##      camframe.grid()
        if (not fixed_size):
            sxysize.set("3")
        ##         szsize.set("3")
        sxyvel.set("2")
        ##      szvel.set("2")
        ##############
        ##      zcoordframe.grid()
        szup.set("0.05")
        szdown.set("-0.005")

        ##############
        sdia.set("0.008")
        soverlap.set("0.8")
        ##      toolframe.grid()
        toolframe.pack()
        sfeed.set("100")
        sspindle.set("1000")
        stool.set("1")
        ##      gframe.grid()
        ##      z2Dframe.grid()
        gframe.pack()
        z2Dframe.pack()
        outframe.pack()
    elif (find(outtext, ".l") != -1):
        delframes()
        ##      camframe.grid()
        if (not fixed_size):
            sxysize.set("3")
            szsize.set("3")
        sxyvel.set("2")
        szvel.set("2")
        sdia.set("0.004")
        soverlap.set("0.8")
        ##      toolframe.grid()
        toolframe.pack()
        sfeed.set("100")
        sspindle.set("100")
        stool.set("1")
        ##      gframe.grid()
        gframe.pack()
        outframe.pack()
    else:
        print "output file format not supported"
    return


def devselect(event):
    #
    # select the output device
    #
    sel = wdevlist.get(wdevlist.curselection())
    cur_sel = outfile.get()
    dot = find(cur_sel, '.')
    cur_sel = cur_sel[(dot + 1):]
    if ((sel[0:2] == 'g:') & (cur_sel != 'g')):
        outfile.set('out.g')
        camselect(0)
    elif ((sel[0:2] == 'l:') & (cur_sel != 'l')):
        outfile.set('out.l')
        camselect(0)
    plot_delete(event)


##def send(event):
##   #
##   # send to the output device
##   #
##   outtext = outfile.get()
##   if (find(outtext,".rml") != -1):
##      wdevbtn.config(text="sending ...")
##      wdevbtn.update()
##      write(event)
##      print os.system('stty 9600 raw -echo crtscts </dev/ttyS0')
##      print os.system('cat %s > /dev/ttyS0'%outtext)
##      print os.system('rm %s'%outtext)
##      wdevbtn.config(text="send to")
##      #wdevbtn.update()
##   elif (find(outtext,".camm") != -1):
##      wdevbtn.config(text="sending ...")
##      wdevbtn.update()
##      write(event)
##      print os.system('stty 9600 raw -echo crtscts </dev/ttyS0')
##      print os.system('cat %s > /dev/ttyS0'%outtext)
##      print os.system('rm %s'%outtext)
##      wdevbtn.config(text="send to")
##      #wdevbtn.update()
##   elif (find(outtext,".epi") != -1):
##      wdevbtn.config(text="sending ...")
##      wdevbtn.update()
##      write(event)
##      print os.system('lpr -P Queue %s'%outtext)
##      print os.system('rm %s'%outtext)
##      wdevbtn.config(text="send to")
##      #wdevbtn.update()
##   else:
##      print "output not configured for",outtext

def openfile():
    #
    # dialog to select an input file
    #
    ##   definedFileTypes = [('gerber','.gbl .gtl .gbr .cmp'),\
    ##                       ('drill files','.drl .dbd'),('all files','.*')]
    ##   filename = askopenfilename(filetypes=definedFileTypes)
    ##   infile.set(filename)
    read(0)


def savefile():
    #
    # dialog to select an output file
    #
    filename = asksaveasfilename()
    outfile.set(filename)
    camselect(0)


def showcoord(event):
    xycoord.set("X %6.3f Y %6.3f" % ((round(c.canvasx(event.x) / DPI, 4)), (round(-c.canvasy(event.y) / DPI, 4))))


# windows mouse wheel zoom
def zoomer(event):
    # get current mouse position as a canvas coordinate
    mouse_x = c.canvasx(event.x)
    mouse_y = c.canvasy(event.y)
    if event.delta < 0:
        zoomScale = 0.8
    elif event.delta > 0:
        zoomScale = 1.2
    else:
        return
    # The following zooms centred to the origin
    # it would be better to zoom in around mouse point
    # but the scaling commands are mysterious as it is.
    c.scale("PlotObjects", 0, 0, zoomScale, zoomScale)
    uiparams.scale *= zoomScale
    scalelabel.set("Scale %6.5f" % uiparams.scale)

    # Scale linewidth
    linewidth = c.itemcget("plot_path", "width")
    if linewidth != '': c.itemconfig("plot_path", width=float(linewidth) * zoomScale)
    c.configure(scrollregion=getScrollBounds())


def pan_start(event):
    c.configure(cursor="fleur")
    c.scan_mark(event.x, event.y)


def pan_move(event):
    c.scan_dragto(event.x, event.y, gain=1)
    uiparams.panx = c.canvasx(0)
    uiparams.pany = c.canvasy(0)
    xycoord.set("X %2.1f Y %2.1f Sc %5.3f" % (uiparams.panx, uiparams.pany, uiparams.scale))


def pan_end(event):
    c.configure(cursor="crosshair")


def Canvas_ScrollX(event):
    if event.delta < 0:
        c.xview_scroll(1, "units")
    if event.delta > 0:
        c.xview_scroll(-1, "units")


def Canvas_ScrollY(event):
    if event.delta < 0:
        c.yview_scroll(1, "units")
    if event.delta > 0:
        c.yview_scroll(-1, "units")


def zoomin():
    #
    # Zoom plot in
    #
    c.scale("PlotObjects", 0, 0, 1.1, 1.1)
    uiparams.scale *= 1.1
    scalelabel.set("Scale %6.5f" % uiparams.scale)
    # Scale linewidth
    linewidth = c.itemcget("plot_path", "width")
    if linewidth != '':
        c.itemconfig("plot_path", width=float(linewidth) * 1.1)
    c.configure(scrollregion=getScrollBounds())


def zoomout():
    #
    # Zoom plot out
    #
    c.scale("PlotObjects", 0, 0, 0.8, 0.8)
    uiparams.scale *= 0.8
    scalelabel.set("Scale %6.5f" % uiparams.scale)
    # Scale linewidth
    linewidth = c.itemcget("plot_path", "width")
    if linewidth != '':
        c.itemconfig("plot_path", width=float(linewidth) * 0.8)
    c.configure(scrollregion=getScrollBounds())


def callplot():
    plot()


def canvasframe_resize(event):
    canvas_width = event.width
    canvas_height = event.height


def SetCanvasFocus(event):
    c.focus_set()


def ClearCanvasFocus(event):
    root.focus_set()


def donothing():
    nothing = 0


def quitApp():
    root.destroy()


# ===========================================================================


#
# initial canvas size in pixels
#
WINDOW = 500

#
# define GUI
#
root = Tk()
root.title('LaZoR.py')
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)
root.update()
root.minsize(root.winfo_width(), root.winfo_height())

infile = StringVar()
infile.set('')
infilepcb = StringVar()
infilepcb.set('')
infileedge = StringVar()
infileedge.set('')
infiledrill = StringVar()
infiledrill.set('')
outfile = StringVar()
outfile.set('out.g')
uiparams = UIParams()
xyscale = 1.0
zscale = 1.0
xysize = 1.0
zsize = 1.0
nverts = 16
fixed_size = False
jobname = ""
sxmin = StringVar()
sxmin.set(str(uiparams.xmin))
symin = StringVar()
symin.set(str(uiparams.ymin))
szmax = StringVar()
szmax.set(str(uiparams.zmax))
sxyscale = StringVar()
sxyscale.set(str(xyscale))
szscale = StringVar()
szscale.set(str(zscale))
sxysize = StringVar()
sxysize.set(str(xysize))
szsize = StringVar()
szsize.set(str(zsize))
sncontour = StringVar()
sncontour.set(1)
sundercut = StringVar()
sundercut.set(.8)
xycoord = StringVar()
xycoord.set("X 0.000, Y 0.000")
scalelabel = StringVar()

# Plot options
coppermode = IntVar()
coppermode.set(0)
showcontour = IntVar()
showboundary = IntVar()
showorigin = IntVar()
showorigin.set(1)
showtoolpath = IntVar()
showtoolpath.set(1)
showpad = IntVar()
showtrack = IntVar()
showregion = IntVar()
showcuts = IntVar()

# ********* Main Menu ***************
menubar = Menu(root)
filemenu = Menu(menubar, tearoff=0)
filemenu.add_command(label="Load board file", command=read_pcb)
filemenu.add_command(label="Load PCB edge file", command=read_edge)
filemenu.add_command(label="Load Drill file", command=donothing)
filemenu.add_separator()
filemenu.add_command(label="Exit", command=quitApp)
menubar.add_cascade(label="File", menu=filemenu)

viewmenu = Menu(menubar, tearoff=0)
viewmenu.add_command(label="Zoom in", command=zoomin)
viewmenu.add_command(label="Zoom out", command=zoomout)
viewmenu.add_command(label="Zoom to fit", command=donothing)
viewmenu.add_command(label="Redraw", command=donothing)
viewmenu.add_separator()
viewmenu.add_radiobutton(label="Show copper filled", variable=coppermode, value=0, command=callplot)
viewmenu.add_radiobutton(label="Show copper boundary", variable=coppermode, value=1, command=callplot)
viewmenu.add_radiobutton(label="Hide copper", variable=coppermode, value=2, command=callplot)
viewmenu.add_separator()
viewmenu.add_checkbutton(label="Show tracks", command=donothing)
viewmenu.add_checkbutton(label="Show pads", command=donothing)
viewmenu.add_checkbutton(label="Show regions", command=donothing)
viewmenu.add_separator()
viewmenu.add_checkbutton(label="Show origin", variable=showorigin, command=donothing)
viewmenu.add_checkbutton(label="Show toolpaths", variable=showtoolpath, command=callplot)
viewmenu.add_checkbutton(label="Show cutwidth", variable=showcuts, command=callplot)
menubar.add_cascade(label="View", menu=viewmenu)

workmenu = Menu(menubar, tearoff=0)
isomenu = Menu(workmenu, tearoff=0)
workmenu.add_cascade(label="Isolation", menu=isomenu)
isomenu.add_command(label="Milling", command=donothing)
isomenu.add_command(label="LaZoR (TM)", command=donothing)
workmenu.add_command(label="Drill", command=donothing)
workmenu.add_command(label="Edge Cuts", command=donothing)
workmenu.add_separator()
workmenu.add_command(label="Shoot Lasers", command=donothing)
menubar.add_cascade(label="Workbench", menu=workmenu)

exportmenu = Menu(menubar, tearoff=0)
exportmenu.add_command(label="Export mill file", command=donothing)
exportmenu.add_command(label="Export LaZoR (TM) file", command=donothing)
menubar.add_cascade(label="Export", menu=exportmenu)

helpmenu = Menu(menubar, tearoff=0)
helpmenu.add_command(label="Help Index", command=donothing)
helpmenu.add_command(label="About...", command=donothing)
menubar.add_cascade(label="Help", menu=helpmenu)

centrestrip = Frame(root)
centrestrip.pack(side=TOP, fill=BOTH, expand=YES)

leftframe = Frame(centrestrip)
leftframe.pack(side=LEFT, fill=BOTH)
leftframe.config(bd=5, relief=SUNKEN)

Label(leftframe, text="Workbench").pack(side=TOP, pady=10)

#
# *********** Output device selection *********
#
devframe = Frame(leftframe, pady=10)
##devframe.grid(row = 3, column = 0, pady = 10)
devframe.pack()
##wdevbtn = Button(devframe, text="send to")
##wdevbtn.bind('<Button-1>',send)
##wdevbtn.pack(side="left")
Label(devframe, text=" output device: ").grid(row=0, column=0, sticky=W)
wdevscroll = Scrollbar(devframe, orient=VERTICAL)
wdevlist = Listbox(devframe, width=40, height=1, yscrollcommand=wdevscroll.set)
wdevlist.bind('<ButtonRelease-1>', devselect)
wdevscroll.config(command=wdevlist.yview)
wdevscroll.grid(row=1, column=2, rowspan=3, sticky=N + S)
wdevlist.insert(END, "g: G code file")
wdevlist.insert(END, "l: LaZoR code file")
wdevlist.grid(row=1, column=0, rowspan=3, columnspan=2, sticky=N + S + E + W)
wdevlist.select_set(0)

#
toolframe = Frame(leftframe)
Label(toolframe, text="Tool diameter: ").grid(row=0, column=0, sticky=E)
sdia = StringVar()
wtooldia = Entry(toolframe, width=6, textvariable=sdia)
wtooldia.grid(row=0, column=1, sticky=E + W)
wtooldia.bind('<Key>', plot_delete)
Label(toolframe, text="N contour: ").grid(row=1, column=0, sticky=E)
wncontour = Entry(toolframe, width=3, textvariable=sncontour)
wncontour.grid(row=1, column=1, sticky=E + W)
wncontour.bind('<Key>', plot_delete)
Label(toolframe, text="Contour undercut: ").grid(row=1, column=2, sticky=E)
wundercut = Entry(toolframe, width=6, textvariable=sundercut)
wundercut.grid(row=1, column=3, sticky=E + W)
wundercut.bind('<Return>', plot_delete)
contbtn = Button(toolframe, text="Contour")
contbtn.bind('<Button-1>', contour)
contbtn.grid(row=2, column=0, columnspan=4, sticky=E + W, pady=10)

Label(toolframe, text="Raster overlap: ").grid(row=3, column=0, sticky=E)
soverlap = StringVar()
woverlap = Entry(toolframe, width=6, textvariable=soverlap)
woverlap.grid(row=3, column=1, sticky=E + W)
woverlap.bind('<Key>', plot_delete)
rastbtn = Button(toolframe, text="Raster")
rastbtn.bind('<Button-1>', raster)
rastbtn.grid(row=4, column=0, columnspan=4, sticky=E + W, pady=10)

#
feedframe = Frame(leftframe)
Label(feedframe, text=" xy speed:").grid(row=0, column=0, sticky=W)
sxyvel = StringVar()
Entry(feedframe, width=10, textvariable=sxyvel).grid(row=0, column=1, sticky=W)
Label(feedframe, text=" z speed:").grid(row=1, column=0, sticky=W)
szvel = StringVar()
Entry(feedframe, width=10, textvariable=szvel).grid(row=1, column=1, sticky=W)

#
z2Dframe = Frame(leftframe)
Label(z2Dframe, text="z up:").grid(row=0, column=0, sticky=W)
szup = StringVar()
Entry(z2Dframe, width=10, textvariable=szup).grid(row=0, column=1, sticky=E + W)
Label(z2Dframe, text=" z down:").grid(row=1, column=0, sticky=W)
szdown = StringVar()
Entry(z2Dframe, width=10, textvariable=szdown).grid(row=1, column=1, sticky=E + W)

#
gframe = Frame(leftframe)
Label(gframe, text=" feed rate:").grid(row=0, column=0, sticky=W)
sfeed = StringVar()
Entry(gframe, width=6, textvariable=sfeed).grid(row=0, column=1, sticky=W)
Label(gframe, text=" spindle speed:").grid(row=0, column=2, sticky=W)
sspindle = StringVar()
Entry(gframe, width=6, textvariable=sspindle).grid(row=0, column=3, sticky=W)
Label(gframe, text=" tool:").grid(row=1, column=0, sticky=W)
stool = StringVar()
Entry(gframe, width=3, textvariable=stool).grid(row=1, column=1, sticky=W)
icool = IntVar()
wcool = Checkbutton(gframe, text="coolant", variable=icool)
wcool.grid(row=1, column=2, columnspan=2, sticky=W)

#
# *********** Toolpath write *********
#
outframe = Frame(leftframe)
##outframe.grid(row = 4, column = 0, pady = 10)
outframe.pack()

outbtn = Button(outframe, text="output file:", command=savefile)
outbtn.grid(row=0, column=0, pady=10, sticky=W)
##outbtn.pack()
woutfile = Entry(outframe, width=15, textvariable=outfile)
woutfile.bind('<Return>', camselect)
woutfile.grid(row=0, column=1, columnspan=2, sticky=E)
##Label(outframe, text=" ").grid(row = 1, column = 0)
##Button(outframe, text="quit", command='exit').grid(row = 0, column = 3)
writebtn = Button(outframe, text="write toolpath", command=write)
# writebtn.bind('<Button-1>',write)
writebtn.grid(row=1, column=0, columnspan=4, sticky=E + W)
##Label(camframe, text=" ").pack(side="left")##Label(outframe, text=" ").grid(row = 1, column = 0)

#
centreframe = Frame(centrestrip)
centreframe.pack(side=LEFT, fill=BOTH, expand=YES)
centreframe.config(bd=5, relief=SUNKEN)

topcentre = Frame(centreframe)

topcentre1 = Frame(topcentre)
Label(topcentre1, text="     ").pack(side="left")
topcentre1.pack(side=LEFT, fill=X, expand=YES)
topcentre2 = Frame(topcentre)
topcentre2.pack(side=LEFT, fill=X)
topcentre3 = Frame(topcentre)
Label(topcentre3, text="     ").pack(side="left")
topcentre3.pack(side=LEFT, fill=X, expand=YES)

Label(topcentre2, text="     ").pack(side="left")
BLButt = Button(topcentre2, text="Bottom Left", command=donothing)
BLButt.pack(side=LEFT, padx=2, pady=2)
TLButt = Button(topcentre2, text="Top Left", command=donothing)
TLButt.pack(side=LEFT, padx=2, pady=2)
CentButt = Button(topcentre2, text="Centre", command=donothing)
CentButt.pack(side=LEFT, padx=2, pady=2)
TRButt = Button(topcentre2, text="Top Right", command=donothing)
TRButt.pack(side=LEFT, padx=2, pady=2)
BRButt = Button(topcentre2, text="Bottom Right", command=donothing)
BRButt.pack(side=LEFT, padx=2, pady=2)
Label(topcentre2, text="     ").pack(side="left")
topcentre.pack(side=TOP, fill=X)
##topcentre.config(bd = 5, relief = SUNKEN)

#
# *********** Canvas *********
#
canvasframe = Frame(centreframe)
c = Canvas(canvasframe, width=WINDOW, height=WINDOW, bg="light blue", cursor="crosshair", highlightthickness=0)
c.grid(row=0, column=0, sticky=N + S + E + W)
# allow the canvas to grow
canvasframe.grid_rowconfigure(0, weight=1)
canvasframe.grid_columnconfigure(0, weight=1)

# Scroll bars
xscrollbar = Scrollbar(canvasframe, orient=HORIZONTAL, command=c.xview)
xscrollbar.grid(row=1, column=0, sticky=E + W)
yscrollbar = Scrollbar(canvasframe, orient=VERTICAL, command=c.yview)
yscrollbar.grid(row=0, column=1, sticky=N + S)
c.configure(xscrollcommand=xscrollbar.set, yscrollcommand=yscrollbar.set)

# set scroll region
c.configure(scrollregion=(0, 0, WINDOW, WINDOW))

canvasframe.pack(side=TOP, fill=BOTH, expand=YES)
##canvasframe.config(bd = 5, relief = SUNKEN)

# canvas event bindings
c.bind("<Enter>", SetCanvasFocus)
c.bind("<Leave>", ClearCanvasFocus)
c.bind("<Motion>", showcoord)
c.bind("<Configure>", canvasframe_resize)
c.bind("<ButtonPress-1>", pan_start)
c.bind("<ButtonRelease-1>", pan_end)
c.bind("<B1-Motion>", pan_move)

# linux scroll
# c.bind("<Button-4>", zoomer_in)
# c.bind("<Button-5>", zoomer_out)

# windows scroll
c.bind("<MouseWheel>", zoomer)
c.bind("<Control-MouseWheel>", Canvas_ScrollX)
c.bind("<Shift-MouseWheel>", Canvas_ScrollY)

#
bottomcentre = Frame(centreframe)

bottomcentre1 = Frame(bottomcentre)
# Label(bottomcentre1, text="     ", width=15).pack(side="left")
Label(bottomcentre1, textvariable=scalelabel, width=20).pack(side=LEFT)
bottomcentre1.pack(side=LEFT, fill=X)

bottomcentre2 = Frame(bottomcentre)
Label(bottomcentre2, text="     ").pack(side="left")
bottomcentre2.pack(side=LEFT, fill=X, expand=YES)

bottomcentre3 = Frame(bottomcentre)
bottomcentre3.pack(side=LEFT, fill=X)

bottomcentre4 = Frame(bottomcentre)
Label(bottomcentre4, text="     ").pack(side="left")
bottomcentre4.pack(side=LEFT, fill=X, expand=YES)

bottomcentre5 = Frame(bottomcentre)
bottomcentre5.pack(side=RIGHT)

Label(bottomcentre3, text="     ").pack(side="left")
ZoominButt = Button(bottomcentre3, text="Zoom In", command=zoomin)
##ZoominButt.bind('<Button-1>',zoomin)
ZoominButt.pack(side=LEFT, padx=2, pady=2)
ZoomoutButt = Button(bottomcentre3, text="Zoom Out", command=zoomout)
##ZoomoutButt.bind('<Button-1>',zoomout)
ZoomoutButt.pack(side=LEFT, padx=2, pady=2)
FitScrButt = Button(bottomcentre3, text="Fit to Screen")
FitScrButt.bind('<Button-1>', autoscale)
FitScrButt.pack(side=LEFT, padx=2, pady=2)
FixtScrButt = Button(bottomcentre3, text="File Origin")
FixtScrButt.bind('<Button-1>', fixedscale)
FixtScrButt.pack(side=LEFT, padx=2, pady=2)
Label(bottomcentre3, text="     ").pack(side="left")
bottomcentre.pack(side=TOP, fill=X)

Label(bottomcentre5, textvariable=xycoord, width=20).pack(side=RIGHT)

rightframe = Frame(centrestrip)
##rightframe.grid(row = 1,column = 2, sticky = N + S)
rightframe.pack(side=LEFT, fill=BOTH)
rightframe.config(bd=5, relief=SUNKEN)
##rightframe.columnconfigure(2, weight = 1)
##rightframe.rowconfigure(1, weight = 1)

layerGeo = Frame(rightframe)
#majorGeo.grid(row = 0, column = 0, pady = 10, sticky = N)
layerGeo.pack(side=TOP, fill=BOTH, pady=5)
#
# majorGeo = Frame(rightframe)
# ##majorGeo.grid(row = 0, column = 0, pady = 10, sticky = N)
# majorGeo.pack(side=TOP, fill=BOTH, pady=5)
#
# Label(majorGeo, text="Copper View", anchor=W).grid(row=0, column=0)
# Label(majorGeo, text=" ").grid(row=1, column=0)
#
# coppermodes = [("Show Filled", 0),
#                ("Show Boundary", 1),
#                ("Clear All", 2)]
#
# for text, mode in coppermodes:
#     copperbtn = Radiobutton(majorGeo, text=text,
#                             variable=coppermode,
#                             value=mode,
#                             command=callplot,
#                             width=20,
#                             anchor=W)
#     copperbtn.grid(column=0, sticky=W)
#

#
# minorGeo = Frame(rightframe)
# ##minorGeo.grid(row = 1, column = 0, pady = 10, sticky = N)
# minorGeo.pack(side=TOP, fill=BOTH)
#
# Label(minorGeo, text=" ").grid(row=3, column=0)
# padbtn = Checkbutton(minorGeo, text="show pads", variable=showpad, width=20, command=callplot, anchor=W)
# padbtn.grid(row=4, column=0)
# trackbtn = Checkbutton(minorGeo, text="show track", variable=showtrack, width=20, command=callplot, anchor=W)
# trackbtn.grid(row=5, column=0)
# regionbtn = Checkbutton(minorGeo, text="show regions", variable=showregion, width=20, command=callplot, anchor=W)
# regionbtn.grid(row=6, column=0)

#
viewframe = Frame(rightframe)
##viewframe.grid(pady = 10, sticky = N)
viewframe.pack(side=BOTTOM, fill=BOTH)

Label(viewframe, text=" ").grid(row=0, column=0)
##Label(viewframe, text="xy display size:").grid(row = 12, column = 0, sticky = W)
##wxysize = Entry(viewframe, width=4, textvariable=sxysize)
##wxysize.grid(row = 12, column = 1, sticky = E + W)
##wxysize.bind('<Return>',plot)
Label(viewframe, text=" x min:").grid(row=13, column=0, sticky=W)
wxmin = Entry(viewframe, width=6, textvariable=sxmin)
wxmin.grid(row=13, column=1, sticky=E + W)
wxmin.bind('<Return>', plot)
Label(viewframe, text=" y min:").grid(row=14, column=0, sticky=W)
wymin = Entry(viewframe, width=6, textvariable=symin)
wymin.grid(row=14, column=1, sticky=E + W)
wymin.bind('<Return>', plot)
Label(viewframe, text=" xy scale factor:").grid(row=15, column=0, sticky=W)
wxyscale = Entry(viewframe, width=6, textvariable=sxyscale)
wxyscale.grid(row=15, column=1, sticky=E + W)
wxyscale.bind('<Return>', plot_delete)
sdxy = StringVar()
Label(viewframe, text=" ").grid(row=19, column=0)
Label(viewframe, textvariable=sdxy).grid(row=20, column=0, columnspan=2, sticky=E + W)

#
toolGeo = Frame(rightframe)
##toolGeo.grid(row = 2, column = 0, pady = 10, sticky = N)
toolGeo.pack(side=BOTTOM, fill=BOTH)

Label(toolGeo, text=" ").grid(row=0, column=0)
toolbtn = Checkbutton(toolGeo, text="show toolpaths", variable=showtoolpath, width=20, command=callplot, anchor=W)
toolbtn.grid(row=1, column=0)
toolbtn.select()
cutbtn = Checkbutton(toolGeo, text="show cutwidth", variable=showcuts, width=20, command=callplot, anchor=W)
cutbtn.grid(row=2, column=0)

#
statusframe = Frame(root, borderwidth=1, relief=SUNKEN)
status = StringVar()
version = StringVar()
status.set("Ok")
namedate = " LaZoR.py (" + VERSION + " " + DATE + ")  "
version.set(namedate)
Label(statusframe, text="Status:").pack(side=LEFT)
Label(statusframe, textvariable=status, width=40).pack(side=LEFT)
Label(statusframe, text="Board:").pack(side=LEFT)
Label(statusframe, textvariable=infilepcb, width=20).pack(side=LEFT)
Label(statusframe, text="").pack(side=LEFT, fill=X)
Label(statusframe, text="Edge:").pack(side=LEFT)
Label(statusframe, textvariable=infileedge, width=20).pack(side=LEFT)
Label(statusframe, text="").pack(side=LEFT, fill=X)
Label(statusframe, text="Drill:").pack(side=LEFT)
Label(statusframe, textvariable=infiledrill, width=20).pack(side=LEFT)
Label(statusframe, text="").pack(side=LEFT, fill=X, expand=YES)
Label(statusframe, textvariable=version, anchor=E).pack(side=RIGHT)
##statusframe.grid(row = 2, column = 0, sticky = S+E+W)
statusframe.pack(side=TOP, fill=X)
statusframe.config(bd=5, relief=SUNKEN)
##statusframe.resizable(width=FALSE, height=FALSE)
##statusframe.maxsize(statusframe.winfo_width(), statusframe.winfo_height())
#

#
boundarys=[[]]
toolpaths = [[]]
regions = [[]]
placeaxis = 1

#
# read input file and set up GUI
#
##if (infile.get() != ''):
##   read(0)
##else:
##   camselect(0)

#
# parse output command line arguments
#
##for i in range(len(sys.argv)):
##   if (find(sys.argv[i],"-f") != -1):
##      sforce.set(sys.argv[i+1])
##   elif (find(sys.argv[i],"-v") != -1):
##      svel.set(sys.argv[i+1])
##   elif (find(sys.argv[i],"-t") != -1):
##      sdia.set(sys.argv[i+1])
##   elif (find(sys.argv[i],"-a") != -1):
##      srate.set(sys.argv[i+1])
##   elif (find(sys.argv[i],"-e") != -1):
##      spower.set(sys.argv[i+1])
##   elif (find(sys.argv[i],"-s") != -1):
##      sspeed.set(sys.argv[i+1])
##   elif (find(sys.argv[i],"-h") != -1):
##      sheight.set(sys.argv[i+1])
##   elif (find(sys.argv[i],"-c") != -1):
##      contour(0)
##   elif (find(sys.argv[i],"-r") != -1):
##      raster(0)
##   elif (find(sys.argv[i],"-w") != -1):
##      write(0)
##      sys.exit()

#
# set up GUI
#
camselect(0)

#
# start GUI
#
root.config(menu=menubar)
root.update()
root.minsize(root.winfo_width(), root.winfo_height())
root.mainloop()
