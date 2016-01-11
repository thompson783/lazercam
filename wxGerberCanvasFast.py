import wx
import wx.lib.dragscroller
from GerberReader3 import GerberData

__author__ = 'Thompson'

#----------------------------------------------------------------------

# this version does not use a graphics context. It is all done on DC
# performance boost appears to be negligible

USE_BUFFER = True #('wxMSW' in wx.PlatformInfo) # use buffered drawing on Windows
    # NOT using buffering makes it painfully slow!!!!!

clrbrush = wx.TRANSPARENT_BRUSH
clrpen = wx.TRANSPARENT_PEN


class GerberCanvas(wx.ScrolledWindow):
    """
    Canvas for rendering Gerber data using wxPython frameworks.
    Limitations: buffering is limited to memory. Zooming in very close will exceed available memory.
    To avoid this, the canvas switches to direct rendering. This is VERY SLOW.
    """

    def __init__(self, parent, statusbar=None, statuspos=0):
        wx.ScrolledWindow.__init__(self, parent, -1, size=(600, 600))
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.Bind(wx.EVT_MOTION, self.OnMotion)
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
        self.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
        self.Bind(wx.EVT_SCROLLWIN, self.OnScroll)
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

        self.statusbar = statusbar
        self.statuspos = statuspos
        self._buffer = None

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
            xx, yy = self.GetViewStart()
            x, y = evt.GetPositionTuple()
            x = self.MouseToCoordX(x + xx)
            y = self.MouseToCoordY(y + yy)
            self.statusbar.SetStatusText("X %8.3f, Y %8.3f" % (x, y), self.statuspos)

    def OnEnter(self, evt):
        self.SetFocus()

    def OnLeave(self, evt):
        if self.panning: self.OnLeftUp(evt)

    def OnWheel(self, evt):
        if evt.ControlDown():
            rot = evt.GetWheelRotation()
            mult = 1.25 if rot > 0 else 0.8
            self.scale *= mult

            # Calculate offset so zoom focuses on mouse cursor - these 5 lines took me >10 hours to figure out
            xx, yy = evt.GetPositionTuple()
            tx, ty = self.GetViewStart()
            mult2 = (1 - mult)
            tx = int(tx*mult - xx*mult2)
            ty = int(ty*mult - yy*mult2)

            self.updateToolpathData()
            self.adjustScrollBars(tx, ty)
            # self.redraw()
            # self.Refresh()
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

    def OnPaint(self, evt):
        if self._buffer is not None:
            # The buffer already contains our drawing, so no need to
            # do anything else but create the buffered DC.  When this
            # method exits and dc is collected then the buffer will be
            # blitted to the paint DC automagically
            if self.bufferAll:
                dc = wx.BufferedPaintDC(self, self._buffer, wx.BUFFER_VIRTUAL_AREA)
                if self.statusbar is not None:
                    self.statusbar.SetStatusText("Full buffered render", self.statuspos + 1)
            else:
                dc = wx.BufferedPaintDC(self, self._buffer, wx.BUFFER_CLIENT_AREA)
                if self.statusbar is not None:
                    self.statusbar.SetStatusText("Partial buffered render", self.statuspos + 1)
        else:
            # Otherwise we need to draw our content to the paint DC at this time.
            dc = wx.PaintDC(self)
            # gc = self.MakeGC(dc)
            self.Draw(dc)  # , gc)

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

    # def MakeGC(self, dc):
    #     try:
    #         if False:
    #             # If you want to force the use of Cairo instead of the
    #             # native GraphicsContext backend then create the
    #             # context like this.  It works on Windows so far, (on
    #             # wxGTK the Cairo context is already being used as the
    #             # native default.)
    #             gcr = wx.GraphicsRenderer.GetCairoRenderer
    #             gc = gcr() and gcr().CreateContext(dc)
    #             if gc is None:
    #                 wx.MessageBox("Unable to create Cairo Context.", "Oops")
    #                 gc = wx.GraphicsContext.Create(dc)
    #         else:
    #             # Otherwise, creating it this way will use the native
    #             # backend, (GDI+ on Windows, CoreGraphics on Mac, or
    #             # Cairo on GTK).
    #             gc = wx.GraphicsContext.Create(dc)
    #
    #     except NotImplementedError:
    #         dc.DrawText("This build of wxPython does not support the wx.GraphicsContext "
    #                     "family of classes.",
    #                     25, 25)
    #         return None
    #     return gc

    def Draw(self, dc):
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
            # gc.Translate(-tx, -ty)

        # scale = self.scale
        # gc.Scale(scale, -scale)
        # gc.Translate(-self.offsetx, -self.offsety)
        #
        # for tmp in data.layers:
        #     if not tmp.visible: continue
        #     for seg in tmp.points:
        #         if len(seg) > 0:
        #             col = tmp.color if tmp.isDark else self.BackgroundColour
        #             if tmp.filled:
        #                 gc.SetPen(clrpen)
        #                 gc.SetBrush(wx.Brush(col))
        #             else:
        #                 gc.SetPen(wx.Pen(col))
        #                 gc.SetBrush(clrbrush)
        #             gc.DrawLines(seg, fillStyle=wx.WINDING_RULE)
        #     # print("   Drawn layer: " + tmp.name + ",  # of poly: " + str(len(tmp.points)))

        # # Draw origin (grey)
        # gc.SetPen(wx.Pen("grey", 2/self.scale))
        # gc.SetBrush(wx.TRANSPARENT_BRUSH)
        # b = 10/self.scale
        # b2 = 2*b
        # # file origin
        # gc.DrawEllipse(-b, -b, b2, b2)
        # gc.StrokeLine(0, -b2, 0, b2)
        # gc.StrokeLine(-b2, 0, b2, 0)
        # # output origin (orange)
        # gc.SetPen(wx.Pen("#FFA500", 2/self.scale))
        # gc.DrawEllipse(-b + data.originx, -b + data.originy, b2, b2)
        # gc.StrokeLine(data.originx, -b2 + data.originy, data.originx, b2 + data.originy)
        # gc.StrokeLine(-b2 + data.originx, data.originy, b2 + data.originx, data.originy)

        # if self.toolpaths != []:
        #     # Doing this under scale and translate of GC appears to be inaccurate due to rounding error
        #     # so to work around this, we roll out our own scaling but this is rather slow
        #     # so I have made a hack to cahce the scaling and offsetting operation
        #     # this makes it a bit messier to update toolpath data but at least it works faster and correctly
        #     gc.PopState()
        #     gc.SetPen(wx.Pen("red",  1.0 if self.toolpathlinewidth == 0 else self.toolpathlinewidth/self.mousescale*scale))
        #     for seg in self.toolpaths2:
        #         gc.DrawLines(seg)

        scale = self.scale
        dc.SetLogicalOrigin(int(tx + scale*self.offsetx), int(ty - scale*self.offsety))

        for tmp in data.layers:
            if not tmp.visible: continue
            col = tmp.color if tmp.isDark else self.BackgroundColour
            if tmp.filled:
                dc.SetPen(clrpen)
                dc.SetBrush(wx.Brush(col))
            else:
                dc.SetPen(wx.Pen(col))
                dc.SetBrush(clrbrush)
            # for seg in tmp.points:
            #     if len(seg) > 0:
                    # dc.DrawPolygon(seg)
                    # ttmp = []
                    # for sseg in seg:
                    #     ttmp.append([sseg[0]*scale, -sseg[1]*scale])
                    # dc.DrawPolygon(ttmp)
            dc.DrawPolygonList(tmp.data3)

            # print("   Drawn layer: " + tmp.name + ",  # of poly: " + str(len(tmp.points)))

        # The following is not scaled - rendered at 1:1 ratio

        dc.SetUserScale(1, 1)
        dc.SetLogicalOrigin(tx, ty)

        # Draw origin (grey)
        dc.SetPen(wx.Pen("grey", 2))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        b = 10
        b2 = 2*b
        x = -self.offsetx*scale
        y = self.offsety*scale
        # file origin
        dc.DrawEllipse(x + -b, y - b, b2, b2)
        dc.DrawLine(x, y - b2, x, y + b2)
        dc.DrawLine(x - b2, y, x + b2, y)
        # output origin (orange)
        dc.SetPen(wx.Pen("#FFA500", 2))
        x += data.originx*scale
        y -= data.originy*scale
        dc.DrawEllipse(x + -b, y - b, b2, b2)
        dc.DrawLine(x, y - b2, x, y + b2)
        dc.DrawLine(x - b2, y, x + b2, y)

        if self.toolpaths != []:
            # Doing this under scale and translate of GC appears to be inaccurate due to rounding error
            # so to work around this, we roll out our own scaling but this is rather slow
            # so I have made a hack to cahce the scaling and offsetting operation
            # this makes it a bit messier to update toolpath data but at least it works faster and correctly
            dc.SetPen(wx.Pen("red",  1.0 if self.toolpathlinewidth == 0 else self.toolpathlinewidth/self.mousescale*self.scale))
            for seg in self.toolpaths2:
                dc.DrawPolygon(seg)

    def redraw(self):
        if self._buffer is None: return
        dc = wx.MemoryDC(self._buffer)
        dc.SetBackground(wx.Brush(self.BackgroundColour))
        dc.Clear()
        # gc = self.MakeGC(dc)
        self.Draw(dc) # , gc)

        if self.statusbar is not None:
            self.statusbar.SetStatusText("Direct render", self.statuspos + 1)

#==============================================

    def loadData(self, gerber_data):
        """
        Sets the data and displays it
        :type gerber_data: GerberData
        """
        oldunits = self.displayunits
        self.gerber_data = gerber_data
        self.displayunits = gerber_data.units
        self.setUnit(oldunits)
        self.autoscale()
        self.Refresh()

    def loadData2(self, gerber_data, xmin, xmax, ymin, ymax):
        oldunits = self.displayunits
        self.gerber_data = gerber_data
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

    def adjustScrollBars(self, tx=0, ty=0):
        """ Adjusts scroll bars to current scale  - this method also initialises the buffer """
        w, h = self.GetClientSize()
        vw = int(self.scale * (self.xmax - self.xmin - (self.xmax - self.gerber_data.xmax))) + w/2
        vh = int(self.scale * (self.ymax - self.ymin - (self.gerber_data.ymin - self.ymin))) + h/2
        # print "  Scroll bounds (virtual, actual):", vw, vh, w, h
        self.Freeze()
        self.SetScrollbars(1, 1, vw, vh, tx, ty)
        self.InitBuffer()
        self.Thaw()

    def MouseToCoordX(self, x):
        return (x/self.scale + self.offsetx) * self.mousescale

    def MouseToCoordY(self, y):
        return (self.offsety - y/self.scale) * self.mousescale

    def setUnit(self, unit):
        """
        Sets the unit of the canvas. All this does is modify the X/Y coordinates shown in status bar.
        Internally, point data is left changed to preserve accuracy.
        :type unit: int
        """
        if self.gerber_data is None:
            self.displayunits = unit
            return
        self.mousescale = 10**-self.gerber_data.fraction
        if unit != self.gerber_data.units:
            self.displayunits = unit
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

        data = self.gerber_data
        if data is None:
            self.toolpaths2 = []
            return
        scale = self.scale
        for tmp in data.layers:
            # if not tmp.visible: continue
            tmp.data3 = []
            for seg in tmp.points:
                if len(seg) > 0:
                    ttmp = []
                    for sseg in seg:
                        ttmp.append([sseg[0]*scale, -sseg[1]*scale])
                    tmp.data3.append(ttmp)

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

