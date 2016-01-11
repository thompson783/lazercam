
"""
Read an Excellon drill file (minimal implementation)
Only loads the details for drilling holes and their diameters.
No enforcement is made on the file structure. E.g. you could theoretically define a
tool anywhere as long as it is defined before that tool is used.

Format specifications:
    http://web.archive.org/web/20071030075236/http://www.excellon.com/manuals/program.htm
"""


def load_file(filename):
    """
    Parse gerber file from file path
    :rtype filename: str
    :rtype: [float[], float]
    """
    file = open(filename, 'r')
    str = file.read()
    file.close()

    return parse(str)


def parse(str):
    """
    :type str: str
    :rtype: [float[], float]
    """

    str = str.split('\n')

    if not str[0].startswith("M48"):
        raise StandardError("Excellon file data is invalid. First line must br M48 command")
    str = str[1:]

    units = 0  # 0 = mm, 1 = in (same as Gerber)
    tools = []  # stores tool diameters - very basic
    drillPts = []  # list of X,Y,T where X,Y is the drill coordinate and T is tool number
    formatTZ = False  # default is to leading zero (LZ)
    absMode = True
    tooln = 0  # active tool
    x = 0
    y = 0

    for s in str:
        s = s.strip()  # remove whitespaces
        if s[0] == ';' or s[0] == '%':
            continue
        elif s[0] == 'X' or s[0] == 'Y':
            # TODO: convert to float numbers formatted without decimal indicating some scaling will be required.
            # The specifications aren't clear about how many decimal places should be used though
            # The options are 2 or 3 places and chosen value appears to change depending on machine setting
            if s[0] == 'X':
                splitpos = s.find('Y', 1)
                if splitpos == -1:
                    # omit Y indicating it hasn't change
                    if absMode:
                        x = readCoord(s[1:], formatTZ)
                    else:
                        x += readCoord(s[1:], formatTZ)
                else:
                    if absMode:
                        x = readCoord(s[1:splitpos], formatTZ)
                        y = readCoord(s[splitpos+1:], formatTZ)
                    else:
                        x += readCoord(s[1:splitpos], formatTZ)
                        y += readCoord(s[splitpos+1:], formatTZ)
            else:  # s[0] == y
                # omit x indicating it hasn't change
                if absMode:
                    y = readCoord(s[1:], formatTZ)
                else:
                    y += readCoord(s[1:], formatTZ)
            drillPts.append([x, y, tools[tooln]])  # We should really store a ref to tool info but we only need
                                    # the tool diameter here so we will be lazy here and store just that.
                                    # If we care about feedrate and/or spindle speed, then we would need to store
                                    # all of the tool information.
        elif s[0] == 'T':
            # Format:   T##C##[F##][S##]
            # Where T is tool number, C is diameter, F is feedrate and S is spindle speed
            # F and S are optional and are IGNORED by this parser
            splitpos = s.find('C')
            if splitpos == -1:
                # we assume it is a tool set if C is not supplied.
                # Proper checking would require a tool set to occur in the header section ONLY
                tooln = int(s[1:])  # leading zero is sometimes dropped off but max of 2 digits
                                    # T#### where 4 digits are specified indicate a compensation index is provided
                                    # We ignore this here but if encountered, the program would likely crash
                                    # trying to access the non-existant tool index.
            else:
                splitpos2 = s.find('F')
                splitpos3 = s.find('S')
                if splitpos2 == -1: splitpos2 = 10000
                if splitpos3 == -1: splitpos3 = 10000
                splitpos3 = min(splitpos2, splitpos3)
                if splitpos3 == 10000:
                    tooln = int(s[1:splitpos])
                else:
                    tooln = int(s[1:splitpos3])
                tooldia = readCoord(s[splitpos+1:], formatTZ)
                while len(tools) <= tooln: tools.append(0)
                tools[tooln] = tooldia
            pass
        elif s[0] == 'G':
            if s.startswith("00", 1):
                raise StandardError("Rout mode not supported")
            elif s.startswith("01", 1):
                # linear interpolation - ignored
                pass
            elif s.startswith("02", 1):
                # circular CW interpolation - ignored
                pass
            elif s.startswith("03", 1):
                # circular CCW interpolation - ignored
                pass
            elif s.startswith("05", 1):
                # drill mode - the ONLY mode supported
                pass
            elif s.startswith("90", 1):
                # absolute coordinates - the only coordinate input type supported
                absMode = True
            elif s.startswith("91", 1):
                # incremental input coordinates - NOT RECOMMENDED
                print("WARNING: using incremental input mode is not recommended due to floating point imprecision")
                absMode = False
            else:
                raise StandardError("Rout command '%s' is not supported" % s)
        elif s.startswith("M95"):
            pass  # end header - ignored
        elif s.startswith("INCH"):
            units = 1
            formatTZ = s.find("TZ", 5) != -1
        elif s.startswith("METRIC"):
            units = 0
            formatTZ = s.find("TZ", 7) != -1
        elif s.startswith("M30"):
            # End of program command.
            break
        else:
            print("Ignored unsupported command: ", s)

    # Commands intentionally ignored but not so safe - i.e. it may affect some things
    # VER, FMAT

    return [drillPts, units]

def readCoord(str, formatTZ):
    if str.find('.') != -1:
        return float(str)
    else:
        if formatTZ:
            return float(str)*0.0001  # assume 4 decimal places
        else:
            # what a horrible way to specify this. Converting to float is rather messy
            if len(str) == 1:
                return float(str)*10
            elif len(str) == 2:
                return float(str)
            else:
                return float(str[:2] + '.' + str[2:])

# TODO: in matrix units, you can apparently specify values using 3 decimal places (in microns)
# but the Excellon specifications make no mention of how you determine whether to use 2 or 3 DP?!?
