from Tkinter import *
from GerberReader import GerberData, GerberLayer
from tkColorChooser import askcolor

__author__ = 'Thompson'


def createTable2(tframe, gerber_data, change_cmd):
    """
    Creates a table for editing visual properties of GerberData layers
    :type tframe: Frame
    :type gerber_data: GerberData
    """
    for widget in tframe.winfo_children():
        widget.destroy() # clear children
    Label(tframe, text="Name", relief=RIDGE, width=13).grid(row=0,column=0)
    Label(tframe, text=" ", relief=RIDGE, width=2).grid(row=0,column=1)
    Label(tframe, text="Visible", relief=RIDGE, width=8).grid(row=0,column=2)
    Label(tframe, text="Filled", relief=RIDGE, width=8).grid(row=0,column=3)
    Label(tframe, text="Colour", relief=RIDGE, width=12).grid(row=0,column=4,columnspan=2)
    r = 1
    for gl in gerber_data.layers:
        Label(tframe, text=gl.name.get(), relief=RIDGE, width=13).grid(row=r,column=0)
        Label(tframe, text=("D" if gl.isDark else "C"), relief=RIDGE, width=2).grid(row=r,column=1)
        Checkbutton(tframe, variable=gl.visible,relief=SUNKEN, command=change_cmd, width=5).grid(row=r,column=2)
        Checkbutton(tframe, variable=gl.filled, relief=SUNKEN, command=change_cmd, width=5).grid(row=r,column=3)
        b1 = Button(tframe, bg=gl.color.get(), relief=SUNKEN, width=1)
        b1.grid(row=r,column=4)
        l1 = Label(tframe, text=gl.color.get(), relief=SUNKEN, width=10)
        l1.grid(row=r,column=5)

        def chgCol(gl=gl, b1=b1, l1=l1):
            tmp = askcolor(gl.color.get())[1]
            if tmp is None: return
            gl.color.set(tmp)
            b1.configure(bg=gl.color.get())
            l1.configure(text=gl.color.get())
            change_cmd()
        b1.configure(command=chgCol)

        r += 1

