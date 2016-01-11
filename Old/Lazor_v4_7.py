#!/usr/bin/env python
#
# LaZoR.py
#
# Damien Hill and Ben Saunders
#
#--------------------------------------------------
# v2.1 - 16/5/15
# > Added new coord function for handling arcs (I and J)
# > Added initial support for arc interpolation
# > Improved GUI layout
#--------------------------------------------------
# v2.2 - 19/5/15
# > Implemented Minkowski sum for aperture interpolation (circular aperture only)

VERSION = "v4.7"
DATE = "19/5/15"

##prompt = \
##"""modes: 1D path following, 2D contour and raster, 3D slicing
##input:
##   *.cmp,*.sol,*.via,*.mill: Gerber
##      RS-274X format, with 0-width trace defining board boundary
##   *.drl, *.drd: Excellon (with embedded drill defitions)
##output:
##   *.g: G codes
##   *.l: LaZoR file
##keys: Q to quit
##usage: python cam.py [[-i] infile][-d display scale][-p part scale][-x xmin][-y ymin][-o outfile][-f force][-v velocity][-t tooldia][-a rate][-e power][-s speed][-h height][-c contour][-r raster][-n no noise][-# number of arc segments][-j jobname][-w write toolpath]
##"""

from Tkinter import *
from tkFileDialog import *
from string import *
from math import *

import pyclipper

DPI = 25400
#
# numerical roundoff tolerance for testing intersections
#
EPS = 1e-20
#
# relative std dev of numerical noise to add to remove degeneracies
#
NOISE = 1e-6
noise_flag = 1

HUGE = 1e10

Xpos = 0
Ypos = 1

START = 0
END = 1
EVENT_SEG = 3
EVENT_VERT = 4

SEG = 0
VERT = 1
A = 1

TYPE = 0
SIZE = 1
WIDTH = 1
HEIGHT = 2

def coord(str,digits,fraction):
   #
   # parse Gerber coordinates
   #
   # > modified to handle I and J coordinates
   # > Made robust to missing coordinates as per gerber standard
   #
   global gerbx, gerby
   xindex = find(str,"X")
   yindex = find(str,"Y")
   iindex = find(str,"I")
   jindex = find(str,"J")
   index = find(str,"D")
   # i and j are zero if not given
   # gerbx and gerby maintain their last values
   i = 0
   j = 0
   # Check for each of the coordinates and read out the following number
   if (xindex != -1):
      gerbx = int(re.search(r'[-+]?\d+', str[(xindex+1):index]).group())
   if (yindex != -1):
      gerby = int(re.search(r'[-+]?\d+', str[(yindex+1):index]).group())
   if (iindex != -1):
      i = int(re.search(r'[-+]?\d+', str[(iindex+1):index]).group())
   if (jindex != -1):
      j = int(re.search(r'[-+]?\d+', str[(jindex+1):index]).group())
   return [gerbx,gerby,i,j]

def read_Gerber(filename):
   global boundarys,regions,fraction_g
   #
   # Gerber parser
   #
   file = open(filename,'r')
   str = file.readlines()
   file.close()
   nlines = len(str)
   trackseg = -1
   padseg = -1
   regionseg = -1
   edgeseg = -1
   xold = []
   yold = []
   line = 0
   track = []
   tracksize = []
   pad = []
   region = []
   pcb_edge = []
   macros = []
   N_macros = 0
   apertures = [[] for i in range(1000)]
   appsize = [[] for i in range(1000)]
   interpMode = 1
   arcMode = 0
   regionMode = 0

   while line < nlines:
      if (find(str[line],"%FS") != -1):
         #
         # format statement
         #
         index = find(str[line],"X")
         digits = int(str[line][index+1])
         fraction = int(str[line][index+2])
         fraction_g = fraction
         line += 1
         continue
      elif (find(str[line],"%AM") != -1):
         #
         # aperture macro
         #
         index = find(str[line],"%AM")
         index1 = find(str[line],"*")
         macros.append([])
         macros[-1] = str[line][index+3:index1]
         N_macros += 1
         line += 1
         continue
      elif (find(str[line],"%MOIN*%") != -1):
         #
         # inches
         #
         line += 1
         continue
      elif (find(str[line],"G01*") != -1):
         #
         # linear interpolation
         #
         interpMode = 1
         line += 1
         continue
      elif (find(str[line],"G02*") != -1):
         #
         # Set clockwise circular interpolation
         #
         interpMode = 2
         line += 1
         continue
      elif (find(str[line],"G03*") != -1):
         #
         # Set counterclockwise circular interpolation
         #
         interpMode = 3
         line += 1
         continue
      elif (find(str[line],"G70*") != -1):
         #
         # set unit to inches - deprecated command
         #
         print "   G70 command ignored (deprecated)"
         line += 1
         continue
      elif (find(str[line],"G71*") != -1):
         #
         # set unit to mm - deprecated command
         #
         print "   G71 command ignored (deprecated)"
         line += 1
         continue
      elif (find(str[line],"G74*") != -1):
         #
         # Set single quadrant circular interpolation
         #
         arcMode = 1
         line += 1
         continue
      elif (find(str[line],"G75*") != -1):
         #
         # Set multi quadrant circular interpolation
         #
         arcMode = 2
         line += 1
         continue
      elif (find(str[line],"G90*") != -1):
         #
         # set absolute coordinate format - deprecated command
         #
         print "   G90 command ignored (deprecated)"
         line += 1
         continue
      elif (find(str[line],"G91*") != -1):
         #
         # set incremental coordinate format - deprecated command
         #
         print "   G91 command ignored (deprecated)"
         line += 1
         continue
      elif (find(str[line],"%ADD") != -1):
         #
         # aperture definition
         #
         index = find(str[line],"%ADD")
         parse = 0
         if (find(str[line],"C,") != -1):
            #
            # circle
            #
            index = find(str[line],"C,")
            index1 = find(str[line],"*")
            aperture = int(str[line][4:index])
            size = float(str[line][index+2:index1])*(10**(fraction))
            appsize[aperture] = size
            for i in range(nverts):
               angle = i*2.0*pi/(nverts-1.0)
               x = (size/2.0)*cos(angle)
               y = (size/2.0)*sin(angle)
               apertures[aperture].append([x,y])

            print "   read aperture",aperture,": circle diameter",size
            line += 1
            continue

         elif (find(str[line],"O,") != -1):
            #
            # obround
            #
            index = find(str[line],"O,")
            aperture = int(str[line][4:index])
            index1 = find(str[line],",",index)
            index2 = find(str[line],"X",index)
            index3 = find(str[line],"*",index)
            width = float(str[line][index1+1:index2])*(10**(fraction))
            height = float(str[line][index2+1:index3])*(10**(fraction))

            if (width > height):
               for i in range(nverts/2):
                  angle = i*pi/(nverts/2-1.0) + pi/2.0
                  x = -(width-height)/2.0 + (height/2.0)*cos(angle)
                  y = (height/2.0)*sin(angle)
                  apertures[aperture].append([x,y])
               for i in range(nverts/2):
                  angle = i*pi/(nverts/2-1.0) - pi/2.0
                  x = (width-height)/2.0 + (height/2.0)*cos(angle)
                  y = (height/2.0)*sin(angle)
                  apertures[aperture].append([x,y])
            else:
               for i in range(nverts/2):
                  angle = i*pi/(nverts/2-1.0) + pi
                  x = (width/2.0)*cos(angle)
                  y = -(height-width)/2.0 + (width/2.0)*sin(angle)
                  apertures[aperture].append([x,y])
               for i in range(nverts/2):
                  angle = i*pi/(nverts/2-1.0)
                  x = (width/2.0)*cos(angle)
                  y = (height-width)/2.0 + (width/2.0)*sin(angle)
                  apertures[aperture].append([x,y])

            print "   read aperture",aperture,": obround",width,"x",height
            line += 1
            continue

         elif (find(str[line],"R,") != -1):
            #
            # rectangle
            #
            index = find(str[line],"R,")
            aperture = int(str[line][4:index])
            index1 = find(str[line],",",index)
            index2 = find(str[line],"X",index)
            index3 = find(str[line],"*",index)

            width = float(str[line][index1+1:index2])*(10**(fraction))/ 2.0
            height = float(str[line][index2+1:index3])*(10**(fraction))/ 2.0

            apertures[aperture].append([-width,-height])
            apertures[aperture].append([+width,-height])
            apertures[aperture].append([+width,+height])
            apertures[aperture].append([-width,+height])
            apertures[aperture].append([-width,-height])

            print "   read aperture",aperture,": rectangle",width,"x",height
            line += 1
            continue

         for macro in range(N_macros):
            #
            # macros
            #
            index = find(str[line],macros[macro]+',')
            if (index != -1):
               #
               # hack: assume macros can be approximated by
               # a circle, and has a size parameter
               #
               aperture = int(str[line][4:index])
               index1 = find(str[line],",",index)
               index2 = find(str[line],"*",index)
               size = float(str[line][index1+1:index2])*(10**(fraction))
               appsize[aperture] = size
               for i in range(nverts):
                  angle = i*2.0*pi/(nverts-1.0)
                  x = (size/2.0)*cos(angle)
                  y = (size/2.0)*sin(angle)
                  apertures[aperture].append([x,y])
               print "   read aperture",aperture,": macro (assuming circle) diameter",size
               parse = 1
               continue
            if (parse == 0):
               print "   aperture not implemented:",str[line]
               return

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

      elif (find(str[line],"D01*") != -1):
         #
         # interpolate operation
         #
         # First check if we need to change the interpolate mode
         if (find(str[line],"G01") != -1):
            interpMode = 1
         elif (find(str[line],"G02") != -1):
            interpMode = 2
         elif (find(str[line],"G03") != -1):
            interpMode = 3
         # Now do the interpolate operation
         if (interpMode == 1):
            #
            # linear interpolate
            #
            [xnew,ynew,iarc,jarc] = coord(str[line],digits,fraction)

            if ((abs(xnew-xold) > EPS) | (abs(ynew-yold) > EPS)):
               if regionMode == 0:
                  track[trackseg].append([xnew,ynew])
               elif regionMode == 1:
                  region[regionseg].append([xnew,ynew])

            xold = xnew
            yold = ynew
            line += 1
            continue

         elif (interpMode == 2):
            #
            # CW circular interpolate
            #
            # just ignore for now
            line += 1
            continue
         elif (interpMode == 3):
            #
            # CCW circular interpolate
            #
            [xnew,ynew,iarc,jarc] = coord(str[line],digits,fraction)
            radius = sqrt(pow(iarc,2)+pow(jarc,2))
            centreX = xold + iarc
            centreY = yold + jarc
            startAngle = atan2(yold-centreY,xold-centreX)
            endAngle = atan2(ynew-centreY,xnew-centreX)

            if (startAngle < endAngle):
               angleStep = (endAngle-startAngle)/(nverts-1.0)
            else:
               angleStep = (endAngle+2.0*pi-startAngle)/(nverts-1.0)
            print ""
            print "   Plotting arc:"
            print "   arc centre (i,j) = ",iarc,",",jarc
            print "   arc centre (x,y) = ",centreX,",",centreY
            print "   arc radius = ",radius
            print "   start angle = ",startAngle
            print "   end angle = ",endAngle
            print "   angle step = ",angleStep


            if ((abs(xnew-xold) > EPS) | (abs(ynew-yold) > EPS)):
               for i in range(nverts):
                  xarcseg = centreX + radius*cos(startAngle+angleStep*i)
                  yarcseg = centreY + radius*sin(startAngle+angleStep*i)
                  xarcseg = round(xarcseg)
                  yarcseg = round(yarcseg)
                  if regionMode == 0:
                     track[trackseg].append([xarcseg,yarcseg])
                  elif regionMode == 1:
                     region[regionseg].append([xarcseg,yarcseg])

            xold = xnew
            yold = ynew
            line += 1
            continue
         continue

      elif (find(str[line],"D02*") != -1):
         #
         # Move operation
         #
         [xold,yold,iarc,jarc] = coord(str[line],digits,fraction)

         if regionMode == 0:
            track.append([])
            tracksize.append(aperture)
            trackseg += 1
            track[trackseg].append([xold,yold])
         elif regionMode == 1:
            region.append([])
            regionseg += 1
            region[regionseg].append([xold,yold])
         line += 1
         continue

      elif (find(str[line],"D03*") != -1):
         #
         # Flash operation
         #
         if (find(str[line],"D03*") == 0):
            #
            # coordinates on preceeding line
            #
            [xnew,ynew] = [xold,yold]
         else:
            #
            # coordinates on this line
            #
            [xnew,ynew,iarc,jarc] = coord(str[line],digits,fraction)
         line += 1
         pad.append([])
         padseg += 1

         for verts in apertures[aperture]:
            pad[padseg].append([xnew + verts[Xpos],ynew + verts[Ypos]])

         xold = xnew
         yold = ynew
         continue

      elif (find(str[line],"D") == 0):
         #
         # change aperture
         #
         index = find(str[line],'*')
         aperture = int(str[line][1:index])
         size = apertures[aperture][SIZE]
         line += 1
         continue
      elif (find(str[line],"G54D") == 0):
         #
         # change aperture
         #
         index = find(str[line],'*')
         aperture = int(str[line][4:index])
         size = apertures[aperture][SIZE]
         line += 1
         continue
      elif (find(str[line],"G36") == 0):
         #
         # region ON
         #

         regionMode = 1
         line += 1
         continue

      elif (find(str[line],"G37") == 0):
         #
         # region OFF
         #

         regionMode = 0
         line += 1
         continue

      elif (find(str[line],"M02") == 0):
         #
         # File End
         #

         print "End of file"
         break

      else:
         print "   not parsed:",str[line]
      line += 1

   readstuff = [[] for i in xrange(5)]
   readstuff[0].extend(pad)
   readstuff[1].extend(track)
   readstuff[2].extend(tracksize)
   readstuff[3].extend(apertures)
   readstuff[4].extend(region)

   return readstuff

def read_Excellon(filename):
   global boundarys
   #
   # Excellon parser
   #
   file = open(filename,'r')
   str = file.readlines()
   file.close()
   segment = -1
   line = 0
   nlines = len(str)
   boundary = []
   header = TRUE
   drills = [[] for i in range(1000)]
   while line < nlines:
      if ((find(str[line],"T") != -1) & (find(str[line],"C") != -1) \
         & (find(str[line],"F") != -1)):
         #
         # alternate drill definition style
         #
         index = find(str[line],"T")
         index1 = find(str[line],"C")
         index2 = find(str[line],"F")
         drill = int(str[line][1:index1])
         print str[line][index1+1:index2]
         size = float(str[line][index1+1:index2])
         drills[drill] = ["C",size]
         print "   read drill",drill,"size:",size
         line += 1
         continue
      if ((find(str[line],"T") != -1) & (find(str[line]," ") != -1) \
         & (find(str[line],"in") != -1)):
         #
         # alternate drill definition style
         #
         index = find(str[line],"T")
         index1 = find(str[line]," ")
         index2 = find(str[line],"in")
         drill = int(str[line][1:index1])
         print str[line][index1+1:index2]
         size = float(str[line][index1+1:index2])
         drills[drill] = ["C",size]
         print "   read drill",drill,"size:",size
         line += 1
         continue
      elif ((find(str[line],"T") != -1) & (find(str[line],"C") != -1)):
         #
         # alternate drill definition style
         #
         index = find(str[line],"T")
         index1 = find(str[line],"C")
         drill = int(str[line][1:index1])
         size = float(str[line][index1+1:-1])
         drills[drill] = ["C",size]
         print "   read drill",drill,"size:",size
         line += 1
         continue
      elif (find(str[line],"T") == 0):
         #
         # change drill
         #
         index = find(str[line],'T')
         drill = int(str[line][index+1:-1])
         size = drills[drill][SIZE]
         line += 1
         continue
      elif (find(str[line],"X") != -1):
         #
         # drill location
         #
         index = find(str[line],"X")
         index1 = find(str[line],"Y")
         x0 = float(int(str[line][index+1:index1])/10000.0)
         y0 = float(int(str[line][index1+1:-1])/10000.0)
         line += 1
         boundary.append([])
         segment += 1
         size = drills[drill][SIZE]
         for i in range(nverts):
            angle = -i*2.0*pi/(nverts-1.0)
            x = x0 + (size/2.0)*cos(angle)
            y = y0 + (size/2.0)*sin(angle)
            boundary[segment].append([x,y,[]])
         continue
      else:
         print "   not parsed:",str[line]
      line += 1
   boundarys[0] = boundary

def read_pcb():
   global vertices, faces, boundarys, toolpaths, contours, slices,\
      xmin, xmax, ymin, ymax, zmin, zmax, noise_flag,tracks
   #
   # read pcbfile
   #
   definedFileTypes = [('gerber','.gbl .gtl .gbr .cmp'),\
                       ('drill files','.drl .dbd'),('all files','.*')]
   filename = askopenfilename(filetypes=definedFileTypes)
##   infile.set(filename)
##   read(0)
##   filename = infile.get()

############

   if ((find(filename,".cmp") != -1) | (find(filename,".CMP")!= -1) \
      | (find(filename,".gtl")!= -1) | (find(filename,".GTL") != -1) \
      | (find(filename,".gbl")!= -1) | (find(filename,".GBL")!= -1)):
      print "reading Gerber file",filename
      contours = [[]]
      boundarys = [[]]
      toolpaths = [[]]

      infilepcb.set('')
      infileedge.set('')
      infiledrill.set('')

      if (find(filename,".") != -1):
         index2 = find(filename,".")
         if (find(filename,"/") != -1):
            index1 = find(filename,"/")
            while(find(filename[index1+1:index2],"/") != -1):
               index1 = index1+1+find(filename[index1+1:index2],"/")
            infilepcb.set(filename[index1+1:index2])

      readstuff = read_Gerber(filename)

      pad = readstuff[0]
      tracks[0] = readstuff[1]
      tracksize = readstuff[2]
      apertures = readstuff[3]
      regions[0] = readstuff[4]
      singletrack = [[]]
      temp = []
      track_outlines = []


      # Expand tracks from centrelines based on aperture
      for seg in range(len(tracks[0])):
         for vert in range(len(tracks[0][seg])-1):
            xstart = tracks[0][seg][vert][0]
            xend = tracks[0][seg][vert+1][0]
            ystart = tracks[0][seg][vert][1]
            yend = tracks[0][seg][vert+1][1]
            singletrack = pyclipper.MinkowskiSum(apertures[tracksize[seg]],\
                                                [[xstart,ystart],[xend,yend]],-1)
            if len(singletrack) > 1:
               biggest = []
               myarea = 0
               for mypath in singletrack:
                  newarea = pyclipper.Area(mypath)
                  if newarea > myarea:
                      biggest = mypath
                      myarea =newarea
   ##            print biggest
               singletrack = [[]]
               singletrack[0]=(biggest)
            track_outlines.extend(singletrack)





      tracks[0] = track_outlines
      pads[0] = pad


      # boundarys contains both pad and track outlines
      pcb_edges[0] = []
      boundarys[0].extend(pads[0])
      boundarys[0].extend(tracks[0])
      union_boundary(0)

      status.set("Gerber read ok")
      read(0)

#############

def read_edge():
   global vertices, faces, boundarys, toolpaths, contours, slices,\
      xmin, xmax, ymin, ymax, zmin, zmax, noise_flag,tracks
   #
   # read edge file
   #
   definedFileTypes = [('gerber','.gbl .gtl .gbr .cmp'),\
                       ('drill files','.drl .dbd'),('all files','.*')]
   filename = askopenfilename(filetypes=definedFileTypes)

   if ((find(filename,".gbr")!= -1) | (find(filename,".GBR")!= -1)):
      print "reading PCB edge file",filename

      readstuff = read_Gerber(filename)
##      pcb_edges[0] = readstuff[1]
##      pcb_edges = [[]]
      brdoutline = []
      startpnt = []
      endpnt = []
      brdseg = -1

      while len(readstuff[1]) > 0:
         brdoutline.append([])
         brdseg += 1
         brdoutline[brdseg].extend(readstuff[1][0])
         readstuff[1].remove(readstuff[1][0])
         startpnt = brdoutline[brdseg][0]
         endpnt = brdoutline[brdseg][len(brdoutline[brdseg])-1]

         while(abs(startpnt[0]-endpnt[0]) > 10) | (abs(startpnt[1]-endpnt[1]) > 10):
            for seg in readstuff[1]:
               if abs(seg[0][0]-endpnt[0]) < 10:
                  if abs(seg[0][1]-endpnt[1]) < 10:
                     brdoutline[brdseg].extend(seg)
                     readstuff[1].remove(seg)
                     endpnt = brdoutline[brdseg][len(brdoutline[brdseg])-1]
                     continue
               if abs(seg[len(seg)-1][0]-endpnt[0]) < 10:
                  if abs(seg[len(seg)-1][1]-endpnt[1]) < 10:
                     readstuff[1].remove(seg)
                     seg = seg[::-1]
                     brdoutline[brdseg].extend(seg)
                     endpnt = brdoutline[brdseg][len(brdoutline[brdseg])-1]

      pcb_edges[0] = brdoutline

      pcb_edges[0] = pyclipper.CleanPolygons(pcb_edges[0])

      toolpaths = [[]]

      if (find(filename,".") != -1):
         index2 = find(filename,".")
         if (find(filename,"/") != -1):
            index1 = find(filename,"/")
            while(find(filename[index1+1:index2],"/") != -1):
               index1 = index1+1+find(filename[index1+1:index2],"/")
            infileedge.set(filename[index1+1:index2])

      read(0)

###################
def read_drill():
   global vertices, faces, boundarys, toolpaths, contours, slices,\
      xmin, xmax, ymin, ymax, zmin, zmax, noise_flag,tracks
   #
   # read drill file
   #
   definedFileTypes = [('gerber','.gbl .gtl .gbr .cmp'),\
                       ('drill files','.drl .dbd'),('all files','.*')]
   filename = askopenfilename(filetypes=definedFileTypes)

   if ((find(filename,".drl") != -1) | (find(filename,".DRL") != -1) | \
      (find(filename,".drd") != -1) | (find(filename,".DRD") != -1)):
      print "reading Excellon file",filename
      read_Excellon(filename)

      infiledrill.set(filename)

##################

   else:
      print "unsupported file type"
      status.set("Unsupported file type")
      return
   read(0)

def read(event):
   global vertices, faces, boundarys, toolpaths, contours, slices,\
      xmin, xmax, ymin, ymax, zmin, zmax, noise_flag,tracks

   xmin = HUGE
   xmax = -HUGE
   ymin = HUGE
   ymax = -HUGE
   zmin = HUGE
   zmax = -HUGE

   boundary = boundarys[0]
   region = regions[0]
   pcb_edge = pcb_edges[0]
   edgelimit = []
   sum1 = 0

   if len(pcb_edge) == 0:
      edgelimit = boundary
   else:
      edgelimit = pcb_edge

   for segment in edgelimit:
      sum1 += len(segment)
      for vertex in segment:
         x = vertex[0]*(10**(-fraction_g))
         y = vertex[1]*(10**(-fraction_g))
         if (x < xmin): xmin = x
         if (x > xmax): xmax = x
         if (y < ymin): ymin = y
         if (y > ymax): ymax = y
   print "   found",len(boundary),"polygons,",sum1,"vertices"
   print "   found",len(region),"pours"
   print "   found",len(pcb_edges[0]),"edge segments"
   print "   xmin: %0.3g "%xmin,"xmax: %0.3g "%xmax,"dx: %0.3g "%(xmax-xmin)
   print "   ymin: %0.3g "%ymin,"ymax: %0.3g "%ymax,"dy: %0.3g "%(ymax-ymin)

   boundarys[0] = boundary
   regions[0] = region

   outer_offset = 0.01

   if len(pcb_edges[0]) == 0:
      pcb_edge=[[]]
      xmax += outer_offset
      ymax += outer_offset
      xmin -= outer_offset
      ymin -= outer_offset
      pcb_edge[0].append([xmax/(10**(-fraction_g)),ymax/(10**(-fraction_g))])
      pcb_edge[0].append([xmax/(10**(-fraction_g)),ymin/(10**(-fraction_g))])
      pcb_edge[0].append([xmin/(10**(-fraction_g)),ymin/(10**(-fraction_g))])
      pcb_edge[0].append([xmin/(10**(-fraction_g)),ymax/(10**(-fraction_g))])
      pcb_edges[0].extend(pcb_edge)

   camselect(event)
   plot(event)
#   plot_delete(event)

def autoscale(event):
   global xmax, xmin, ymax, ymin, zmax, zmin, fixed_size
   #
   # fit window to object
   #
   xyscale = float(sxyscale.get())
   sxmin.set("0")
   symin.set("0")

   if ((ymax-ymin) > (xmax-xmin)):
      sxysize.set(str(xyscale*(round(ymax-ymin,2))))
   else:
      sxysize.set(str(xyscale*(round(xmax-xmin,2))))

   fixed_size = True
   #plot_delete(event)
   plot(event)

def fixedscale(event):
   global xmax, xmin, ymax, ymin, zmax, zmin, fixed_size
   #
   # show object at original scale and location
   #
   fixed_size = False
   camselect(event)
   xyscale = float(sxyscale.get())
   sxmin.set(str(xmin*xyscale))
   symin.set(str(ymin*xyscale))
   #plot_delete(event)
   plot(event)

def plot(event):
   global vertices, faces, boundarys, toolpaths, \
      xmin, xmax, ymin, ymax, zmin, zmax, regions, showregion
   #
   # scale and plot object and toolpath
   # > updated to plot a closed path
   #
   print "plotting"
   xysize = float(sxysize.get())
   #zsize = float(szsize.get())
   xyscale = float(sxyscale.get())
   #zscale = float(szscale.get())
##   xoff = float(sxmin.get()) - xmin*xyscale
##   yoff = float(symin.get()) - ymin*xyscale
##   zoff = float(szmax.get()) - zmax*zscale
   if placeaxis == 1:
      xoff = float(sxmin.get()) - xmin*xyscale
      yoff = float(symin.get()) - ymin*xyscale
   elif placeaxis == 2:
      xoff = float(sxmin.get()) - xmin*xyscale
      yoff = float(symin.get()) - ymax*xyscale
   elif placeaxis == 3:
      xoff = float(sxmin.get()) - xmax*xyscale
      yoff = float(symin.get()) - ymax*xyscale
   elif placeaxis == 4:
      xoff = float(sxmin.get()) - xmax*xyscale
      yoff = float(symin.get()) - ymin*xyscale
   else:
      xoff_export = float(sxmin.get()) - (xmin + (xmax - xmin)/2)*xyscale
      yoff_export = float(symin.get()) - (ymin + (ymax - ymin)/2)*xyscale
      xoff = xoff_export + float(sxysize.get())/2
      yoff = yoff_export + float(sxysize.get())/2

   sdxy.set("  dx:%6.3f  dy:%6.3f"%((xmax-xmin)*xyscale,(ymax-ymin)*xyscale))
   #sdz.set("  dz:%6.3f"%((zmax-zmin)*zscale))
   #vert = ivert.get()
   vert = 0

   # Clear the plots
   c.delete("plot_boundary")
   c.delete("plot_pcb_edges")
   c.delete("plot_path")

   c.delete("plot_pads")
   c.delete("plot_tracks")
   c.delete("plot_regions")
   c.delete("plot_origin")

   #
   # plot copper
   #
   curcoppermode = coppermode.get()

   if (curcoppermode == 1):
      for seg in boundarys[0]:
         if len(seg) > 0:

            path_plot = []
            for vertex in seg:
               xplot = int((vertex[0]*(10**(-fraction_g))*xyscale + xoff)*DPI)
               path_plot.append(xplot)
##               yplot = (WINDOW-1) - int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               yplot = -int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               path_plot.append(yplot)
##               if (vert == 1):
##                  c.create_text(xplot,yplot,text=str(seg)+':'+str(vertex),tag="plot_boundary")
##            if len(path_plot) > 0:
            path_plot.append(path_plot[0])
            path_plot.append(path_plot[1])
            c.create_line(path_plot,tags=("plot_boundary","PlotObjects"),fill = "blue")

   elif (curcoppermode == 0):

      for seg in pads[0]:
         if len(seg) > 0:
            path_plot = []
            for vertex in seg:
               xplot = int((vertex[0]*(10**(-fraction_g))*xyscale + xoff)*DPI)
               path_plot.append(xplot)
##               yplot = (WINDOW-1) - int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               yplot = -int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               path_plot.append(yplot)
            path_plot.append(path_plot[0])
            path_plot.append(path_plot[1])
            c.create_polygon(path_plot,tags=("plot_pads","PlotObjects"),fill="dark green",activefill = "yellow")

      for seg in tracks[0]:
         if len(seg) > 0:
            path_plot = []
            for vertex in seg:
               xplot = int((vertex[0]*(10**(-fraction_g))*xyscale + xoff)*DPI)
               path_plot.append(xplot)
##               yplot = (WINDOW-1) - int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               yplot = - int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               path_plot.append(yplot)
            path_plot.append(path_plot[0])
            path_plot.append(path_plot[1])
            c.create_polygon(path_plot,tags=("plot_tracks","PlotObjects"),fill="dark green",activefill = "yellow")

      for seg in regions[0]:
         if len(seg) > 0:
            path_plot = []
            for vertex in seg:
               xplot = int((vertex[0]*(10**(-fraction_g))*xyscale + xoff)*DPI)
               path_plot.append(xplot)
##               yplot = (WINDOW-1) - int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               yplot = -int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               path_plot.append(yplot)
            path_plot.append(path_plot[0])
            path_plot.append(path_plot[1])
            c.create_polygon(path_plot,tags=("plot_regions","PlotObjects"),fill="dark green",activefill = "yellow")

   #
   # plot PCB edges segments
   #
   for seg in pcb_edges[0]:
      path_plot = []
      for vertex in seg:
         xplot = int((vertex[0]*(10**(-fraction_g))*xyscale + xoff)*DPI)
         path_plot.append(xplot)
##         yplot = (WINDOW-1) - int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
         yplot = -int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
         path_plot.append(yplot)
##         if (vert == 1):
##            c.create_text(xplot,yplot,text=str(seg)+':'+str(vertex),tag="plot_pcb_edges")
      path_plot.append(path_plot[0])
      path_plot.append(path_plot[1])
      c.create_line(path_plot,tags=("plot_pcb_edges","PlotObjects"),fill="blue")
   #
   # plot toolpath segments
   #
   showtoolpaths = showtoolpath.get()
   cutwidth = showcuts.get()
   if cutwidth == 0:
      linewidth = 0
   else:
      linewidth =ceil(((float(sdia.get())))*DPI)


   if (showtoolpaths == 1):
      for seg in range(len(toolpaths[0])):
         if len(toolpaths[0][seg]) > 0:

            path_plot = []

            for vertex in range (len(toolpaths[0][seg])):
               xplot = int((toolpaths[0][seg][vertex][Xpos]*(10**(-fraction_g))*xyscale + xoff)*DPI)
               path_plot.append(xplot)
##               yplot = (WINDOW-1) - int((toolpaths[0][seg][vertex][Ypos]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               yplot = -int((toolpaths[0][seg][vertex][Ypos]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               path_plot.append(yplot)
##               if (vert == 1):
##                  c.create_text(xplot,yplot,text=str(seg)+':'+str(vertex),tag="plot_path")
##            if len(path_plot) > 0:
##               path_plot.append(path_plot[0])
##               path_plot.append(path_plot[1])
            c.create_line(path_plot,tags=("plot_path","PlotObjects"),fill="red", width = linewidth,\
                           capstyle = "round")
   #
   # plot pads
   #
   showpads = showpad.get()

   if (showpads == 1):
      for seg in pads[0]:
         if len(seg) > 0:
            path_plot = []
            for vertex in seg:
               xplot = int((vertex[0]*(10**(-fraction_g))*xyscale + xoff)*DPI)
               path_plot.append(xplot)
               yplot = - int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               path_plot.append(yplot)
##               if (vert == 1):
##                  c.create_text(xplot,yplot,text=str(seg)+':'+str(vertex),tag="plot_pads")
            path_plot.append(path_plot[0])
            path_plot.append(path_plot[1])
            c.create_polygon(path_plot,tags=("plot_pads","PlotObjects"),fill="yellow")

   #
   # plot tracks
   #
   showtracks = showtrack.get()

   if (showtracks == 1):
      for seg in tracks[0]:
         if len(seg) > 0:
            path_plot = []
            for vertex in seg:
               xplot = int((vertex[0]*(10**(-fraction_g))*xyscale + xoff)*DPI)
               path_plot.append(xplot)
               yplot = - int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               path_plot.append(yplot)
##               if (vert == 1):
##                  c.create_text(xplot,yplot,text=str(seg)+':'+str(vertex),tag="plot_trackss")
            path_plot.append(path_plot[0])
            path_plot.append(path_plot[1])
            c.create_polygon(path_plot,tags=("plot_tracks","PlotObjects"),fill="yellow")

   #
   # plot regions
   #
   showregions = showregion.get()

   if (showregions == 1):
      for seg in regions[0]:
         if len(seg) > 0:
            path_plot = []
            for vertex in seg:
               xplot = int((vertex[0]*(10**(-fraction_g))*xyscale + xoff)*DPI)
               path_plot.append(xplot)
               yplot = - int((vertex[1]*(10**(-fraction_g))*xyscale + yoff)*DPI)
               path_plot.append(yplot)
##               if (vert == 1):
##                  c.create_text(xplot,yplot,text=str(seg)+':'+str(vertex),tag="plot_regions")
            path_plot.append(path_plot[0])
            path_plot.append(path_plot[1])
            c.create_polygon(path_plot,tags=("plot_regions","PlotObjects"),fill="yellow")
   #
   # mark origin
   #
   c.create_line([(-20,0),(20,0)],tags=("plot_origin","CanvasObjects"),fill="orange",width = 3)
   c.create_line([(0,-20),(0,20)],tags=("plot_origin","CanvasObjects"),fill="orange",width = 3)
   c.create_oval(-10, -10, 10, 10, tags=("plot_origin","CanvasObjects"),outline="orange",width = 3)

   # Update canvas scroll region to fit everything we have just plotted
   c.configure(scrollregion = c.bbox("PlotObjects"))


def plot_delete(event):
   global boundarys, toolpaths, contours, regions
   #
   # scale and plot boundary, delete toolpath
   #
   for layer in range(len(toolpaths)):
      toolpaths[layer] = []
      contours[layer] = []

   print "deleted toolpath"
   plot(event)


def offset_poly(path, toolrad):

   c_osp = pyclipper.PyclipperOffset()
   c_osp.AddPaths(path,pyclipper.JT_SQUARE, pyclipper.ET_CLOSEDPOLYGON)
   polyclip = c_osp.Execute(toolrad)

   polyclip = pyclipper.CleanPolygons(polyclip)


   c_osp.Clear()
   return polyclip


def union(paths,union_type = pyclipper.PFT_NONZERO):
   #
   #
   # performs union on list, or list of lists
   #
   #

   c = pyclipper.Pyclipper()

   polyclip = paths

   for path in range(len(polyclip)):
      c.AddPaths(polyclip[path], pyclipper.PT_SUBJECT,True)
   polyclip = c.Execute(pyclipper.CT_UNION, union_type, union_type)
   c.Clear()

   return polyclip

def union_boundary(event):
   #global boundary, intersections
   #
   # union intersecting polygons on boundary
   #
   print "union boundary ..."

   region = []
   paths = [[]]
   boundary = union(boundarys,pyclipper.PFT_NONZERO)
   paths[0] = boundary
   if (len(regions[0]) > 0):
      region = union(regions,pyclipper.PFT_NONZERO)
      paths.append(region)
      boundary = union(paths,pyclipper.PFT_NONZERO)
   #regions[0] = []

   boundary = pyclipper.CleanPolygons(boundary)
   #boundary = pyclipper.SimplifyPolygons(boundary)
   for segs in boundary:
      if len(segs) == 0:
         boundary.remove([])
         break

   boundarys[0] = boundary

   print "   done"
   status.set("Union done")
   plot(event)



def contour(event):
   global boundarys, toolpaths, contours, regions
   #
   # contour boundary to find toolpath
   #
   print "contouring boundary ..."
   xyscale = float(sxyscale.get())
   N_contour = int(sncontour.get())
   overlap = float(sundercut.get())

   boundary = boundarys[0]
   pcb_edge = pcb_edges[0]
   toolpaths[0] = []

   c5 = pyclipper.PyclipperOffset()

   for n in range(1,N_contour+1):
      if n == 1:
         toolrad = (n)*((float(sdia.get())/2.0)/xyscale)*(10**fraction_g)
      else:
         toolrad += ((float(sdia.get())/2.0)*overlap/xyscale)*(10**fraction_g)
      contours[0] = offset_poly(boundarys[0],toolrad)
      toolpaths[0].extend(contours[0])

   toolpaths[0].extend(pcb_edge)
   #contours[0].extend(pcb_edge)
   for seg in toolpaths[0]:
      if (len(seg) > 0):
         seg.append(seg[0])

   plot(event)

   print "   done"
   status.set("Contour done")

def raster(event):
   global contours, boundarys, toolpaths,\
      xmin, xmax, ymin, ymax, zmin, zmax
   #
   # raster interiors
   #
   print "rastering interior ..."
   xyscale = float(sxyscale.get())
   tooldia = (float(sdia.get())/xyscale)*(10**fraction_g)
   #
   # 2D raster
   #
   if (contours[0] == []):
      edgepath = boundarys[0]
      delta = tooldia/2.0
   else:
      edgepath = contours[0]
      delta = 0#tooldia/4.0
   rasterpath = raster_area(edgepath,delta,ymin*(10**fraction_g),ymax*(10**fraction_g),xmin*(10**fraction_g),xmax*(10**fraction_g))
   #toolpaths[0].extend(pyclipper.PolyTreeToPaths(rasterpath))
   toolpaths[0].extend(rasterpath)

   plot(event)
   print "   done"
   status.set("Raster done")

def raster_area(edgepath,delta,ymin1,ymax1,xmin1,xmax1):
   #
   #
   # raster a 2D region
   #
   # find row-edge intersections
   #
   xyscale = float(sxyscale.get())
   overlap = float(soverlap.get())
   tooldia = (float(sdia.get())/xyscale)*(10**fraction_g)
   rastlines = []
   starty = ymin1
   endy = ymax1
   startx = round(xmax1,2)
   endx = round(xmin1,2)
   numrows = int(floor((endy-starty)/(tooldia*overlap)))
   crast = pyclipper.Pyclipper()
   edgepath = offset_poly(edgepath,delta)
   result=[]



   for row in range(numrows+1):
      rastlines.append([])
      rastlines[row].append([startx,round((starty+row*(tooldia*overlap)),4)])
      rastlines[row].append([endx,round((starty+row*(tooldia*overlap)),4)])
      startx, endx = endx, startx

   crast.AddPaths(pcb_edges[0], pyclipper.PT_CLIP,True)
   crast.AddPaths(rastlines, pyclipper.PT_SUBJECT,False)
   rastlines = crast.Execute2(pyclipper.CT_INTERSECTION, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)

   crast.Clear()
   rastlines = pyclipper.PolyTreeToPaths(rastlines)

##
   crast.AddPaths(edgepath, pyclipper.PT_CLIP,True)
   crast.AddPaths(rastlines, pyclipper.PT_SUBJECT,False)
   rastlines = crast.Execute2(pyclipper.CT_DIFFERENCE, pyclipper.PFT_POSITIVE, pyclipper.PFT_POSITIVE)

   crast.Clear()

   rastlines = pyclipper.PolyTreeToPaths(rastlines)
   #polyclip.sort(key=lambda x: (x[0][1],x[0][0]))
   #polyclip.sort(key=lambda x: x[0][1])
   #polyclip.sort(key=lambda x: x[0][0])
   rastltor=[]
   rastrtol=[]
   for segs in rastlines:
      if (segs[0][0] < segs[1][0]):
         rastltor.append(segs)
      else:
         rastrtol.append(segs)
   rastltor.sort(key=lambda x: (x[0][1],x[0][0]))
   rastrtol.sort(key=lambda x: (x[0][1],-x[0][0]))


   result.extend(rastltor)
   result.extend(rastrtol)
   result.sort(key=lambda x: x[0][1])

   return result

def write_G():
   global boundarys, toolpaths, xmin, ymin, zmin, zmax
   #
   # G code output
   #
   xyscale = float(sxyscale.get())
   zscale = float(sxyscale.get())
   feed = float(sfeed.get())
   xoff = float(sxmin.get()) - xmin*xyscale
   yoff = float(symin.get()) - ymin*xyscale
   cool = icool.get()
   text = outfile.get()
   file = open(text, 'w')
   #file.write("%\n")
   file.write("G20\n")
   file.write("T"+stool.get()+"M06\n") # tool
   file.write("G90 G54\n") # absolute positioning with respect to set origin
   file.write("F%0.3f\n"%feed) # feed rate
   file.write("S"+sspindle.get()+"\n") # spindle speed
   if (cool == TRUE): file.write("M08\n") # coolant on
   file.write("G0 Z"+szup.get()+"\n") # move up before starting spindle
   file.write("M3\n") # spindle on clockwise
   nsegment = 0
   for layer in range((len(boundarys)-1),-1,-1):
      if (toolpaths[layer] == []):
         path = boundarys[layer]
      else:
         path = toolpaths[layer]
      if (szdown.get() == " "):
         raise StandardError("This line has error")
         #zdown = zoff + zmin + (layer-0.50)*dlayer
      else:
         zdown = float(szdown.get())
      for segment in range(len(path)):
         nsegment += 1
         vertex = 0
         x = path[segment][vertex][Xpos]*xyscale*(10**-fraction_g) + xoff
         y = path[segment][vertex][Ypos]*xyscale*(10**-fraction_g) + yoff
         file.write("G0 X%0.4f "%x+"Y%0.4f "%y+"Z"+szup.get()+"\n") # rapid motion
         file.write("G1 Z%0.4f "%zdown+"\n") # linear motion
         for vertex in range(1,len(path[segment])):
            x = path[segment][vertex][Xpos]*xyscale*(10**-fraction_g) + xoff
            y = path[segment][vertex][Ypos]*xyscale*(10**-fraction_g) + yoff
            file.write("G1 X%0.4f "%x+"Y%0.4f"%y+"\n")
         file.write("Z"+szup.get()+"\n")
   file.write("G0 Z"+szup.get()+"\n") # move up before stopping spindle
   file.write("M5\n") # spindle stop
   if (cool == TRUE): file.write("M09\n") # coolant off
   file.write("M30\n") # program end and reset
   #file.write("%\n")
   file.close()
   print "wrote",nsegment,"G code toolpath segments to",text
   status.set("wrote "+str(nsegment)+" G code toolpath segments to "+str(text))

def write_l():
   global boundarys, toolpaths, xmin, ymin, zmin, zmax
   #
   # LaZoR Mk1 code output
   #
   print xmax,"  ",xmin
   print ymax,"  ",ymin
   xyscale = float(sxyscale.get())
   zscale = float(sxyscale.get())
   #dlayer = float(sthickness.get())/zscale
   feed = float(sfeed.get())
   xoff = float(sxmin.get()) - xmin*xyscale
   yoff = float(symin.get()) - ymin*xyscale
   cool = icool.get()
   text = outfile.get()
   file = open(text, 'w')
   #file.write("%\n")
   #file.write("O1234\n")
   #file.write("T"+stool.get()+"M06\n") # tool
   file.write("G90G54\n") # absolute positioning with respect to set origin
   #file.write("F%0.3f\n"%feed) # feed rate
   file.write("S"+sspindle.get()/100+"\n") # spindle speed
   #if (cool == TRUE): file.write("M08\n") # coolant on
   #file.write("G00Z"+szup.get()+"\n") # move up before starting spindle
   #file.write("M03\n") # spindle on clockwise
   nsegment = 0
   for layer in range((len(boundarys)-1),-1,-1):
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
         x = path[segment][vertex][Xpos]*xyscale*(10**-fraction_g) + xoff
         y = path[segment][vertex][Ypos]*xyscale*(10**-fraction_g) + yoff


         file.write("G00X%0.4f"%x+"Y%0.4f"%y+"\n") # rapid motion
         #file.write("G01Z%0.4f"%zdown+"\n") # linear motion
         file.write("M03\n")
         for vertex in range(1,len(path[segment])):
            x = path[segment][vertex][Xpos]*xyscale*(10**-fraction_g) + xoff
            y = path[segment][vertex][Ypos]*xyscale*(10**-fraction_g) + yoff
            file.write("G01X%0.4f"%x+"Y%0.4f"%y+"F%0.3f\n"%feed+"\n")

         #file.write("Z"+szup.get()+"\n")
         file.write("M05\n")
   #file.write("G00Z"+szup.get()+"\n") # move up before stopping spindle
   file.write("M05\n") # spindle stop
   if (cool == TRUE): file.write("M09\n") # coolant off
   file.write("M30\n") # program end and reset
   #file.write("%\n")
   file.close()
   print "wrote",nsegment,"G code toolpath segments to",text
   status.set("wrote "+str(nsegment)+" G code toolpath segments to "+str(text))

#
#*********** GUI event handlers ********************
#

def write():
   global xmin, xmax, ymin, ymax, zmin, zmax
   #
   # write toolpath
   #
   text = outfile.get()
   if (find(text,".g") != -1):
      write_G()
   elif (find(text,".l") != -1):
      write_l()
   else:
      print "unsupported output file format"
      return
   xyscale = float(sxyscale.get())
   xoff = float(sxmin.get()) - xmin*xyscale
   yoff = float(symin.get()) - ymin*xyscale
   print "   xmin: %0.3g "%(xmin*xyscale+xoff),\
      "xmax: %0.3g "%(xmax*xyscale+xoff),\
      "dx: %0.3g "%((xmax-xmin)*xyscale)
   print "   ymin: %0.3g "%(ymin*xyscale+yoff),\
      "ymax: %0.3g "%(ymax*xyscale+yoff), \
      "dy: %0.3g "%((ymax-ymin)*xyscale)

def delframes():
   #
   # delete all CAM frames
   #
##   camframe.pack_forget()
   #cutframe.pack_forget()
   #imgframe.pack_forget()
   toolframe.pack_forget()
   feedframe.pack_forget()
##   zcoordframe.pack_forget()
   z2Dframe.pack_forget()
   #zsliceframe.pack_forget()
   gframe.pack_forget()
   outframe.pack_forget()
   #laserframe.pack_forget()
   #excimerframe.pack_forget()
   #autofocusframe.pack_forget()
   #jetframe.pack_forget()
   #out3Dframe.pack_forget()
##   leftframe.grid_forget
##   boardGeo.grid_forget
##   devframe.grid_forget

def camselect(event):
   global faces, xmin, xmax, ymin, ymax, zmin, zmax, xysize, zsize, fixed_size
   #
   # pack appropriate CAM GUI options based on output file
   #
   xyscale = float(sxyscale.get())
   zscale = float(szscale.get())
   outtext = outfile.get()
   if (find(outtext,".g") != -1):
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
   elif (find(outtext,".l") != -1):
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
   dot = find(cur_sel,'.')
   cur_sel = cur_sel[(dot+1):]
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
   xycoord.set("X %6.3f Y %6.3f"%((round(c.canvasx(event.x)/DPI,4)),(round(-c.canvasy(event.y)/DPI,4))))

# windows mouse wheel zoom
def zoomer(event):
   # get current mouse position as a canvas coordinate
   mouse_x = c.canvasx(event.x)
   mouse_y = c.canvasy(event.y)
   if event.delta < 0:
      zoomScale = 0.8
   if event.delta > 0:
      zoomScale = 1.2
   c.scale("PlotObjects", 0, 0, zoomScale, zoomScale)
   # Scale linewidth
   linewidth = c.itemcget("plot_path","width")
   if linewidth != '':
      c.itemconfig("plot_path",width = float(linewidth)*zoomScale)
   c.configure(scrollregion = c.bbox("PlotObjects"))

def pan_start(event):
   c.configure(cursor="fleur")
   c.scan_mark(event.x, event.y)

def pan_move(event):
   c.scan_dragto(event.x, event.y, gain=1)

def pan_end(event):
   c.configure(cursor="crosshair")

def Canvas_ScrollX(event):
   if event.delta < 0:
      c.xview_scroll(1,"units")
   if event.delta > 0:
      c.xview_scroll(-1,"units")

def Canvas_ScrollY(event):
   if event.delta < 0:
      c.yview_scroll(1,"units")
   if event.delta > 0:
      c.yview_scroll(-1,"units")

def zoomin():
   #
   # Zoom plot in
   #
   c.scale("PlotObjects", 0, 0, 1.1, 1.1)
   # Scale linewidth
   linewidth = c.itemcget("plot_path","width")
   if linewidth != '':
      c.itemconfig("plot_path",width = float(linewidth)*1.1)
   c.configure(scrollregion = c.bbox("PlotObjects"))

def zoomout():
   #
   # Zoom plot out
   #
   c.scale("PlotObjects", 0, 0, 0.8, 0.8)
   # Scale linewidth
   linewidth = c.itemcget("plot_path","width")
   if linewidth != '':
      c.itemconfig("plot_path",width = float(linewidth)*0.8)
   c.configure(scrollregion = c.bbox("PlotObjects"))

def callplot():
   plot(0)

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

#
#************************************************
#

print "cam.py "+VERSION+" "+DATE+" (c) D.Hill & B. Saunders"
print """Permission granted for experimental and personal use;
   license for commercial not yet available"""

#
# initial canvas size in pixels
#
WINDOW = 500

#
# define GUI
#
root = Tk()
root.title('LaZoR.py')
root.columnconfigure(0, weight = 1)
root.rowconfigure(0, weight = 1)
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
xmin = 0.0
xmax = 0.0
ymin = 0.0
ymax = 0.0
zmin = -1.0
zmax = 0.0
xyscale = 1.0
zscale = 1.0
xysize = 1.0
zsize = 1.0
nverts = 16
fixed_size = False
jobname = ""
sxmin = StringVar()
sxmin.set(str(xmin))
symin = StringVar()
symin.set(str(ymin))
szmax = StringVar()
szmax.set(str(zmax))
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

#********* Main Menu ***************
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
viewmenu.add_radiobutton(label="Show copper filled", variable = coppermode, value = 0, command = callplot)
viewmenu.add_radiobutton(label="Show copper boundary", variable = coppermode, value = 1, command = callplot)
viewmenu.add_radiobutton(label="Hide copper", variable = coppermode, value = 2, command = callplot)
viewmenu.add_separator()
viewmenu.add_checkbutton(label="Show tracks", command = donothing)
viewmenu.add_checkbutton(label="Show pads", command = donothing)
viewmenu.add_checkbutton(label="Show regions", command = donothing)
viewmenu.add_separator()
viewmenu.add_checkbutton(label="Show origin", variable = showorigin, command=donothing)
viewmenu.add_checkbutton(label="Show toolpaths", variable=showtoolpath, command=callplot)
viewmenu.add_checkbutton(label="Show cutwidth", variable = showcuts, command=callplot)
menubar.add_cascade(label="View", menu=viewmenu)

workmenu = Menu(menubar, tearoff=0)
isomenu = Menu(workmenu, tearoff = 0)
workmenu.add_cascade(label = "Isolation",menu = isomenu)
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

#*********** Toolbar *********
##toolbar = Frame(root)
##
##Label(toolbar, text="   ").pack(side="left")
##contButt = Button(toolbar, text = "Contour Boundary")
##contButt.bind('<Button-1>',contour)
##contButt.pack(side = LEFT, padx=2, pady=2)
##rastButt = Button(toolbar, text = "Raster Interior")
##rastButt.bind('<Button-1>',raster)
##rastButt.pack(side = LEFT, padx=2, pady=2)
##deltoolButt = Button(toolbar, text = "Delete Toolpaths",command=donothing)
##deltoolButt.bind('<Button-1>',plot_delete)
##deltoolButt.pack(side = LEFT, padx=2, pady=2)
##Label(toolbar, text="     ").pack(side="left")
##BLButt = Button(toolbar, text = "Bottom Left",command=donothing)
##BLButt.pack(side = LEFT, padx=2, pady=2)
##TLButt = Button(toolbar, text = "Top Left",command=donothing)
##TLButt.pack(side = LEFT, padx=2, pady=2)
##CentButt = Button(toolbar, text = "Centre",command=donothing)
##CentButt.pack(side = LEFT, padx=2, pady=2)
##TRButt = Button(toolbar, text = "Top Right",command=donothing)
##TRButt.pack(side = LEFT, padx=2, pady=2)
##BRButt = Button(toolbar, text = "Bottom Right",command=donothing)
##BRButt.pack(side = LEFT, padx=2, pady=2)
##Label(toolbar, text="     ").pack(side="left")
##ZoominButt = Button(toolbar, text = "Zoom In",command=donothing)
##ZoominButt.pack(side = LEFT, padx=2, pady=2)
##ZoomoutButt = Button(toolbar, text = "Zoom Out",command=donothing)
##ZoomoutButt.pack(side = LEFT, padx=2, pady=2)
##FitScrButt = Button(toolbar, text = "Fit to Screen")
##FitScrButt.bind('<Button-1>',autoscale)
##FitScrButt.pack(side = LEFT, padx=2, pady=2)
##FixtScrButt = Button(toolbar, text = "File Origin")
##FixtScrButt.bind('<Button-1>',fixedscale)
##FixtScrButt.pack(side = LEFT, padx=2, pady=2)

##toolbar.grid(row = 0, column = 0, sticky = E+W+N)
##toolbar.config(bd = 5, relief = SUNKEN)
##toolbar.pack(side=TOP, fill=X)

#viewframe = Frame(root)

centrestrip=Frame(root)
##centrestrip.grid(row = 1, column = 0, sticky = E + W + N + S)
centrestrip.pack(side=TOP, fill=BOTH, expand = YES)
##centrestrip.config(bd = 5, relief = SUNKEN)
##centrestrip.columnconfigure(0, weight = 1)
##centrestrip.rowconfigure(1, weight = 1)

#
leftframe = Frame(centrestrip)
##leftframe.grid(row = 1,column = 0, sticky = N + S + W)
leftframe.pack(side=LEFT, fill=BOTH)
leftframe.config(bd = 5, relief = SUNKEN)
##leftframe.columnconfigure(0, weight = 1)
##leftframe.rowconfigure(0, weight = 1)

##boardGeo = Frame(leftframe)
##boardGeo.grid(row = 0, column = 0)
#


##zcoordframe = Frame(leftframe)
##Label(zcoordframe, text="z max: ").grid(row = 0, column = 0)
##wzmax = Entry(zcoordframe, width=6, textvariable=szmax)
##wzmax.bind('<Return>',plot)
##wzmax.grid(row = 0, column = 1)
##Label(zcoordframe, text="z scale factor:").grid(row = 1, column = 0)
##wzscale = Entry(zcoordframe, width=6, textvariable=szscale)
##wzscale.bind('<Return>',plot)
##wzscale.grid(row = 1, column = 1)
##Label(zcoordframe, text="z display size:").grid(row = 2, column = 0)
##wzsize = Entry(zcoordframe, width=6, textvariable=szsize)
##wzsize.bind('<Return>',plot)
##wzsize.grid(row = 2, column = 1)
##sdz = StringVar()
##Label(zcoordframe, textvariable=sdz).grid(row = 3, column = 0)


Label(leftframe, text = "Workbench").pack(side = TOP,pady = 10)

#
#*********** Output device selection *********
#
devframe = Frame(leftframe,pady = 10)
##devframe.grid(row = 3, column = 0, pady = 10)
devframe.pack()
##wdevbtn = Button(devframe, text="send to")
##wdevbtn.bind('<Button-1>',send)
##wdevbtn.pack(side="left")
Label(devframe, text=" output device: ").grid(row=0, column = 0, sticky = W)
wdevscroll = Scrollbar(devframe,orient=VERTICAL)
wdevlist = Listbox(devframe,width=40,height=1,yscrollcommand=wdevscroll.set)
wdevlist.bind('<ButtonRelease-1>',devselect)
wdevscroll.config(command=wdevlist.yview)
wdevscroll.grid(row = 1, column = 2, rowspan = 3,  sticky = N + S)
wdevlist.insert(END,"g: G code file")
wdevlist.insert(END,"l: LaZoR code file")
wdevlist.grid(row = 1, column = 0, rowspan = 3, columnspan = 2, sticky = N+S+E+W)
wdevlist.select_set(0)

#
toolframe = Frame(leftframe)
Label(toolframe, text="Tool diameter: ").grid(row = 0, column = 0, sticky = E)
sdia = StringVar()
wtooldia = Entry(toolframe, width=6, textvariable=sdia)
wtooldia.grid(row = 0, column = 1, sticky = E+W)
wtooldia.bind('<Key>',plot_delete)
Label(toolframe, text="N contour: ").grid(row = 1, column = 0, sticky = E)
wncontour = Entry(toolframe, width=3, textvariable=sncontour)
wncontour.grid(row = 1, column = 1, sticky = E+W)
wncontour.bind('<Key>',plot_delete)
Label(toolframe, text="Contour undercut: ").grid(row = 1, column = 2, sticky = E)
wundercut = Entry(toolframe, width=6, textvariable=sundercut)
wundercut.grid(row = 1, column = 3, sticky = E+W)
wundercut.bind('<Return>',plot_delete)
contbtn = Button(toolframe, text="Contour")
contbtn.bind('<Button-1>',contour)
contbtn.grid(row = 2, column = 0, columnspan = 4, sticky = E+W, pady = 10)

Label(toolframe, text="Raster overlap: ").grid(row = 3, column = 0, sticky = E)
soverlap = StringVar()
woverlap = Entry(toolframe, width=6, textvariable=soverlap)
woverlap.grid(row = 3, column = 1, sticky = E+W)
woverlap.bind('<Key>',plot_delete)
rastbtn = Button(toolframe, text="Raster")
rastbtn.bind('<Button-1>',raster)
rastbtn.grid(row = 4, column = 0, columnspan = 4, sticky = E+W, pady = 10)

#
feedframe = Frame(leftframe)
Label(feedframe, text=" xy speed:").grid(row = 0, column = 0, sticky = W)
sxyvel = StringVar()
Entry(feedframe, width=10, textvariable=sxyvel).grid(row = 0, column = 1, sticky = W)
Label(feedframe, text=" z speed:").grid(row = 1, column = 0, sticky = W)
szvel = StringVar()
Entry(feedframe, width=10, textvariable=szvel).grid(row = 1, column = 1, sticky = W)

#
z2Dframe = Frame(leftframe)
Label(z2Dframe, text="z up:").grid(row = 0, column = 0, sticky = W)
szup = StringVar()
Entry(z2Dframe, width=10, textvariable=szup).grid(row = 0, column = 1, sticky = E+W)
Label(z2Dframe, text=" z down:").grid(row = 1, column = 0, sticky = W)
szdown = StringVar()
Entry(z2Dframe, width=10, textvariable=szdown).grid(row = 1, column = 1, sticky = E+W)

#
gframe = Frame(leftframe)
Label(gframe, text=" feed rate:").grid(row = 0, column = 0, sticky = W)
sfeed = StringVar()
Entry(gframe, width=6, textvariable=sfeed).grid(row = 0, column = 1, sticky = W)
Label(gframe, text=" spindle speed:").grid(row = 0, column = 2, sticky = W)
sspindle = StringVar()
Entry(gframe, width=6, textvariable=sspindle).grid(row = 0, column = 3, sticky = W)
Label(gframe, text=" tool:").grid(row = 1, column = 0, sticky = W)
stool = StringVar()
Entry(gframe, width=3, textvariable=stool).grid(row = 1, column = 1, sticky = W)
icool = IntVar()
wcool = Checkbutton(gframe, text="coolant", variable=icool)
wcool.grid(row = 1, column = 2, columnspan = 2, sticky = W)

#
#*********** Toolpath write *********
#
outframe = Frame(leftframe)
##outframe.grid(row = 4, column = 0, pady = 10)
outframe.pack()

outbtn = Button(outframe, text="output file:",command=savefile)
outbtn.grid(row = 0, column = 0, pady = 10, sticky = W)
##outbtn.pack()
woutfile = Entry(outframe, width=15, textvariable=outfile)
woutfile.bind('<Return>',camselect)
woutfile.grid(row = 0, column = 1, columnspan = 2, sticky = E)
##Label(outframe, text=" ").grid(row = 1, column = 0)
##Button(outframe, text="quit", command='exit').grid(row = 0, column = 3)
writebtn = Button(outframe, text="write toolpath", command = write)
#writebtn.bind('<Button-1>',write)
writebtn.grid(row = 1, column = 0, columnspan = 4, sticky = E+W)
##Label(camframe, text=" ").pack(side="left")##Label(outframe, text=" ").grid(row = 1, column = 0)

#
centreframe = Frame(centrestrip)
centreframe.pack(side=LEFT, fill=BOTH, expand = YES)
centreframe.config(bd = 5, relief = SUNKEN)

topcentre = Frame(centreframe)

topcentre1 = Frame(topcentre)
Label(topcentre1, text="     ").pack(side="left")
topcentre1.pack(side=LEFT, fill=X, expand = YES)
topcentre2 = Frame(topcentre)
topcentre2.pack(side=LEFT, fill=X)
topcentre3 = Frame(topcentre)
Label(topcentre3, text="     ").pack(side="left")
topcentre3.pack(side=LEFT, fill=X, expand = YES)

Label(topcentre2, text="     ").pack(side="left")
BLButt = Button(topcentre2, text = "Bottom Left",command=donothing)
BLButt.pack(side = LEFT, padx=2, pady=2)
TLButt = Button(topcentre2, text = "Top Left",command=donothing)
TLButt.pack(side = LEFT, padx=2, pady=2)
CentButt = Button(topcentre2, text = "Centre",command=donothing)
CentButt.pack(side = LEFT, padx=2, pady=2)
TRButt = Button(topcentre2, text = "Top Right",command=donothing)
TRButt.pack(side = LEFT, padx=2, pady=2)
BRButt = Button(topcentre2, text = "Bottom Right",command=donothing)
BRButt.pack(side = LEFT, padx=2, pady=2)
Label(topcentre2, text="     ").pack(side="left")
topcentre.pack(side=TOP, fill=X)
##topcentre.config(bd = 5, relief = SUNKEN)

#
#*********** Canvas *********
#
canvasframe = Frame(centreframe)
c = Canvas(canvasframe, width=WINDOW, height=WINDOW, bg ="light blue", cursor = "crosshair", highlightthickness=0)
c.grid(row=0, column=0, sticky=N+S+E+W)
# allow the canvas to grow
canvasframe.grid_rowconfigure(0, weight=1)
canvasframe.grid_columnconfigure(0, weight=1)

# Scroll bars
xscrollbar = Scrollbar(canvasframe, orient=HORIZONTAL, command=c.xview)
xscrollbar.grid(row=1, column=0, sticky=E+W)
yscrollbar = Scrollbar(canvasframe, orient=VERTICAL, command=c.yview)
yscrollbar.grid(row=0, column=1, sticky=N+S)
c.configure(xscrollcommand=xscrollbar.set, yscrollcommand=yscrollbar.set)

# set scroll region
c.configure(scrollregion=(0,0,WINDOW,WINDOW))

canvasframe.pack(side=TOP, fill=BOTH, expand = YES)
##canvasframe.config(bd = 5, relief = SUNKEN)

# canvas event bindings
c.bind("<Enter>", SetCanvasFocus)
c.bind("<Leave>", ClearCanvasFocus)
c.bind("<Motion>",showcoord)
c.bind("<Configure>",canvasframe_resize)
c.bind("<ButtonPress-1>", pan_start)
c.bind("<ButtonRelease-1>", pan_end)
c.bind("<B1-Motion>", pan_move)

#linux scroll
#c.bind("<Button-4>", zoomer_in)
#c.bind("<Button-5>", zoomer_out)

# windows scroll
c.bind("<MouseWheel>", zoomer)
c.bind("<Control-MouseWheel>", Canvas_ScrollX)
c.bind("<Shift-MouseWheel>", Canvas_ScrollY)

#
bottomcentre = Frame(centreframe)

bottomcentre1 = Frame(bottomcentre)
Label(bottomcentre1, text="     ", width = 15).pack(side="left")
bottomcentre1.pack(side=LEFT, fill=X)

bottomcentre2 = Frame(bottomcentre)
Label(bottomcentre2, text="     ").pack(side="left")
bottomcentre2.pack(side=LEFT, fill=X, expand = YES)

bottomcentre3 = Frame(bottomcentre)
bottomcentre3.pack(side=LEFT, fill=X)

bottomcentre4 = Frame(bottomcentre)
Label(bottomcentre4, text="     ").pack(side="left")
bottomcentre4.pack(side=LEFT, fill=X, expand = YES)

bottomcentre5 = Frame(bottomcentre)
bottomcentre5.pack(side=RIGHT)

Label(bottomcentre3, text="     ").pack(side="left")
ZoominButt = Button(bottomcentre3, text = "Zoom In",command=zoomin)
##ZoominButt.bind('<Button-1>',zoomin)
ZoominButt.pack(side = LEFT, padx=2, pady=2)
ZoomoutButt = Button(bottomcentre3, text = "Zoom Out",command=zoomout)
##ZoomoutButt.bind('<Button-1>',zoomout)
ZoomoutButt.pack(side = LEFT, padx=2, pady=2)
FitScrButt = Button(bottomcentre3, text = "Fit to Screen")
FitScrButt.bind('<Button-1>',autoscale)
FitScrButt.pack(side = LEFT, padx=2, pady=2)
FixtScrButt = Button(bottomcentre3, text = "File Origin")
FixtScrButt.bind('<Button-1>',fixedscale)
FixtScrButt.pack(side = LEFT, padx=2, pady=2)
Label(bottomcentre3, text="     ").pack(side="left")
bottomcentre.pack(side=TOP, fill=X)

Label(bottomcentre5, textvariable = xycoord, width = 15).pack(side = RIGHT)

rightframe = Frame(centrestrip)
##rightframe.grid(row = 1,column = 2, sticky = N + S)
rightframe.pack(side=LEFT, fill=BOTH)
rightframe.config(bd = 5, relief = SUNKEN)
##rightframe.columnconfigure(2, weight = 1)
##rightframe.rowconfigure(1, weight = 1)

#
majorGeo = Frame(rightframe)
##majorGeo.grid(row = 0, column = 0, pady = 10, sticky = N)
majorGeo.pack(side=TOP, fill=BOTH, pady = 5)

Label(majorGeo, text="Copper View",anchor = W).grid(row = 0, column = 0)
Label(majorGeo, text=" ").grid(row = 1, column = 0)

coppermodes = [("Show Filled",0),
               ("Show Boundary",1),
               ("Clear All",2)]

for text, mode in coppermodes:
   copperbtn = Radiobutton(majorGeo, text = text,
                           variable = coppermode,
                           value = mode,
                           command = callplot,
                           width = 20,
                           anchor = W)
   copperbtn.grid(column = 0, sticky = W)


#
minorGeo = Frame(rightframe)
##minorGeo.grid(row = 1, column = 0, pady = 10, sticky = N)
minorGeo.pack(side=TOP, fill=BOTH)

Label(minorGeo, text=" ").grid(row = 3, column = 0)
padbtn = Checkbutton(minorGeo, text="show pads", variable=showpad, width = 20, command = callplot, anchor = W)
padbtn.grid(row = 4, column = 0)
trackbtn = Checkbutton(minorGeo, text="show track", variable=showtrack, width = 20, command = callplot, anchor = W)
trackbtn.grid(row = 5, column = 0)
regionbtn = Checkbutton(minorGeo, text="show regions", variable=showregion, width = 20, command = callplot,anchor = W)
regionbtn.grid(row = 6, column = 0)

#
toolGeo = Frame(rightframe)
##toolGeo.grid(row = 2, column = 0, pady = 10, sticky = N)
toolGeo.pack(side=TOP, fill=BOTH)

Label(toolGeo, text=" ").grid(row = 0, column = 0)
toolbtn = Checkbutton(toolGeo, text="show toolpaths", variable=showtoolpath, width = 20, command = callplot, anchor = W)
toolbtn.grid(row = 1, column = 0)
toolbtn.select()
cutbtn = Checkbutton(toolGeo, text="show cutwidth",  variable=showcuts, width = 20, command = callplot, anchor = W)
cutbtn.grid(row = 2, column = 0)

#
viewframe = Frame(rightframe)
##viewframe.grid(pady = 10, sticky = N)
viewframe.pack(side=TOP, fill=BOTH)

Label(viewframe, text=" ").grid(row = 0, column = 0)
##Label(viewframe, text="xy display size:").grid(row = 12, column = 0, sticky = W)
##wxysize = Entry(viewframe, width=4, textvariable=sxysize)
##wxysize.grid(row = 12, column = 1, sticky = E + W)
##wxysize.bind('<Return>',plot)
Label(viewframe, text=" x min:").grid(row = 13, column = 0, sticky = W)
wxmin = Entry(viewframe, width=6, textvariable=sxmin)
wxmin.grid(row = 13, column = 1, sticky = E + W)
wxmin.bind('<Return>',plot)
Label(viewframe, text=" y min:").grid(row = 14, column = 0, sticky = W)
wymin = Entry(viewframe, width=6, textvariable=symin)
wymin.grid(row = 14, column = 1, sticky = E + W)
wymin.bind('<Return>',plot)
Label(viewframe, text=" xy scale factor:").grid(row = 15, column = 0, sticky = W)
wxyscale = Entry(viewframe, width=6, textvariable=sxyscale)
wxyscale.grid(row = 15, column = 1, sticky = E + W)
wxyscale.bind('<Return>',plot_delete)
sdxy = StringVar()
Label(viewframe, text=" ").grid(row = 19, column = 0)
Label(viewframe, textvariable=sdxy).grid(row = 20, column = 0, columnspan = 2, sticky = E + W)
#
statusframe = Frame(root,borderwidth=1,relief=SUNKEN)
status = StringVar()
version = StringVar()
status.set("Ok")
namedate = " LaZoR.py ("+VERSION+" "+DATE+")  "
version.set(namedate)
Label(statusframe, text="Status:").pack(side = LEFT)
Label(statusframe, textvariable=status, width = 40).pack(side = LEFT)
Label(statusframe, text="Board:").pack(side = LEFT)
Label(statusframe, textvariable=infilepcb, width = 20).pack(side = LEFT)
Label(statusframe, text="").pack(side = LEFT, fill = X)
Label(statusframe, text="Edge:").pack(side = LEFT)
Label(statusframe, textvariable=infileedge, width = 20).pack(side = LEFT)
Label(statusframe, text="").pack(side = LEFT, fill = X)
Label(statusframe, text="Drill:").pack(side = LEFT)
Label(statusframe, textvariable=infiledrill, width = 20).pack(side = LEFT)
Label(statusframe, text="").pack(side = LEFT, fill = X, expand = YES)
Label(statusframe, textvariable=version,anchor = E).pack(side = RIGHT)
##statusframe.grid(row = 2, column = 0, sticky = S+E+W)
statusframe.pack(side=TOP, fill=X)
statusframe.config(bd = 5, relief = SUNKEN)
##statusframe.resizable(width=FALSE, height=FALSE)
##statusframe.maxsize(statusframe.winfo_width(), statusframe.winfo_height())
#

#
pcb_edges = [[]]
contours = [[]]
pads = [[]]
tracks = [[]]
boundarys=[[]]
toolpaths = [[]]
regions = [[]]
fraction_g = 0
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
