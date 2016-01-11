import math
import wx
import wx.lib.scrolledpanel
from GerberReader3 import GerberData, GerberLayer

__author__ = 'Thompson'

#----------------------------------------------------------------------


USE_BUFFER = True #('wxMSW' in wx.PlatformInfo) # use buffered drawing on Windows
    # NOT using buffering makes it painfully slow!!!!!

clrbrush = wx.TRANSPARENT_BRUSH
clrpen = wx.TRANSPARENT_PEN


class GerberCanvas(wx.lib.scrolledpanel.ScrolledPanel):
    """
    Canvas for rendering Gerber data using wxPython frameworks.

    Note about the coordinate system. There are 3 layers:
     - Mouse (or screen): has unit pixels and is 1:1 to screen. +ve going down
     - Internal: coordinates unmodified from gerber file. Must be multiplied by data.fraction and converted to
       desired measurement unit in order to be useful (consider this as the unitless raw format). +ve going up
     - Coord X/Y: real world scaled coordinates. +ve going up

     MouseToCoord# is used for converting mouse to real world coords (output to human)
     MouseToInternal# is mainly used to convert data suitable for storing into internal raw data
    """

    def __init__(self, parent, statusbar=None, statuspos=0):
        wx.lib.scrolledpanel.ScrolledPanel.__init__(self, parent, -1, size=(600, 600))
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
        self.Bind(wx.EVT_MOTION, self.OnMotion)
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
        self.Bind(wx.EVT_SCROLLWIN, self.OnScroll)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        if USE_BUFFER:
            self.Bind(wx.EVT_SIZE, self.OnSize)

        self.BackgroundColour = "#DDDDDD"

        self.panning = False
        self.offsetx = 300
        self.offsety = 300
        self.scale = 1.0
        self.gerber_data = None
        """ :type gerber_data: GerberData """
        self.mousescale = 1
        self.displayunits = 1
        self.toolpaths = []
        self.toolpathlinewidth = 0
        self.bufferAll = True
        self.drillPts = []

        self.measureX = -1
        self.measureY = -1

        self.statusbar = statusbar
        self.statuspos = statuspos
        self._buffer = None

        self.SetupScrolling(True, True, scrollToTop=False, scrollIntoView=False, rate_x=5, rate_y=5)
        self.SetScrollbars(1, 1, 100, 100, 0, 0)  # default, will be overwritten

    def OnLeftDown(self, evt):
        self.x, self.y = evt.GetPositionTuple()
        self.scrollx, self.scrolly = self.GetViewStart()
        self.panning = True

    def OnLeftUp(self, evt):
        if self.panning:
            self.panning = False

    def OnMotion(self, evt):
        if self.panning:
            xx, yy = evt.GetPositionTuple()
            self.Scroll(self.scrollx + self.x - xx, self.scrolly + self.y - yy)
            if self._buffer is None: self.Refresh()
            elif self._buffer is not None and not self.bufferAll:
                self.redraw()
                # self.Refresh()
        elif self.statusbar is not None:
            tx, ty = self.GetViewStart()
            x, y = evt.GetPositionTuple()
            x = self.MouseToCoordX(x + tx)
            y = self.MouseToCoordY(y + ty)
            self.statusbar.SetStatusText("X %8.3f, Y %8.3f" % (x, y), self.statuspos)

        if self.measureX != -1 and self.statusbar is not None:
            tx, ty = self.GetViewStart()
            dx, dy = evt.GetPositionTuple()
            dx = (self.MouseToInternalX(tx + dx) - self.measureX)*self.mousescale
            dy = (self.MouseToInternalY(ty + dy) - self.measureY)*self.mousescale
            self.statusbar.SetStatusText("Measure: dx=%4.3f dy=%4.3f dist=%4.3f" % (dx, dy, math.sqrt(dx*dx+dy*dy)), 0)

    def OnEnter(self, evt):
        self.SetFocus()

    def OnLeave(self, evt):
        if self.panning: self.OnLeftUp(evt)

    def OnWheel(self, evt):
        if evt.ControlDown():
            if self.gerber_data is None: return
            rot = evt.GetWheelRotation()
            mult = 1.25 if rot > 0 else 0.8

            self.zoomrel(mult, evt.GetPositionTuple())
        else:
            evt.Skip()

    def OnSize(self, evt):
        if self._buffer is None or not self.bufferAll:
            self.InitBuffer()
        evt.Skip()

    def OnScroll(self, evt):
        if self._buffer is not None and not self.bufferAll:
            self.redraw()  # trigger redraw when view changes if not buffering all the time
            self.Refresh()
        else:
            evt.Skip()

    def OnKeyDown(self, evt):
        if evt.GetKeyCode() == wx.WXK_ESCAPE:
            self.stopMeasurement()

    def OnPaint(self, evt):
        if self._buffer is not None:
            # The buffer already contains our drawing, so no need to
            # do anything else but create the buffered DC.  When this
            # method exits and dc is collected then the buffer will be
            # blitted to the paint DC automagically
            if self.bufferAll:
                dc = wx.BufferedPaintDC(self, self._buffer, wx.BUFFER_VIRTUAL_AREA)
                if self.statusbar is not None:
                    self.statusbar.SetStatusText("Full buffered render", self.statuspos + 2)
            else:
                dc = wx.BufferedPaintDC(self, self._buffer, wx.BUFFER_CLIENT_AREA)
                if self.statusbar is not None:
                    self.statusbar.SetStatusText("Partial buffered render", self.statuspos + 2)
        else:
            # Otherwise we need to draw our content to the paint DC at this time.
            dc = wx.PaintDC(self)
            gc = self.MakeGC(dc)
            self.Draw(dc, gc)

    def InitBuffer(self):
        if not USE_BUFFER: return
        w, h = self.GetVirtualSize()
        if w*h > 5000*5000:  # 25M pixels
            # buffer too large... switch to direct rendering
            # TODO: the check is rather basic - different computers will have different req. The check should be
            # to see if bitmap allocation was successful and abort if needed but I can't find a way to check this.
            # self._buffer = None
            w, h = self.GetClientSize()
            self._buffer = wx.EmptyBitmap(w, h, 32)
            self.bufferAll = False
        else:
            self._buffer = wx.EmptyBitmap(w, h, 32)
            self.bufferAll = True
        self.redraw()

    def MakeGC(self, dc):
        try:
            if False:
                # If you want to force the use of Cairo instead of the
                # native GraphicsContext backend then create the
                # context like this.  It works on Windows so far, (on
                # wxGTK the Cairo context is already being used as the
                # native default.)
                gcr = wx.GraphicsRenderer.GetCairoRenderer
                gc = gcr() and gcr().CreateContext(dc)
                if gc is None:
                    wx.MessageBox("Unable to create Cairo Context.", "Oops")
                    gc = wx.GraphicsContext.Create(dc)
            else:
                # Otherwise, creating it this way will use the native
                # backend, (GDI+ on Windows, CoreGraphics on Mac, or
                # Cairo on GTK).
                gc = wx.GraphicsContext.Create(dc)

        except NotImplementedError:
            dc.DrawText("This build of wxPython does not support the wx.GraphicsContext "
                        "family of classes.",
                        25, 25)
            return None
        return gc

    def Draw(self, dc, gc):
        """
        Render the actual canvas data
        :type gc: wx.DC
        :type gc: wx.GraphicsContext
        """
        data = self.gerber_data
        if data is None: return

        # gc.SetAntialiasMode(wx.ANTIALIAS_NONE)

        tx = 0
        ty = 0
        if self._buffer is None or not self.bufferAll:
            # direct drawing so take offset into account
            tx, ty = self.GetViewStart()
            gc.Translate(-tx, -ty)

        scale = self.scale
        gc.PushState()
        gc.Scale(scale, -scale)
        gc.Translate(-self.offsetx, -self.offsety)

        for tmp in data.layers:
            if not tmp.visible: continue
            col = tmp.color if tmp.isDark or tmp.type == GerberLayer.TYPE_BOUNDARY else self.BackgroundColour
            if tmp.filled:
                gc.SetPen(clrpen)
                gc.SetBrush(wx.Brush(col))
                # gc.SetBrush(wx.Brush(col, wx.BDIAGONAL_HATCH))  # could use this for clear layers
            else:
                gc.SetPen(wx.Pen(col))
                gc.SetBrush(clrbrush)
            path = gc.CreatePath()
            for seg in tmp.points:
                if len(seg) == 0: continue
                path.MoveToPoint(seg[0])
                for pt in seg[1:]:
                    path.AddLineToPoint(pt)
            gc.DrawPath(path)
            # for seg in tmp.points:
            #     # if len(seg) > 0:
            #         gc.DrawLines(seg, fillStyle=wx.WINDING_RULE)
            # print("   Drawn layer: " + tmp.name + ",  # of poly: " + str(len(tmp.points)))

        if self.drillPts != []:
            gc.SetPen(wx.Pen("yellow", 0))
            # Style 1 - circle with small plus
            for (x, y, dia) in self.drillPts:
                hdia = dia/2
                hdia2 = 0.33*hdia
                gc.DrawEllipse(x - hdia, y - hdia, dia, dia)
                gc.StrokeLine(x - hdia2, y, x + hdia2, y)
                gc.StrokeLine(x, y - hdia2, x, y + hdia2)
            # # Style 2 - circle with slightly larger cross
            # mult = 0.98
            # for (x, y, dia) in self.drillPts:
            #     hdia = dia/2
            #     sqrt = hdia*mult
            #     gc.DrawEllipse(x - hdia, y - hdia, dia, dia)
            #     gc.StrokeLine(x - sqrt, y - sqrt, x + sqrt, y + sqrt)
            #     gc.StrokeLine(x + sqrt, y - sqrt, x - sqrt, y + sqrt)

        # The following is not scaled - rendered at 1:1 ratio
        gc.PopState()
        # dc.SetUserScale(1, 1)
        # dc.SetLogicalOrigin(tx, ty)

        # Draw origin (grey)
        gc.SetPen(wx.Pen("grey", 2))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        b = 10
        b2 = 2*b
        x = -self.offsetx*scale
        y = self.offsety*scale
        # file origin
        gc.DrawEllipse(x + -b, y - b, b2, b2)
        gc.StrokeLine(x, y - b2, x, y + b2)
        gc.StrokeLine(x - b2, y, x + b2, y)
        # output origin (orange)
        gc.SetPen(wx.Pen("#FFA500", 2))
        x += data.originx*scale
        y -= data.originy*scale
        gc.DrawEllipse(x + -b, y - b, b2, b2)
        gc.StrokeLine(x, y - b2, x, y + b2)
        gc.StrokeLine(x - b2, y, x + b2, y)

        if self.toolpaths != []:
            # Doing this under scale and translate of GC appears to be inaccurate due to rounding error
            # so to work around this, we roll out our own scaling but this is rather slow
            # so I have made a hack to cahce the scaling and offsetting operation
            # this makes it a bit messier to update toolpath data but at least it works faster and correctly
            gc.SetPen(wx.Pen("red",  1 if self.toolpathlinewidth == 0 else self.toolpathlinewidth/self.mousescale*scale))
            for seg in self.toolpaths2:
                gc.DrawLines(seg)

        if self.measureX != -1:
            mx = self.InternalXToMouse(self.measureX)
            my = self.InternalYToMouse(self.measureY)
            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.SetBrush(wx.Brush("black"))
            gc.DrawRectangle(mx - 11, my - 1, 22, 3)
            gc.DrawRectangle(mx - 1, my - 11, 3, 22)
            gc.SetBrush(wx.Brush("white"))
            gc.DrawRectangle(mx - 10, my, 20, 1)
            gc.DrawRectangle(mx, my - 10, 1, 20)

    def redraw(self):
        if self._buffer is None: return
        dc = wx.MemoryDC(self._buffer)
        dc.SetBackground(wx.Brush(self.BackgroundColour))
        dc.Clear()
        gc = self.MakeGC(dc)
        self.Draw(dc, gc)

        if self.statusbar is not None:
            self.statusbar.SetStatusText("Direct render", self.statuspos + 2)

#==============================================

    def loadData(self, gerber_data):
        """
        Sets the data and displays it
        :type gerber_data: GerberData
        """
        self.measureX = -1
        self.measureY = -1
        self.gerber_data = gerber_data

        oldunits = self.displayunits
        self.displayunits = gerber_data.units
        self.setUnit(oldunits)

        self.autoscale()
        self.Refresh()

    def loadData2(self, gerber_data, xmin, xmax, ymin, ymax):
        self.measureX = -1
        self.measureY = -1
        self.gerber_data = gerber_data
        self.drillPts = []
        self.toolpaths = []
        self.toolpaths2 = []

        oldunits = self.displayunits
        self.displayunits = gerber_data.units
        self.setUnit(oldunits)

        self.xmin = xmin
        self.xmax = xmax
        self.ymin = ymin
        self.ymax = ymax
        self.offsetx = self.xmin
        self.offsety = self.ymax

        self.autoscale_cac()
        self.Refresh()

    def autoscale(self):
        """ Determines bounds of loaded data and adjusts view to display all.
            This should be called once only after each time the data is set """
        if self.gerber_data is None: return
        self.xmin = 0
        self.xmax = 0
        self.ymin = 0
        self.ymax = 0
        for gl in self.gerber_data.layers:
            for pol in gl.points:
                for seg in pol:
                    if seg[0] < self.xmin: self.xmin = seg[0]
                    elif seg[0] > self.xmax: self.xmax = seg[0]
                    if seg[1] < self.ymin: self.ymin = seg[1]
                    elif seg[1] > self.ymax: self.ymax = seg[1]

        # Apply margin
        ww = (self.xmax - self.xmin)*0.1
        hh = (self.ymax - self.ymin)*0.1
        self.xmin -= ww
        self.xmax += ww
        self.ymin -= hh
        self.ymax += hh

        self.offsetx = self.xmin
        self.offsety = self.ymax

        self.autoscale_cac()

    def autoscale_cac(self):
        """ Determines bounds of data and zoom to fit. The calculation uses cached data from last call
            of autoscale (so if data has been modified, you should use that method instead) """
        w, h = self.GetClientSize()
        data = self.gerber_data
        ww = (data.xmax - data.xmin)
        hh = (data.ymax - data.ymin)
        ww2 = ww*1.1
        hh2 = hh*1.1
        self.scale = min(w/ww2, h/hh2)
        self.updateToolpathData()


        # Shift scroll pane to centre data (ignoring the origin)
        tx = int((data.xmin - self.xmin)*self.scale - (w - (data.xmax - data.xmin)*self.scale)/2)
        ty = int((self.ymax - data.ymax)*self.scale - (h - (data.ymax - data.ymin)*self.scale)/2)
        self.adjustScrollBars(tx, ty)

    def zoomrel(self, mult, pt=None):
        """
        :param mult: multiplier to current zoom >1 zooms in, <1 zooms out. Must not be <= 0
        :param pt: zoom focal point of canvas as (x,y) coord in pixel coordinates.
            Omitting this focuses zoom around centre of canvas
        """

        # TODO: limit scale range
        if pt is None:
            pt = self.GetClientSize()
            pt = (pt[0]/2, pt[1]/2)
        self.scale *= mult

        # Calculate offset so zoom focuses on mouse cursor - these 5 lines took me >10 hours to figure out
        xx, yy = pt
        tx, ty = self.GetViewStart()
        mult2 = (1 - mult)
        tx = int(tx*mult - xx*mult2)
        ty = int(ty*mult - yy*mult2)

        self.updateToolpathData()
        self.adjustScrollBars(tx, ty)

    def adjustScrollBars(self, tx=0, ty=0):
        """ Adjusts scroll bars to current scale  - this method also initialises the buffer """
        w, h = self.GetClientSize()
        if self.scale*(self.xmax - self.gerber_data.xmax) < w/2:
            vw = int(self.scale * (self.xmax - self.xmin - (self.xmax - self.gerber_data.xmax))) + w/2
        else:
            vw = int(self.scale * (self.xmax - self.xmin))
        if self.scale*(self.gerber_data.ymin - self.ymin) < h/2:
            vh = int(self.scale * (self.ymax - self.ymin - (self.gerber_data.ymin - self.ymin))) + h/2
        else:
            vh = int(self.scale * (self.ymax - self.ymin))
        # print "  Scroll bounds (virtual, actual):", vw, vh, w, h
        # if self.statusbar is not None:
        #     self.statusbar.SetStatusText("Zoom: %4.1fx" % (self.scale * 10**self.gerber_data.fraction /
        #                                                    wx.ScreenDC().GetPPI()[0]),
        #                                  self.statuspos + 1)
        # print wx.ScreenDC().GetPPI()

        self.Freeze()
        self.SetScrollbars(1, 1, vw, vh, tx, ty)
        self.InitBuffer()
        self.Thaw()

    def MouseToInternalX(self, x):
        """ Convert mouse coord to internal coord of gerber file. Does not take unit into account """
        return x / self.scale + self.offsetx

    def MouseToInternalY(self, y):
        """ Convert mouse coord to internal coord of gerber file. Does not take unit into account """
        return self.offsety - y / self.scale

    def MouseToCoordX(self, x):
        """ Convert mouse coord to coord of gerber file. Takes unit into account """
        return (x/self.scale + self.offsetx) * self.mousescale

    def MouseToCoordY(self, y):
        """ Convert mouse coord to coord of gerber file. Takes unit into account """
        return (self.offsety - y/self.scale) * self.mousescale

    def InternalXToMouse(self, x):
        """ Convert internal coord to mouse coord. Does not take unit into account """
        return (x - self.offsetx) * self.scale

    def InternalYToMouse(self, y):
        """ Convert internal coord to mouse coord. Does not take unit into account """
        return (self.offsety - y) * self.scale

    def setUnit(self, unit):
        """
        Sets the unit of the canvas. All this does is modify the X/Y coordinates shown in status bar.
        Internally, point data is left changed to preserve accuracy.
        :type unit: int
        """
        self.displayunits = unit
        if self.gerber_data is None: return
        self.mousescale = 10**-self.gerber_data.fraction
        if unit != self.gerber_data.units:
            if unit == 0:
                # in -> mm
                self.mousescale *= 25.4
            else:
                # mm -> in
                self.mousescale /= 25.4

    def updateToolpathData(self):
        """ Call this to update cached toolpaths data. Only needs to be updated when toolpaths
        data is changed or scale is changed. Translation of view is not affected (except changing
        origin point but this only occurs when the data is changed which requires a total reset anyway).
        Extended to update cache.
        """
        if self.toolpaths == []:
            self.toolpaths2 = []
            return
        scale = self.scale
        tx, ty = self.offsetx, self.offsety
        tp = self.toolpaths2 = []
        for layer in self.toolpaths:
            tmp = []
            for seg in layer:
                tmp.append([(seg[0] - tx)*scale, (seg[1] - ty)*-scale])
            tp.append(tmp)

    def startMeasurement(self, (x, y)):
        tx, ty = self.GetViewStart()
        self.measureX = self.MouseToInternalX(tx + x)
        self.measureY = self.MouseToInternalY(ty + y)
        self.redraw()
        self.Refresh()

    def stopMeasurement(self):
        if self.measureX == -1: return
        self.measureX = -1
        self.measureY = -1
        self.redraw()
        self.Refresh()
        if self.statusbar is not None: self.statusbar.SetStatusText("Quit measurement mode", 0)
