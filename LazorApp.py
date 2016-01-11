import math
from string import join

import time

import ExcellonReader
import GerberReader3
from wxGerberCanvas import GerberCanvas
from GerberReader3 import load_file, GerberLayer, GerberData
import pyclipper
import wx
import wx.grid
import wx.lib.scrolledpanel
import wx.lib.agw.pycollapsiblepane as PCP

__author__ = 'Damien, Ben, Thompson'
VERSION = "V5.5"
DATE = "02/12/15"


def sizedToFill(content, margin=0):
    """
    Utility method to add a sizer that fills the whole parent with the content pane
    :param content:
    :return:
    """
    sizer = wx.BoxSizer(wx.VERTICAL)
    if margin == 0:
        sizer.Add(content, 0, wx.EXPAND)
    else:
        sizer.Add(content, 0, wx.EXPAND | wx.ALL, margin)
    content.GetParent().SetSizer(sizer)


class DeviceProfile():

    def __init__(self,  name,
                        tooldiameter = None,
                        feedrate = None,
                        spindlespeed = None,
                        toolcode = None,
                        coolant = None,
                        zup = None,
                        zdown = None):
        self.name = name
        self.tooldiameter = tooldiameter
        self.feedrate = feedrate
        self.spindlespeed = spindlespeed
        self.toolcode = toolcode
        self.coolant = coolant
        self.zup = zup
        self.zdown = zdown


class MyPopupMenu(wx.Menu):
    def __init__(self, lazorApp, pos):
        wx.Menu.__init__(self)

        self.pos = pos
        self.lazorApp = lazorApp
        """ :type lazorApp: LazorAppFrame """

        item = wx.MenuItem(self, wx.NewId(), "Set measuring point")
        self.AppendItem(item)
        self.Bind(wx.EVT_MENU, self.OnItem1, item)

        item = wx.MenuItem(self, wx.NewId(), "Cancel measurement")
        self.AppendItem(item)
        self.Bind(wx.EVT_MENU, self.OnItem2, item)

        self.AppendSeparator()

        item = wx.MenuItem(self, wx.NewId(),"Set custom origin")
        self.AppendItem(item)
        self.Bind(wx.EVT_MENU, self.OnItem3, item)

    def OnItem1(self, event):
        self.lazorApp.canvas.startMeasurement(self.pos)

    def OnItem2(self, event):
        self.lazorApp.canvas.stopMeasurement()

    def OnItem3(self, event):
        self.lazorApp.setCustomOrigin(self.pos)


class LazorAppFrame(wx.Frame):
    """ Main App frame"""

    deviceProfiles = [DeviceProfile("g: g code file", "0.008", "100", "1000", "1", False, "0.05", "-0.005"),
                      DeviceProfile("l: LaZoR code file", "0.004", "100", "100", "1", False, None, None)]

    def __init__(self, parent=None):
        super(LazorAppFrame, self).__init__(parent, title="LaZoR",
            size=(800, 600),
            style=wx.DEFAULT_FRAME_STYLE|wx.NO_FULL_REPAINT_ON_RESIZE)

        # Create status bar
        self.CreateStatusBar()
        self.GetStatusBar().SetFieldsCount(4)
        self.SetStatusWidths([-1, 125, 125, 125])

        # Setting up the menu.
        self.loadMenu()

        # Set up frame contents
        self.canvas = canvas = GerberCanvas(self, self.GetStatusBar(), 1)  # shows gerber data
        canvas.Bind(wx.EVT_RIGHT_UP, self.OnRightClick, canvas)
        toolapanel = self.loadToolsPanel()
        self.layersPanel = layersPanel = LayersPanel(self)
        layersPanel.loadLayersPanel(None, self.NotifyDataChange)

        self.sizerH1 = sizerH1 = wx.BoxSizer(wx.HORIZONTAL)
        sizerH1.Add(toolapanel, 0, wx.EXPAND)
        sizerH1.Add(canvas, 1, wx.EXPAND)
        sizerH1.Add(layersPanel, 0, wx.EXPAND)

        self.SetSizer(sizerH1)
        self.SetAutoLayout(True)
        sizerH1.Fit(self)

        # Initialise variables
        self.contours = None
        self.boundarys = None
        self.pcb_edges = None
        self.data = None
        """ :type data: GerberData """

    def loadMenu(self):
        filemenu = wx.Menu()
        menuAbout = filemenu.Append(wx.ID_ABOUT, "&About"," Information about this program")
        filemenu.AppendSeparator()
        menuExit = filemenu.Append(wx.ID_EXIT,"E&xit"," Terminate the program")

        filemenu2 = wx.Menu()
        zoomin = filemenu2.Append(wx.ID_ANY, "Zoom In")
        zoomout = filemenu2.Append(wx.ID_ANY, "Zoom Out")
        menuFitToView = filemenu2.Append(wx.ID_ANY, "Fit to View")
        filemenu2.AppendSeparator()
        self.menuLayerEditor = filemenu2.AppendCheckItem(wx.ID_ANY, "Show/Hide layer editor")
        filemenu2.Check(self.menuLayerEditor.GetId(), True)

        # Create the menubar.
        menuBar = wx.MenuBar()
        menuBar.Append(filemenu,"&File")
        menuBar.Append(filemenu2, "&View")
        self.SetMenuBar(menuBar)

        # Set events.
        self.Bind(wx.EVT_MENU, self.OnAbout, menuAbout)
        self.Bind(wx.EVT_MENU, self.OnExit, menuExit)
        self.Bind(wx.EVT_MENU, self.OnShowHideLayerEditor, self.menuLayerEditor)
        self.Bind(wx.EVT_MENU, self.OnZoomIn, zoomin)
        self.Bind(wx.EVT_MENU, self.OnZoomOut, zoomout)
        self.Bind(wx.EVT_MENU, self.OnFitToView, menuFitToView)

    def loadToolsPanel(self):
        panel = wx.lib.scrolledpanel.ScrolledPanel(self, size=(300, 0))
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizerH1 = wx.BoxSizer(wx.HORIZONTAL)
        sizerH1.Add(wx.StaticText(panel, -1, "Units: "), 0, wx.FIXED | wx.TOP | wx.RIGHT, 3)
        self.unitcombo = wx.ComboBox(panel, -1, "in", choices=["mm","in"], style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, self.hdl)
        sizerH1.Add(self.unitcombo, 0, wx.FIXED | wx.ALIGN_BOTTOM)
        self.nativeLabel = wx.StaticText(panel, -1)
        sizerH1.AddSpacer(10)
        sizerH1.Add(self.nativeLabel, 0, wx.FIXED | wx.TOP, 3)
        sizer.Add(sizerH1, 0, wx.EXPAND | wx.ALL, 10)

        deviceNames = []
        for dp in self.deviceProfiles: deviceNames.append(dp.name)
        self.devicecombo = wx.ComboBox(panel, -1, deviceNames[0], style=wx.CB_READONLY, choices=deviceNames)
        fontMono = self.devicecombo.GetFont()
        fontMono = wx.Font(fontMono.GetPointSize(), wx.TELETYPE,
                           fontMono.GetStyle(),
                           fontMono.GetWeight(), fontMono.GetUnderlined())
        self.devicecombo.SetFont(fontMono)
        self.Bind(wx.EVT_COMBOBOX, self.OnDeviceCombo, self.devicecombo)

        sizerH2 = wx.BoxSizer(wx.HORIZONTAL)
        sizerH2.Add(wx.StaticText(panel, -1, "Output device: "), 0, wx.EXPAND | wx.TOP | wx.RIGHT, 4)
        sizerH2.Add(self.devicecombo, 0, wx.FIXED)
        sizer.Add(sizerH2, 0, wx.EXPAND | wx.ALL, 10)

        cp = PCP.PyCollapsiblePane(panel, label="Import Data", agwStyle=wx.CP_NO_TLW_RESIZE)
        self.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.OnPaneChanged, cp)
        self.loadToolsImportPanel(cp.GetPane())
        sizer.Add(cp, 0, wx.EXPAND)
        cp.Expand()

        cp = PCP.PyCollapsiblePane(panel, label="Isolation Workbench", agwStyle=wx.CP_NO_TLW_RESIZE)
        self.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.OnPaneChanged, cp)
        self.loadToolsIsolationPanel(cp.GetPane())
        sizer.Add(cp, 0, wx.EXPAND)

        cp = PCP.PyCollapsiblePane(panel, label="Drill Workbench", agwStyle=wx.CP_NO_TLW_RESIZE)
        self.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.OnPaneChanged, cp)
        self.loadToolsDrillPanel(cp.GetPane())
        sizer.Add(cp, 0, wx.EXPAND)

        cp = PCP.PyCollapsiblePane(panel, label="Edge Workbench", agwStyle=wx.CP_NO_TLW_RESIZE)
        self.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.OnPaneChanged, cp)
        self.loadToolsEdgePanel(cp.GetPane())
        sizer.Add(cp, 0, wx.EXPAND)

        self.OnDeviceCombo(0)

        panel.SetSizer(sizer)
        panel.SetAutoLayout(True)
        panel.SetupScrolling(False, True, scrollIntoView=False)
        return panel

    def loadToolsImportPanel(self, parent):
        panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)

        button1 = wx.Button(panel, -1, "Load Gerber")
        sizer.Add(button1, 0, wx.EXPAND | wx.ALL, 5)
        button2 = wx.Button(panel, -1, "Load Edge")
        sizer.Add(button2, 0, wx.EXPAND | wx.ALL, 5)
        button3 = wx.Button(panel, -1, "Load Drill")
        sizer.Add(button3, 0, wx.EXPAND | wx.ALL, 5)
        button4 = wx.Button(panel, -1, "Clear Drill Data")
        sizer.Add(button4, 0, wx.EXPAND | wx.ALL, 5)

        panel.Bind(wx.EVT_BUTTON, self.LoadGerberFile, button1)
        panel.Bind(wx.EVT_BUTTON, self.LoadEdgeFile, button2)
        panel.Bind(wx.EVT_BUTTON, self.LoadDrillFile, button3)
        panel.Bind(wx.EVT_BUTTON, self.ClearDrillData, button4)

        panel.SetSizer(sizer)
        sizedToFill(panel)
        return panel

    def loadToolsIsolationPanel(self, parent):
        panel = wx.Panel(parent)
        sizer = wx.FlexGridSizer(20, 2, 4, 0)
        sizer.AddGrowableCol(1, 1)
        sizer.SetFlexibleDirection(wx.VERTICAL)

        button1 = wx.Button(panel, -1, "Contour")
        button2 = wx.Button(panel, -1, "Raster")
        button3 = wx.Button(panel, -1, "Clear")
        panel.Bind(wx.EVT_BUTTON, self.addContour, button1)
        panel.Bind(wx.EVT_BUTTON, self.addToolpath, button2)
        panel.Bind(wx.EVT_BUTTON, self.clearToolpath, button3)

        self.showcutwidthcheckbox = wx.CheckBox(panel, -1, "Show cut-width")
        panel.Bind(wx.EVT_CHECKBOX, self.OnUpdateShowCutWidth, self.showcutwidthcheckbox)

        self.tooldiainput = wx.TextCtrl(panel, -1, "0.2")
        self.tooldiainput.SetToolTip(wx.ToolTip("Tool diameter using in units specified at top"))
        self.ncontourinput = wx.TextCtrl(panel, -1, "1")
        self.ncontourinput.SetToolTip(wx.ToolTip("Number of contours as positive integer"))
        self.contourundercutinput = wx.TextCtrl(panel, -1, "0.8")
        self.contourundercutinput.SetToolTip(wx.ToolTip("Contour overlap as decimal proportion"))
        self.rasteroverlapinput = wx.TextCtrl(panel, -1, "0.8")
        self.rasteroverlapinput.SetToolTip(wx.ToolTip("Raster overlap as decimal proportion"))

        sizer.Add(wx.StaticText(panel, -1, "Tool diameter"), 0, wx.EXPAND | wx.TOP, 4)
        sizer.Add(self.tooldiainput, 0, wx.EXPAND)
        sizer.Add(wx.StaticText(panel, -1, "N contour"), 0, wx.EXPAND | wx.TOP, 4)
        sizer.Add(self.ncontourinput, 0, wx.EXPAND)
        sizer.Add(wx.StaticText(panel, -1, "Contour undercut"), 0, wx.EXPAND | wx.TOP, 4)
        sizer.Add(self.contourundercutinput, 0, wx.EXPAND)
        sizer.Add(wx.StaticText(panel, -1, "Raster overlap"), 0, wx.EXPAND | wx.TOP, 4)
        sizer.Add(self.rasteroverlapinput, 0, wx.EXPAND)
        sizer.AddSpacer(0)
        sizer.Add(self.showcutwidthcheckbox, 0, wx.EXPAND)
        sizer.AddSpacer(0)
        sizer.Add(button1, 0, wx.FIXED)
        sizer.AddSpacer(0)
        sizer.Add(button2, 0, wx.FIXED)
        sizer.AddSpacer(0)
        sizer.Add(button3, 0, wx.FIXED)

        sizer.AddSpacer(1)
        sizer.AddSpacer(1)

        button1 = wx.Button(panel, -1, "Output File")
        button2 = wx.Button(panel, -1, "Write Toolpath")
        panel.Bind(wx.EVT_BUTTON, self.OnChooseOutputFile, button1)
        panel.Bind(wx.EVT_BUTTON, self.OnWriteToolpath, button2)

        self.feedrateinput = wx.TextCtrl(panel, -1, "100")
        self.spindlespeedinput = wx.TextCtrl(panel, -1, "1000")
        self.toolinput = wx.TextCtrl(panel, -1, "1")
        self.zupinput = wx.TextCtrl(panel, -1, "0.05")
        self.zdowninput = wx.TextCtrl(panel, -1, "-0.005")
        self.fileoutputinput = wx.TextCtrl(panel, -1, "out.g")

        self.coolantcheckbox = wx.CheckBox(panel, -1, "Coolant")

        self.origincombo = wx.ComboBox(panel, -1, style=wx.CB_READONLY,
                choices=["File Origin", "Centre", "Top Left", "Bottom Left", "Top Right", "Bottom Right", "Custom"])
                # The last of origin combo choices MUST be custom.
        self.origincombo.SetSelection(0)
        self.Bind(wx.EVT_COMBOBOX, self.OnOriginChoose, self.origincombo)

        sizer.Add(wx.StaticText(panel, -1, "Output origin"), 0, wx.EXPAND | wx.TOP, 4)
        sizer.Add(self.origincombo, 0, wx.EXPAND)
        sizer.Add(wx.StaticText(panel, -1, "Feed rate"), 0, wx.EXPAND | wx.TOP, 4)
        sizer.Add(self.feedrateinput, 0, wx.EXPAND)
        sizer.Add(wx.StaticText(panel, -1, "Spindle speed"), 0, wx.EXPAND | wx.TOP, 4)
        sizer.Add(self.spindlespeedinput, 0, wx.EXPAND)
        sizer.Add(wx.StaticText(panel, -1, "Tool"), 0, wx.EXPAND | wx.TOP, 4)
        sizer.Add(self.toolinput, 0, wx.EXPAND)
        sizer.AddSpacer(0)
        sizer.Add(self.coolantcheckbox, 0, wx.EXPAND)
        sizer.Add(wx.StaticText(panel, -1, "Z up"), 0, wx.EXPAND | wx.TOP, 4)
        sizer.Add(self.zupinput, 0, wx.EXPAND)
        sizer.Add(wx.StaticText(panel, -1, "Z down"), 0, wx.EXPAND | wx.TOP, 4)
        sizer.Add(self.zdowninput, 0, wx.EXPAND)
        sizer.Add(button1, 0, wx.EXPAND | wx.RIGHT, 4)
        sizer.Add(self.fileoutputinput, 0, wx.EXPAND)
        sizer.AddSpacer(0)
        sizer.Add(button2, 0, wx.EXPAND)

        panel.SetSizer(sizer)
        panel.SetAutoLayout(True)
        sizedToFill(panel, 12)
        return panel

    def loadToolsDrillPanel(self, parent):
        panel = wx.Panel(parent)
        sizer = wx.FlexGridSizer(5, 2, 4, 4)
        sizer.AddGrowableCol(1, 1)
        sizer.SetFlexibleDirection(wx.BOTH)

        # button1 = wx.Button(panel, -1, "Output File")
        # button2 = wx.Button(panel, -1, "Write Toolpath")
        # panel.Bind(wx.EVT_BUTTON, self.OnChooseOutputFile, button1)
        # panel.Bind(wx.EVT_BUTTON, self.OnWriteToolpath, button2)
        #
        # self.feedrateinput = wx.TextCtrl(panel, -1, "100")
        # self.spindlespeedinput = wx.TextCtrl(panel, -1, "1000")
        # self.toolinput = wx.TextCtrl(panel, -1, "1")
        # self.zupinput = wx.TextCtrl(panel, -1, "0.05")
        # self.zdowninput = wx.TextCtrl(panel, -1, "-0.005")
        # self.fileoutputinput = wx.TextCtrl(panel, -1, "out.g")
        #
        # self.coolantcheckbox = wx.CheckBox(panel, -1, "Coolant")
        #
        # self.origincombo = wx.ComboBox(panel, -1, style=wx.CB_READONLY,
        #         choices=["File Origin", "Centre", "Top Left", "Bottom Left", "Top Right", "Bottom Right", "Custom"])
        # self.origincombo.SetSelection(0)
        # self.Bind(wx.EVT_COMBOBOX, self.OnOriginChoose, self.origincombo)
        #
        # sizer.Add(wx.StaticText(panel, -1, "Output origin"), 0, wx.EXPAND | wx.TOP, 4)
        # sizer.Add(self.origincombo, 0, wx.EXPAND)
        # sizer.Add(wx.StaticText(panel, -1, "Feed rate"), 0, wx.EXPAND | wx.TOP, 4)
        # sizer.Add(self.feedrateinput, 0, wx.EXPAND)
        # sizer.Add(wx.StaticText(panel, -1, "Spindle speed"), 0, wx.EXPAND | wx.TOP, 4)
        # sizer.Add(self.spindlespeedinput, 0, wx.EXPAND)
        # sizer.Add(wx.StaticText(panel, -1, "Tool"), 0, wx.EXPAND | wx.TOP, 4)
        # sizer.Add(self.toolinput, 0, wx.EXPAND)
        # sizer.AddSpacer(0)
        # sizer.Add(self.coolantcheckbox, 0, wx.EXPAND)
        # sizer.Add(wx.StaticText(panel, -1, "Z up"), 0, wx.EXPAND | wx.TOP, 4)
        # sizer.Add(self.zupinput, 0, wx.EXPAND)
        # sizer.Add(wx.StaticText(panel, -1, "Z down"), 0, wx.EXPAND | wx.TOP, 4)
        # sizer.Add(self.zdowninput, 0, wx.EXPAND)
        # sizer.Add(button1, 0, wx.EXPAND)
        # sizer.Add(self.fileoutputinput, 0, wx.EXPAND)
        # sizer.AddSpacer(0)
        # sizer.Add(button2, 0, wx.EXPAND)

        panel.SetSizer(sizer)
        panel.SetAutoLayout(True)
        sizedToFill(panel, 12)
        return panel

    def loadToolsEdgePanel(self, parent):
        panel = wx.Panel(parent)
        sizer = wx.FlexGridSizer(5, 2, 4, 4)
        sizer.AddGrowableCol(1, 1)
        sizer.SetFlexibleDirection(wx.BOTH)

        panel.SetSizer(sizer)
        panel.SetAutoLayout(True)
        sizedToFill(panel, 12)
        return panel

    def hdl(self, evt):
        self.canvas.setUnit(self.unitcombo.GetCurrentSelection())

    def OnAbout(self, evt):
        dlg = wx.MessageDialog( self, join(["LaZoR ", VERSION, "\n", DATE]), "About", wx.OK)
        dlg.ShowModal()
        dlg.Destroy()

    def OnExit(self, evt):
        self.Close(True)

    def OnZoomIn(self, evt):
        self.canvas.zoomrel(1.25)

    def OnZoomOut(self, evt):
        self.canvas.zoomrel(1 / 1.25)

    def OnFitToView(self, evt):
        if self.data is None: return
        self.canvas.autoscale_cac()
        self.canvas.Refresh()

    def OnShowHideLayerEditor(self, evt):
        if self.menuLayerEditor.IsChecked():
            self.layersPanel.Show()
        else:
            self.layersPanel.Hide()
        self.layersPanel.GetParent().Layout()

    def OnPaneChanged(self, evt):
        self.Layout()
        self.Refresh()

    def OnChooseOutputFile(self, evt):
        dlg = wx.FileDialog(self, "Choose g-code output file", "", "",
                            "All Files (*.*)|*",
                            wx.FD_SAVE)

        if dlg.ShowModal() == wx.ID_CANCEL: return
        self.fileoutputinput.SetValue(dlg.GetPath())
        dlg.Destroy()

    def OnDeviceCombo(self, evt):
        dp = self.deviceProfiles[self.devicecombo.GetSelection()]

        self.setComp(self.tooldiainput, dp.tooldiameter)
        self.setComp(self.feedrateinput, dp.feedrate)
        self.setComp(self.spindlespeedinput, dp.spindlespeed)
        self.setComp(self.toolinput, dp.toolcode)
        self.setComp(self.zupinput, dp.zup)
        self.setComp(self.zdowninput, dp.zdown)

        if dp.coolant is None:
            self.coolantcheckbox.SetValue(False)
            self.coolantcheckbox.Disable()
        else:
            self.coolantcheckbox.Enable()
            self.coolantcheckbox.SetValue(dp.coolant)

        self.contours = []
        self.contoolpaths = []
        self.canvas.toolpaths = []
        self.canvas.updateToolpathData()
        self.NotifyDataChange()

    def OnWriteToolpath(self, evt):
        # TODO: should be more generic than this
        if self.devicecombo.GetSelection() == 0:
            self.write_G()
        else:
            self.write_l()

    def OnOriginChoose(self, evt):
        if self.data is None: return
        choice = self.origincombo.GetSelection()
        # "File Origin", "Centre", "Top Left", "Bottom Left", "Top Right", "Bottom Right", "Custom"
        data = self.data
        if choice == 0:  # file origin
            data.originx = 0
            data.originy = 0
        elif choice == 1:  # centre
            data.originx = (data.xmax + data.xmin) / 2.0
            data.originy = (data.ymax + data.ymin) / 2.0
        elif choice == 2:  # top left
            data.originx = data.xmin
            data.originy = data.ymax
        elif choice == 3:  # bottom left
            data.originx = data.xmin
            data.originy = data.ymin
        elif choice == 4:  # top right
            data.originx = data.xmax
            data.originy = data.ymax
        elif choice == 5:  # bottom right
            data.originx = data.xmax
            data.originy = data.ymin
        elif choice == 6:  # custom
            return
        self.NotifyDataChange()

    def OnRightClick(self, evt):
        if self.data is None: return
        menu = MyPopupMenu(self, evt.GetPosition())
        self.canvas.PopupMenu(menu, evt.GetPosition())
        menu.Destroy()

    def setCustomOrigin(self, (mx, my)):
        x, y = self.canvas.GetViewStart()
        self.data.originx = self.canvas.MouseToInternalX(mx + x)
        self.data.originy = self.canvas.MouseToInternalY(my + y)
        self.origincombo.SetSelection(self.origincombo.GetCount() - 1)  # set to custom option
        self.NotifyDataChange()

    def LoadGerberFile(self, evt):
        dlg = wx.FileDialog(self, "Open Gerber file", "", "",
                            "Gerber Files (*.gbl;*.gtl;*.gbr;*.cmp)|*.gbl;*.gtl;*.gbr;*.cmp|All Files (*.*)|*",
                            wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_CANCEL:
            self.SetStatusText("Load Gerber file cancelled by user", 0)
            return
        filename = dlg.GetPath()
        dlg.Destroy()

        self.SetStatusText("Loading Gerber: " + filename + "...", 0)

        [data, tracks] = load_file(filename)
        self.data = data

        xmin = 1E99
        xmax = -1E99
        ymin = 1E99
        ymax = -1E99

        sum1 = 0
        sumReg = 0
        sumBound = 0
        sumTracks = 0
        sumPads = 0

        cbounds = pyclipper.Pyclipper()
        boundarys = []
        pcb_edges = []

        layers = list(data.layers)
        for gl in layers:
            if gl.type == GerberLayer.TYPE_PCBEDGE:
                data.layers.remove(gl)
                pcb_edges.extend(gl.points)
                for segment in gl.points:
                    sum1 += len(segment)
                    for vertex in segment:
                        x = vertex[0]
                        y = vertex[1]
                        if x < xmin: xmin = x
                        if x > xmax: xmax = x
                        if y < ymin: ymin = y
                        if y > ymax: ymax = y
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
                # if gl.isDark:
                #     # boundarys.extend(gl.points)
                #     # if len(boundarys) == 0:
                #         boundarys.extend(gl.points)
                #     # else:
                #     #     cbounds.AddPaths(boundarys, pyclipper.PT_SUBJECT)
                #     #     cbounds.AddPaths(gl.points, pyclipper.PT_SUBJECT)
                #     #     boundarys = cbounds.Execute(pyclipper.CT_UNION, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)
                #     #     cbounds.Clear()
                # else:
                #     cbounds.AddPaths(boundarys, pyclipper.PT_SUBJECT)
                #     cbounds.AddPaths(gl.points, pyclipper.PT_CLIP)
                #     boundarys = cbounds.Execute(pyclipper.CT_DIFFERENCE, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)
                #     cbounds.Clear()
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
                        x = vertex[0]
                        y = vertex[1]
                        if x < xmin: xmin = x
                        if x > xmax: xmax = x
                        if y < ymin: ymin = y
                        if y > ymax: ymax = y
                continue
            if gl.type == GerberLayer.TYPE_MERGEDCOPPER:
                data.layers.remove(gl)
                continue

        print "   fraction = ",self.data.fraction
        print "   found", sumBound, "polygons,", sum1, "vertices"
        print "   found", sumReg, "pours"
        print "   found", sumTracks, "tracks"
        print "   found", sumPads, "pads"
        print "   found", len(pcb_edges), "edge segments"
        print "   xmin: %0.3g " % xmin, "xmax: %0.3g " % xmax, "dx: %0.3g " % (xmax - xmin)
        print "   ymin: %0.3g " % ymin, "ymax: %0.3g " % ymax, "dy: %0.3g " % (ymax - ymin)

        data.xmin2 = xmin
        data.xmax2 = xmax
        data.ymin2 = ymin
        data.ymax2 = ymax

        if len(pcb_edges) == 0:
            outer_offset = (1 if data.units == 0 else 0.03937) * 10**data.fraction  # 1 mm
            # outer_offset = 0.01 * 10**data.fraction
            xmin -= outer_offset
            ymin -= outer_offset
            xmax += outer_offset
            ymax += outer_offset
            pcb_edge = [[xmax, ymax], [xmax, ymin], [xmin, ymin], [xmin, ymax], [xmax, ymax]]
            pcb_edges.append(pcb_edge)

        self.pcb_edges = pcb_edges
        self.boundarys = boundarys = pyclipper.SimplifyPolygons(boundarys, pyclipper.PFT_NONZERO)
        # boundarys = GerberReader3.replace_holes_with_seams(boundarys)
        GerberReader3.closeOffPolys(boundarys)

        data.layers.append(GerberLayer(True, "PCB Edge", pcb_edges, True, False, "blue", GerberLayer.TYPE_PCBEDGE))
        data.layers.append(GerberLayer(True, "Merged Copper", boundarys, False, color="brown", type=GerberLayer.TYPE_MERGEDCOPPER))

        # PCB bounds
        data.xmin = xmin
        data.xmax = xmax
        data.ymin = ymin
        data.ymax = ymax

        # View bounds
        # Includes the origin
        if xmin > 0: xmin = 0
        if xmax < 0: xmax = 0
        if ymin > 0: ymin = 0
        if ymax < 0: ymax = 0

        # Add margin
        ww = (xmax - xmin)*0.1
        hh = (ymax - ymin)*0.1
        xmin -= ww
        xmax += ww
        ymin -= hh
        ymax += hh

        self.contours = []
        self.layersPanel.loadLayersPanel(data, self.NotifyDataChange)
        self.canvas.loadData2(self.data, xmin, xmax, ymin, ymax)
        self.SetStatusText("Load Gerber file completed successfully", 0)
        self.origincombo.SetSelection(0)
        self.nativeLabel.SetLabelText("(File unit: %s, Dec. places: %0d)" % ("mm" if data.units == 0 else "in", data.fraction))

    def LoadEdgeFile(self, evt):
        if self.data is None:
            dlg = wx.MessageDialog(self, "You must load a Gerber file first", "Error", wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
            return

        dlg = wx.FileDialog(self, "Open edge file", "", "",
                            "Gerber Files (*.gml;*.gbl;*.gtl;*.gbr;*.cmp)|*.gml;*.gbl;*.gtl;*.gbr;*.cmp|All Files (*.*)|*",
                            wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_CANCEL:
            self.SetStatusText("Load edge file cancelled by user", 0)
            return
        filename = dlg.GetPath()
        dlg.Destroy()

        self.SetStatusText("Loading edge: " + filename + "...", 0)

        [data, edges] = load_file(filename)
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
                found = False
                for seg in edges:
                    if abs(seg[0][0] - endpnt[0]) < 10:
                        if abs(seg[0][1] - endpnt[1]) < 10:
                            brdoutline[brdseg].extend(seg)
                            edges.remove(seg)
                            endpnt = brdoutline[brdseg][len(brdoutline[brdseg]) - 1]
                            found = True
                            break
                    if abs(seg[len(seg) - 1][0] - endpnt[0]) < 10:
                        if abs(seg[len(seg) - 1][1] - endpnt[1]) < 10:
                            edges.remove(seg)
                            seg = seg[::-1]
                            brdoutline[brdseg].extend(seg)
                            endpnt = brdoutline[brdseg][len(brdoutline[brdseg]) - 1]
                            found = True
                            break
                if not found:
                    dlg = wx.MessageDialog(self, "Edge outline cannot contain any gaps.\n"
                                                 "No changes were made.", "Load edge file failed",
                                           wx.OK | wx.ICON_ERROR)
                    dlg.ShowModal()
                    dlg.Destroy()
                    self.SetStatusText("Load edge failed", 0)
                    return

        xmin = 1E99
        xmax = -1E99
        ymin = 1E99
        ymax = -1E99
        if data.units == self.data.units:
            for poly in brdoutline:
                for (x, y) in poly:
                    if x < xmin: xmin = x
                    if x > xmax: xmax = x
                    if y < ymin: ymin = y
                    if y > ymax: ymax = y
        else:
            # finx bounds and convert units of data at same time
            conv = 25.4 if data.units == 1 else 1/25.4
            print " Unit conversion of edge file data"
            for poly in brdoutline:
                for pt in poly:
                    x = pt[0] = int(pt[0] * conv)
                    y = pt[1] = int(pt[1] * conv)
                    if x < xmin: xmin = x
                    if x > xmax: xmax = x
                    if y < ymin: ymin = y
                    if y > ymax: ymax = y

        # Check if PCB fits inside edge. We're lazy so we just use box bounds (should really use
        # polygon bounds checking).
        eps = 10
        if self.data.xmin2 + eps < xmin or self.data.xmax2 - eps > xmax or \
                self.data.ymin2 + eps < ymin or self.data.ymax2 - eps > ymax:
            print self.data.xmin, xmin
            print self.data.ymin, ymin
            print self.data.xmax, xmax
            print self.data.ymax, ymax
            dlg = wx.MessageDialog(self, "The loaded edge does not fully contain the PCB board.\n"
                                         "Do you still wish to proceed using this edge file?",
                                   "PCB board extends past edge boundary", wx.YES | wx.NO | wx.ICON_WARNING)
            ans = dlg.ShowModal()
            dlg.Destroy()
            if ans != wx.ID_YES:
                self.SetStatusText("Load edge file cancelled by user", 0)
                return

        self.data.xmin = xmin
        self.data.xmax = xmax
        self.data.ymin = ymin
        self.data.ymax = ymax

        # View bounds
        # Includes the origin
        if xmin > 0: xmin = 0
        if xmax < 0: xmax = 0
        if ymin > 0: ymin = 0
        if ymax < 0: ymax = 0

        # Add margin
        ww = (xmax - xmin)*0.1
        hh = (ymax - ymin)*0.1
        xmin -= ww
        xmax += ww
        ymin -= hh
        ymax += hh

        pcb_edges = brdoutline
        pcb_edges = pyclipper.CleanPolygons(pcb_edges)
        for poly in pcb_edges:
            poly.append(poly[0])  # close off polygons

        # Remove existing edge
        layers = list(self.data.layers)
        for gl in layers:
            if gl.type == GerberLayer.TYPE_PCBEDGE: self.data.layers.remove(gl)

        # Add edge data to existing data
        self.data.layers.insert(-1, GerberLayer(True, "PCB Edge", pcb_edges, True, False, "blue", GerberLayer.TYPE_PCBEDGE))
        self.pcb_edges = pcb_edges

        self.canvas.toolpaths = []
        self.canvas.loadData2(self.data, xmin, xmax, ymin, ymax)
        self.layersPanel.loadLayersPanel(self.data, self.NotifyDataChange)
        self.SetStatusText("Load edge file completed successfully", 0)

    def LoadDrillFile(self, evt=None):
        if self.data is None:
            dlg = wx.MessageDialog(self, "You must load a Gerber file first", "Error", wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
            return

        dlg = wx.FileDialog(self, "Open edge file", "", "",
                            "Drill files (*.drl;*.dbd;*.txt)|*.drl;*.dbd;*.txt|All Files (*.*)|*",
                            wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_CANCEL:
            self.SetStatusText("Load drill file cancelled by user", 0)
            return
        filename = dlg.GetPath()
        dlg.Destroy()

        self.SetStatusText("Loading drill: " + filename + "...", 0)

        [drillPts, units] = ExcellonReader.load_file(filename)
        fscale = 10**self.data.fraction
        if self.data.units != units:
            print "Conversion of drill file coords required"
            if units == 0:
                # mm -> in
                fscale *= 25.4
            else:
                # in -> mm
                fscale /= 25.4
        drillPts2 = []
        for (x, y, dia) in drillPts:
            drillPts2.append([int(x*fscale), int(y*fscale), int(dia*fscale)])
        self.canvas.drillPts = drillPts2
        print "  Loaded ", len(drillPts), " drill points"

        self.SetStatusText("Load drill file completed successfully", 0)
        self.NotifyDataChange()

    def ClearDrillData(self, evt):
        self.canvas.drillPts = []
        self.NotifyDataChange()
        self.SetStatusText("Drill data removed", 0)

    def OnUpdateShowCutWidth(self, evt):
        self.canvas.toolpathlinewidth = float(self.tooldiainput.GetValue()) \
            if self.showcutwidthcheckbox.IsChecked() else 0
        self.NotifyDataChange()

    def addContour(self, evt=None):
        if self.data is None: return
        print "contouring boundary ..."
        self.contours = []
        N_contour = int(self.ncontourinput.GetValue())
        overlap = float(self.contourundercutinput.GetValue())
        if self.showcutwidthcheckbox.IsChecked(): self.canvas.toolpathlinewidth = float(self.tooldiainput.GetValue())

        toolpaths = self.canvas.toolpaths = []

        toolrad = float(self.tooldiainput.GetValue()) / 2.0 / self.canvas.mousescale
        self.contours = self.offset_poly(self.boundarys, toolrad)
        toolpaths.extend(self.contours)
        delrad = overlap * toolrad
        for n in range(1, N_contour):
            toolrad += delrad
            self.contours = self.offset_poly(self.boundarys, toolrad)
            toolpaths.extend(self.contours)

        toolpaths.extend(self.pcb_edges)
        for seg in toolpaths:
            if len(seg) > 0:
                seg.append(seg[0])
        self.contoolpaths = list(toolpaths)  # cache to allow multiple raster
        self.canvas.updateToolpathData()  # update toolpath cahce of wxGerberCanvas - this is to workaround a bug

        print "   done"
        self.SetStatusText("Contour completed", 0)
        self.NotifyDataChange()

    def clearToolpath(self, evt=None):
        self.contours = []
        self.contoolpaths = []
        self.canvas.toolpaths = []
        self.NotifyDataChange()
        self.SetStatusText("Toolpath data removed", 0)

    def addToolpath(self, evt=None):
        # previously called raster operation
        if self.data is None: return
        print "rastering interior ..."
        tooldia = float(self.tooldiainput.GetValue()) / self.canvas.mousescale
        if self.showcutwidthcheckbox.IsChecked(): self.canvas.toolpathlinewidth = float(self.tooldiainput.GetValue())

        self.canvas.toolpaths = []
        if self.contours == []:
            edgepath = self.boundarys
            delta = tooldia / 2.0
        else:
            edgepath = self.contours
            self.canvas.toolpaths.extend(self.contoolpaths)
            delta = 0  # tooldia/4.0
        pcbedges = self.pcb_edges
        # pcbedges = []
        # for layer in self.pcb_edges:
        #     tmp = []
        #     for seg in layer:
        #         tmp.append(seg[0] + xoff, seg[0] + yoff)
        rasterpath = self.raster_area(edgepath, pcbedges, delta, self.data.ymin, self.data.ymax, self.data.xmin, self.data.xmax)
        # toolpaths[0].extend(pyclipper.PolyTreeToPaths(rasterpath))
        self.canvas.toolpaths.extend(rasterpath)
        self.canvas.updateToolpathData()  # update toolpath cahce of wxGerberCanvas - this is to workaround a bug

        print "   done"
        self.SetStatusText("Raster completed", 0)
        self.NotifyDataChange()

    def raster_area(self, edgepath, pcbedges, delta, ymin1, ymax1, xmin1, xmax1):
        #
        # raster a 2D region
        #
        # find row-edge intersections
        #
        overlap = float(self.rasteroverlapinput.GetValue())
        tooldia = float(self.tooldiainput.GetValue()) / self.canvas.mousescale
        rastlines = []
        starty = ymin1
        endy = ymax1
        startx = round(xmax1, 2)
        endx = round(xmin1, 2)
        numrows = int(math.floor((endy - starty) / (tooldia * overlap)))
        crast = pyclipper.Pyclipper()
        edgepath = self.offset_poly(edgepath, delta)
        result = []

        for row in range(numrows + 1):
            rastlines.append([])
            ty = round(starty + row * (tooldia * overlap), 4)
            rastlines[row].append([startx, ty])
            rastlines[row].append([endx, ty])
            startx, endx = endx, startx

        tmp = []
        for i in range(numrows):
            tmp.append(rastlines[i][0][1])

        crast.AddPaths(pcbedges, pyclipper.PT_CLIP,True)
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
            if segs[0][0] < segs[1][0]:
                rastltor.append(segs)
            else:
                rastrtol.append(segs)
        rastltor.sort(key=lambda x: (x[0][1], x[0][0]))
        rastrtol.sort(key=lambda x: (x[0][1], -x[0][0]))

        result.extend(rastltor)
        result.extend(rastrtol)
        result.sort(key=lambda x: x[0][1])

        return result

    def offset_poly(self, path, toolrad):
        c_osp = pyclipper.PyclipperOffset()
        c_osp.AddPaths(path, pyclipper.JT_SQUARE, pyclipper.ET_CLOSEDPOLYGON)
        polyclip = c_osp.Execute(toolrad)

        polyclip = pyclipper.CleanPolygons(polyclip)

        c_osp.Clear()
        return polyclip

    def write_G(self):
        #
        # G code output
        #
        data = self.data
        scale = self.canvas.mousescale  # NOTE: this takes units into account as well!
        feed = float(self.feedrateinput.GetValue())
        zup = self.zupinput.GetValue()
        zdown = self.zdowninput.GetValue()
        xoff = -data.originx * scale
        yoff = -data.originy * scale
        cool = self.coolantcheckbox.IsChecked()
        text = self.fileoutputinput.GetValue()
        file = open(text, 'w')
        # file.write("%\n")
        file.write("G20\n")
        file.write("T" + self.toolinput.GetValue() + "M06\n")  # tool
        file.write("G90 G54\n")  # absolute positioning with respect to set origin
        file.write("F%0.3f\n" % feed)  # feed rate
        file.write("S" + self.spindlespeedinput.GetValue() + "\n")  # spindle speed
        if cool: file.write("M08\n")  # coolant on
        file.write("G0 Z" + zup + "\n")  # move up before starting spindle
        file.write("M3\n")  # spindle on clockwise
        nsegment = 0

        if self.canvas.toolpaths == []:
            path = self.boundarys
        else:
            path = self.canvas.toolpaths
        if zdown == " ":
            raise StandardError("This line has an error")
            # zdown = zoff + zmin + (layer-0.50)*dlayer
        else:
            zdown = float(self.zdowninput.GetValue())
        for segment in range(len(path)):
            nsegment += 1
            vertex = 0
            x = path[segment][vertex][0] * scale + xoff
            y = path[segment][vertex][1] * scale + yoff
            file.write("G0 X%0.4f " % x + "Y%0.4f " % y + "Z" + self.zupinput.GetValue() + "\n")  # rapid motion
            file.write("G1 Z%0.4f " % zdown + "\n")  # linear motion
            for vertex in range(1, len(path[segment])):
                x = path[segment][vertex][0] * scale + xoff
                y = path[segment][vertex][1] * scale + yoff
                file.write("G1 X%0.4f " % x + "Y%0.4f" % y + "\n")
            file.write("Z" + zup + "\n")
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
        file.write("G0 Z" + zup + "\n")  # move up before stopping spindle
        file.write("M5\n")  # spindle stop
        if cool: file.write("M09\n")  # coolant off
        file.write("M30\n")  # program end and reset
        # file.write("%\n")
        file.close()
        self.SetStatusText("Successfully written " + str(nsegment) + " G code toolpath segments to " + text, 0)

    def write_l(self):
        #
        # LaZoR Mk1 code output
        #
        data = self.data
        scale = self.canvas.mousescale  # NOTE: this takes units into account as well!
        # dlayer = float(sthickness.get())/zscale
        feed = float(self.feedrateinput.GetValue())
        xoff = -data.originx * scale
        yoff = -data.originy * scale
        cool = self.coolantcheckbox.IsChecked()
        text = self.fileoutputinput.GetValue()
        file = open(text, 'w')
        # file.write("%\n")
        # file.write("O1234\n")
        # file.write("T"+stool.get()+"M06\n") # tool
        file.write("G90G54\n")  # absolute positioning with respect to set origin
        # file.write("F%0.3f\n"%feed) # feed rate
        file.write("S" + str(float(self.spindlespeedinput.GetValue()) / 100) + "\n")  # spindle speed
        # if (cool == TRUE): file.write("M08\n") # coolant on
        # file.write("G00Z"+szup.get()+"\n") # move up before starting spindle
        # file.write("M03\n") # spindle on clockwise
        nsegment = 0
        for layer in range((len(self.boundarys) - 1), -1, -1):
            # FIXME: toolpath will not have same number of layers as boundarys
            if self.canvas.toolpaths[layer] == []:
                path = self.boundarys[layer]
            else:
                path = self.canvas.toolpaths[layer]
            ##      if (szdown.get() == " "):
            ##         zdown = zoff + zmin + (layer-0.50)*dlayer
            ##      else:
            ##         zdown = float(szdown.get())
            for segment in range(len(path)):
                ##         if (len(path[segment])==0):
                ##            continue
                nsegment += 1
                vertex = 0
                x = path[segment][vertex][0] * scale + xoff
                y = path[segment][vertex][1] * scale + yoff

                file.write("G00X%0.4f" % x + "Y%0.4f" % y + "\n")  # rapid motion
                # file.write("G01Z%0.4f"%zdown+"\n") # linear motion
                file.write("M03\n")
                for vertex in range(1, len(path[segment])):
                    x = path[segment][vertex][0] * scale + xoff
                    y = path[segment][vertex][1] * scale + yoff
                    file.write("G01X%0.4f" % x + "Y%0.4f" % y + "F%0.3f\n" % feed + "\n")

                # file.write("Z"+szup.get()+"\n")
                file.write("M05\n")
        # file.write("G00Z"+szup.get()+"\n") # move up before stopping spindle
        file.write("M05\n")  # spindle stop
        if cool: file.write("M09\n")  # coolant off
        file.write("M30\n")  # program end and reset
        # file.write("%\n")
        file.close()
        self.SetStatusText("Successfully written " + str(nsegment) + " LaZoR code toolpath segments to " + text, 0)

    def NotifyDataChange(self):
        self.canvas.redraw()
        self.canvas.Refresh()

    def setComp(self, comp, val):
        if val is None:
            comp.SetValue("")
            comp.Disable()
        else:
            comp.Enable()
            comp.SetValue(val)


class LayersPanel(wx.lib.scrolledpanel.ScrolledPanel):
    """ Gerber layer's editing panel """

    def __init__(self, parent):
        super(LayersPanel, self).__init__(parent, size=(300, 0))
        self.g = None
        self.data = None
        """ Gerber data  :type data: GerberData """
        self.notify = None
        """ Called when data has been modified """
        self.Col = -1

    def loadLayersPanel(self, data=None, change_notifier=None):
        """
        :type data: GerberData
        """
        if data is not None: self.data = data
        if change_notifier is not None: self.notify = change_notifier

        self.Freeze()

        if self.g is not None: self.DestroyChildren()

        g = wx.grid.Grid(self)
        self.g = g
        g.CreateGrid(0 if data is None else len(data.layers), 5)
        g.HideRowLabels()
        g.DisableDragRowSize()

        g.SetColLabelValue(0, "Name")
        g.SetColLabelValue(1, "  ")
        g.SetColLabelValue(2, "Visible")
        g.SetColLabelValue(3, "Filled")
        g.SetColLabelValue(4, "Colour")

        # get the cell attribute for the top left row
        # editor = layersPanel.GetCellEditor(0, 0)
        attr = wx.grid.GridCellAttr()
        attr.SetReadOnly(True)
        g.SetColAttr(0, attr)
        g.SetColAttr(1, attr)
        g.SetColAttr(4, attr)

        attr = wx.grid.GridCellAttr()
        attr.SetEditor(wx.grid.GridCellBoolEditor())
        attr.SetRenderer(wx.grid.GridCellBoolRenderer())
        g.SetColAttr(2, attr)
        g.SetColAttr(3, attr)

        g.SetColSize(0, 125)
        g.SetColSize(1, 25)
        g.SetColSize(2, 50)
        g.SetColSize(3, 50)
        g.SetColSize(4, 50)

        g.Bind(wx.grid.EVT_GRID_CELL_LEFT_CLICK, self.onMouse)
        g.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.onCellSelected)
        g.Bind(wx.grid.EVT_GRID_EDITOR_CREATED, self.onEditorCreated)

        if data is not None:
            r = 0
            for gl in data.layers:
                g.SetCellValue(r, 0, gl.name)
                g.SetCellValue(r, 1, "D" if gl.isDark else "C")
                g.SetCellValue(r, 2, '1' if gl.visible else '')
                g.SetCellValue(r, 3, '1' if gl.filled else '')
                g.SetCellBackgroundColour(r, 4, gl.color)
                if len(gl.points) == 0: g.SetCellTextColour(r, 0, "#808080")  # grey out empty layers
                r += 1

        # r = 0  # test values
        # self.SetCellValue(r, 0, "Test name")
        # self.SetCellValue(r, 1, "D")
        # self.SetCellValue(r, 2, '1')
        # self.SetCellValue(r, 3, '')
        # self.SetCellValue(r, 5, "green")

        sizedToFill(g)
        self.SetupScrolling(False, True)

        self.Thaw()

    # Methods below used to hack wx.grid to allow one click toggling of checkboxed
    # Also modified to activate colour picker

    def onMouse(self,evt):
        if evt.Col == 2 or evt.Col == 3:
            self.Col = evt.Col
            wx.CallLater(100, self.toggleCheckBox)
        elif evt.Col == 4:
            gl = self.data.layers[evt.Row]

            # Change colour
            cdata = wx.ColourData()
            cdata.SetColour(gl.color)
            cdata.ChooseFull = True
            dlg = wx.ColourDialog(self, cdata)
            if dlg.ShowModal() == wx.ID_OK:
                newcol = dlg.GetColourData().Colour.GetAsString(wx.C2S_HTML_SYNTAX)
                gl.color = newcol

                # update ui
                self.g.SetCellBackgroundColour(evt.Row, 4, gl.color)
                print gl.color, evt.Row
                self.notify()
                self.g.Refresh()
            dlg.Destroy()
        evt.Skip()

    def toggleCheckBox(self):
        self.cb.SetValue(not self.cb.Value)
        self.afterCheckBox(self.cb.Value)

    def onCellSelected(self, evt):
        if evt.Col == 2 or evt.Col == 3:
            self.Col = evt.Col
            wx.CallAfter(self.g.EnableCellEditControl)
        evt.Skip()

    def onEditorCreated(self, evt):
        if evt.Col == 2 or evt.Col == 3:
            self.cb = evt.Control
            self.Col = evt.Col
            self.cb.WindowStyle |= wx.WANTS_CHARS
            self.cb.Bind(wx.EVT_KEY_DOWN, self.onKeyDown)
            self.cb.Bind(wx.EVT_CHECKBOX, self.onCheckBox)
        evt.Skip()

    def onKeyDown(self, evt):
        if evt.KeyCode == wx.WXK_UP:
            if self.g.GridCursorRow > 0:
                self.g.DisableCellEditControl()
                self.g.MoveCursorUp(False)
        elif evt.KeyCode == wx.WXK_DOWN:
            if self.g.GridCursorRow < (self.g.NumberRows-1):
                self.g.DisableCellEditControl()
                self.g.MoveCursorDown(False)
        elif evt.KeyCode == wx.WXK_LEFT:
            if self.g.GridCursorCol > 0:
                self.g.DisableCellEditControl()
                self.g.MoveCursorLeft(False)
        elif evt.KeyCode == wx.WXK_RIGHT:
            if self.g.GridCursorCol < (self.g.NumberCols-1):
                self.g.DisableCellEditControl()
                self.g.MoveCursorRight(False)
        else:
            evt.Skip()

    def onCheckBox(self, evt):
        self.afterCheckBox(evt.IsChecked())
        evt.Skip()

    def afterCheckBox(self, isChecked):
        if self.Col == 2:
            self.data.layers[self.g.GridCursorRow].visible = isChecked
        else:
            self.data.layers[self.g.GridCursorRow].filled = isChecked
        self.notify()


#=======================================================

app = wx.App()
frame = LazorAppFrame()
frame.Show()
app.MainLoop()