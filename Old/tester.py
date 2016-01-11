import time
import Tkinter

import GerberReader
import GerberReader3

__author__ = 'Thompson'

folder = "gerber files/"
files = ["xbee_test_usb1_1-Front.gtl","xbee_test_usb1_1-Front2.gtl","feedbax2.gbl","feedbax2.gtl","PCB1.gtl"]#,"PCB1.gbl"]

root = Tkinter.Tk()
times = []


# cProfile.runctx("GerberReader.load_file(folder + files[3])", globals(),locals())
# cProfile.runctx("GerberReader2.load_file(folder + files[3])", globals(),locals())



# for n in range(5):
for f in files:
    stt = time.time()
    GerberReader.load_file(folder + f)
    stt = time.time() - stt;
    print " time = ", stt, " file ", f

    stt2 = time.time()
    GerberReader3.load_file(folder + f)
    stt2 = time.time() - stt2
    print " time = ", stt2, " file ", f

    # stt3 = time.time()
    # GerberReader3.load_file(folder + f)
    # stt3 = time.time() - stt3
    # print " time = ", stt3, " file ", f

    times.append([stt, stt2])
    # cProfile.runctx("GerberReader.load_file(folder + f)", globals(),locals())
    # cProfile.runctx("GerberReader2.load_file(folder + f)", globals(),locals())

print "Times:"
print times

