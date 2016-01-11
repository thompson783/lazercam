import wx
import wx.lib.dragscroller
import colorsys
from math import cos, sin, radians


#----------------------------------------------------------------------

BASE  = 80.0    # sizes used in shapes drawn below
BASE2 = BASE/2
BASE4 = BASE/4

USE_BUFFER = ('wxMSW' in wx.PlatformInfo) # use buffered drawing on Windows


class TestPanel(wx.ScrolledWindow):

    def __init__(self, parent):
        wx.ScrolledWindow.__init__(self, parent, -1)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.Bind(wx.EVT_MOTION, self.OnMotion)
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
        if USE_BUFFER:
            self.Bind(wx.EVT_SIZE, self.OnSize)

        self.panning = False
        self.offsetx = 300
        self.offsety = 300
        self.scale = 1.0

        self.SetScrollbars(1, 1, 1200, 1200, 300, 300)

    def OnLeftDown(self, evt):
        self.x, self.y = evt.GetPositionTuple()
        self.scrollx, self.scrolly = self.GetViewStart()
        self.panning = True

    def OnMotion(self, evt):
        if self.panning:
            xx, yy = evt.GetPositionTuple()
            self.Scroll(self.scrollx + self.x - xx, self.scrolly + self.y - yy)

    def OnLeftUp(self, evt):
        if self.panning:
            self.panning = False

    def OnLeave(self, evt):
        if self.panning: self.OnLeftUp(evt)

    def OnWheel(self, evt):
        if evt.ControlDown():
            rot = evt.GetWheelRotation()
            mult = 0.125 if rot > 0 else -0.125
            self.scale += mult

            # # Adjust scroll so it appears zoom is occuring around mouse point
            # xx, yy = evt.GetPositionTuple()
            # vw, vh = self.GetClientSize()
            # scrollx, scrolly = self.GetViewStart()
            # sx = int((vw+self.offsetx)*mult/2.0)
            # sy = int((vh+self.offsety)*mult/2.0)
            # print sx,sy
            # scrollx -= sx
            # scrolly -= sy
            # self.Scroll(scrollx, scrolly)

            dc = wx.MemoryDC(self._buffer)
            dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
            dc.Clear()
            gc = self.MakeGC(dc)
            self.Draw(gc)
            self.Refresh()

    def OnSize(self, evt):
        # When there is a size event then recreate the buffer to match
        # the new size of the window.
        self.InitBuffer()
        evt.Skip()

    def OnPaint(self, evt):
        if USE_BUFFER:
            # The buffer already contains our drawing, so no need to
            # do anything else but create the buffered DC.  When this
            # method exits and dc is collected then the buffer will be
            # blitted to the paint DC automagically
            dc = wx.BufferedPaintDC(self, self._buffer, wx.BUFFER_VIRTUAL_AREA)
        else:
            # Otherwise we need to draw our content to the paint DC at
            # this time.
            dc = wx.PaintDC(self)
            gc = self.MakeGC(dc)
            self.Draw(gc)

    def InitBuffer(self):
        sz = self.GetVirtualSize()
        sz.width = max(1, sz.width)
        sz.height = max(1, sz.height)
        self._buffer = wx.EmptyBitmap(sz.width, sz.height, 32)

        dc = wx.MemoryDC(self._buffer)
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        gc = self.MakeGC(dc)
        self.Draw(gc)

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

    def Draw(self, gc):
        print("drawing")
        gc.Translate(self.offsetx, self.offsety)  # apply before scale!
        gc.Scale(self.scale, self.scale)

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        font.SetWeight(wx.BOLD)
        gc.SetFont(font)

        # make a path that contains a circle and some lines, centered at 0,0
        path = gc.CreatePath()
        path.AddCircle(0, 0, BASE2)
        # path.MoveToPoint(0, -BASE2)
        # path.AddLineToPoint(0, BASE2)
        # path.MoveToPoint(-BASE2, 0)
        # path.AddLineToPoint(BASE2, 0)
        # path.CloseSubpath()
        path.AddRectangle(-BASE4, -BASE4/2, BASE2, BASE4)
        path.AddRectangle(-7,-7,14,14)
        path.AddRectangle(-4,-4,8,8)


        # Now use that path to demonstrate various capbilites of the grpahics context
        gc.PushState()             # save current translation/scale/other state
        gc.Translate(60, 75)       # reposition the context origin

        gc.SetPen(wx.Pen("navy", 1))
        gc.SetBrush(wx.Brush("pink"))

        # show the difference between stroking, filling and drawing
        for label, PathFunc in [("StrokePath", gc.StrokePath),
                                ("FillPath",   gc.FillPath),
                                ("DrawPath",   gc.DrawPath)]:
            w, h = gc.GetTextExtent(label)

            gc.DrawText(label, -w/2, -BASE2-h-4)
            PathFunc(path)
            gc.Translate(2*BASE, 0)


        gc.PopState()              # restore saved state
        gc.PushState()             # save it again
        gc.Translate(60, 200)      # offset to the lower part of the window

        gc.DrawText("Scale", 0, -BASE2)
        gc.Translate(0, 20)

        # for testing clipping
        gc.Clip(0, 0, 100, 100)
        rgn = wx.RegionFromPoints([ (0,0), (75,0), (75,25,), (100, 25),
                                   (100,100), (0,100), (0,0)  ])
        gc.ClipRegion(rgn)
        gc.ResetClip()

        gc.SetBrush(wx.Brush(wx.Colour(178,  34,  34, 128)))   # 128 == half transparent
        for cnt in range(8):
            gc.Scale(1.08, 1.08)    # increase scale by 8%
            gc.Translate(5,5)
            gc.DrawPath(path)


        gc.PopState()              # restore saved state
        gc.PushState()             # save it again
        gc.Translate(400, 200)
        gc.DrawText("Rotate", 0, -BASE2)

        # Move the origin over to the next location
        gc.Translate(0, 75)

        # draw our path again, rotating it about the central point,
        # and changing colors as we go
        for angle in range(0, 360, 30):
            gc.PushState()         # save this new current state so we can
                                   # pop back to it at the end of the loop
            r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(float(angle)/360, 1, 1)]
            gc.SetBrush(wx.Brush(wx.Colour(r, g, b, 64)))
            gc.SetPen(wx.Pen(wx.Colour(r, g, b, 128)))

            # use translate to artfully reposition each drawn path
            gc.Translate(1.5 * BASE2 * cos(radians(angle)),
                         1.5 * BASE2 * sin(radians(angle)))

            # use Rotate to rotate the path
            gc.Rotate(radians(angle))

            # now draw it
            gc.DrawPath(path)
            gc.PopState()

        gc.PopState()

#----------------------------------------------------------------------


class DoodleFrame(wx.Frame):
    def __init__(self, parent=None):
        super(DoodleFrame, self).__init__(parent, title="Doodle Frame",
            size=(800,600),
            style=wx.DEFAULT_FRAME_STYLE|wx.NO_FULL_REPAINT_ON_RESIZE)
        # doodle = DragScrollerExample(self)
        doodle = TestPanel(self)
  

if __name__ == '__main__':
    app = wx.App()
    frame = DoodleFrame()
    frame.Show()
    app.MainLoop()
