#!/usr/bin/env python
#
#
# Copyright (C) 2002 J�rg Lehmann <joergl@users.sourceforge.net>
# Copyright (C) 2002 Andr� Wobst <wobsta@users.sourceforge.net>
#
# This file is part of PyX (http://pyx.sourceforge.net/).
#
# PyX is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# PyX is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PyX; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA


# this code will be part of PyX 0.3

import os, threading, Queue, traceback, re, struct, tempfile
import helper, attrlist, bbox, unit, box, base, trafo, canvas

###############################################################################
# joergl would mainly work here ...

###############################################################################
# this is the old stuff
_DVI_CHARMIN     =   0 # typeset a character and move right (range min)
_DVI_CHARMAX     = 127 # typeset a character and move right (range max)
_DVI_SET1234     = 128 # typeset a character and move right
_DVI_SETRULE     = 132 # typeset a rule and move right
_DVI_PUT1234     = 133 # typeset a character
_DVI_PUTRULE     = 137 # typeset a rule
_DVI_NOP         = 138 # no operation
_DVI_BOP         = 139 # beginning of page
_DVI_EOP         = 140 # ending of page
_DVI_PUSH        = 141 # save the current positions (h, v, w, x, y, z)
_DVI_POP         = 142 # restore positions (h, v, w, x, y, z)
_DVI_RIGHT1234   = 143 # move right
_DVI_W0          = 147 # move right by w
_DVI_W1234       = 148 # move right and set w
_DVI_X0          = 152 # move right by x
_DVI_X1234       = 153 # move right and set x
_DVI_DOWN1234    = 157 # move down
_DVI_Y0          = 161 # move down by y
_DVI_Y1234       = 162 # move down and set y
_DVI_Z0          = 166 # move down by z
_DVI_Z1234       = 167 # move down and set z
_DVI_FNTNUMMIN   = 171 # set current font (range min)
_DVI_FNTNUMMAX   = 234 # set current font (range max)
_DVI_FNT1234     = 235 # set current font
_DVI_SPECIAL1234 = 239 # special (dvi extention)
_DVI_FNTDEF1234  = 243 # define the meaning of a font number
_DVI_PRE         = 247 # preamble
_DVI_POST        = 248 # postamble beginning
_DVI_POSTPOST    = 249 # postamble ending

_DVI_VERSION     = 2 # dvi version

# position variable indices
_POS_H           = 0
_POS_V           = 1
_POS_W           = 2
_POS_X           = 3
_POS_Y           = 4
_POS_Z           = 5

# reader states
_READ_PRE       = 1
_READ_NOPAGE    = 2
_READ_PAGE      = 3
_READ_POST      = 4
_READ_POSTPOST  = 5
_READ_DONE      = 6

class fix_word:
    def __init__(self, word):
        if word>=0:
            self.sign = 1
        else:
            self.sign = -1

        self.precomma = abs(word) >> 20
        self.postcomma = abs(word) & 0xFFFFF

    def __float__(self):
        return self.sign * (self.precomma + 1.0*self.postcomma/0xFFFFF)

    def __mul__(self, other):
        # hey, it's Q&D
        result = fix_word(0)

        result.sign = self.sign*other.sign
        c = self.postcomma*other.precomma + self.precomma*other.postcomma
        result.precomma = self.precomma*other.precomma + (c >> 20)
        result.postcomma = c & 0xFFFFF + ((self.postcomma*other.postcomma) >> 40)
        return result


class char_info_word:
    def __init__(self, word):
        self.width_index  = (word & 0xFF000000) >> 24
        self.height_index = (word & 0x00F00000) >> 20
        self.depth_index  = (word & 0x000F0000) >> 16
        self.italic_index = (word & 0x0000FC00) >> 10
        self.tag          = (word & 0x00000300) >> 8
        self.remainder    = (word & 0x000000FF)

        if self.width_index==0:
            raise TFMError, "width_index should not be zero"

class binfile:

    def __init__(self, filename, mode="r"):
        self.file = open(filename, mode)

    def tell(self):
        return self.file.tell()

    def read(self, bytes):
        return self.file.read(bytes)

    def readint(self, bytes = 4, signed = 0):
        first = 1
        result = 0
        while bytes:
            value = ord(self.file.read(1))
            if first and signed and value > 127:
                value -= 256
            first = 0
            result = 256 * result + value
            bytes -= 1
        return result

    def readint32(self):
        return struct.unpack(">l", self.file.read(4))[0]

    def readuint32(self):
        return struct.unpack(">L", self.file.read(4))[0]

    def readint24(self):
        # XXX: checkme
        return struct.unpack(">l", "\0"+self.file.read(3))[0]

    def readuint24(self):
        # XXX: checkme
        return struct.unpack(">L", "\0"+self.file.read(3))[0]

    def readint16(self):
        return struct.unpack(">h", self.file.read(2))[0]

    def readuint16(self):
        return struct.unpack(">H", self.file.read(2))[0]

    def readchar(self):
        return struct.unpack("b", self.file.read(1))[0]

    def readuchar(self):
        return struct.unpack("B", self.file.read(1))[0]

    def readstring(self, bytes):
        l = self.readuchar()
        assert l<bytes-1, "inconsistency in file: string too long"
        return self.file.read(bytes-1)[:l]

class DVIError(Exception): pass

class TFMError(Exception): pass

class TFMFile:
    def __init__(self, name):
        self.file = binfile(name, "rb")

        #
        # read pre header
        #

        self.lf = self.file.readint16()
        self.lh = self.file.readint16()
        self.bc = self.file.readint16()
        self.ec = self.file.readint16()
        self.nw = self.file.readint16()
        self.nh = self.file.readint16()
        self.nd = self.file.readint16()
        self.ni = self.file.readint16()
        self.nl = self.file.readint16()
        self.nk = self.file.readint16()
        self.ne = self.file.readint16()
        self.np = self.file.readint16()

        if not (self.bc-1<=self.ec<=255 and
                self.ne<=256 and
                self.lf==6+self.lh+(self.ec-self.bc+1)+self.nw+self.nh+self.nd
                +self.ni+self.nl+self.nk+self.ne+self.np):
            raise TFMError, "error in TFM pre-header"

        #
        # read header
        #

        self.checksum = self.file.readint32()
        self.designsizeraw = self.file.readint32()
        assert self.designsizeraw>0, "invald design size"
        self.designsize = fix_word(self.designsizeraw)
        if self.lh>2:
            self.charcoding = self.file.readstring(40)
        else:
            self.charcoding = None

        if self.lh>12:
            self.fontfamily = self.file.readstring(20)
        else:
            self.fontfamily = None

        if self.lh>17:
            self.sevenbitsave = self.file.readuchar()
            # ignore the following two bytes
            self.file.readint16()
            facechar = self.file.readuchar()
            # decode ugly face specification into the Knuth suggested string
            if facechar<18:
                if facechar>=12:
                    self.face = "E"
                    facechar -= 12
                elif facechar>=6:
                    self.face = "C"
                    facechar -= 6
                else:
                    self.face = "R"

                if facechar>=4:
                    self.face = "L" + self.face
                    facechar -= 4
                elif facechar>=2:
                    self.face = "B" + self.face
                    facechar -= 2
                else:
                    self.face = "M" + self.face

                if facechar==1:
                    self.face = self.face[0] + "I" + self.face[1]
                else:
                    self.face = self.face[0] + "R" + self.face[1]

            else:
                self.face = None
        else:
            self.sevenbitsave = self.face = None

        if self.lh>18:
            # just ignore the rest
            self.file.read((self.lh-18)*4)

        #
        # read char_info
        #

        self.char_info = [None for charcode in range(self.ec+1)]

        for charcode in range(self.bc, self.ec+1):
            self.char_info[charcode] = char_info_word(self.file.readint32())

        #
        # read widths
        #

        self.width = [None for width_index in range(self.nw)]
        for width_index in range(self.nw):
            # self.width[width_index] = fix_word(self.file.readint32())
            self.width[width_index] = self.file.readint32()

        #
        # read heights
        #

        self.height = [None for height_index in range(self.nh)]
        for height_index in range(self.nh):
            # self.height[height_index] = fix_word(self.file.readint32())
            self.height[height_index] = self.file.readint32()

        #
        # read depths
        #

        self.depth = [None for depth_index in range(self.nd)]
        for depth_index in range(self.nd):
            # self.depth[depth_index] = fix_word(self.file.readint32())
            self.depth[depth_index] = self.file.readint32()

        #
        # read italic
        #

        self.italic = [None for italic_index in range(self.ni)]
        for italic_index in range(self.ni):
            # self.italic[italic_index] = fix_word(self.file.readint32())
            self.italic[italic_index] = self.file.readint32()

        #
        # read lig_kern
        #

        # XXX decode to lig_kern_command

        self.lig_kern = [None for lig_kern_index in range(self.nl)]
        for lig_kern_index in range(self.nl):
            self.lig_kern[lig_kern_index] = self.file.readint32()

        #
        # read kern
        #

        self.kern = [None for kern_index in range(self.nk)]
        for kern_index in range(self.nk):
            # self.kern[kern_index] = fix_word(self.file.readint32())
            self.kern[kern_index] = self.file.readint32()

        #
        # read exten
        #

        # XXX decode to extensible_recipe

        self.exten = [None for exten_index in range(self.ne)]
        for exten_index in range(self.ne):
            self.exten[exten_index] = self.file.readint32()

        #
        # read param
        #

        # XXX decode

        self.param = [None for param_index in range(self.np)]
        for param_index in range(self.np):
            self.param[param_index] = self.file.readint32()


class Font:
    def __init__(self, name, c, q, d, tfmconv):
        self.name = name
        path = os.popen("kpsewhich %s.tfm" % self.name, "r").readline()[:-1]
        self.tfmfile = TFMFile(path)

        if self.tfmfile.checksum!=c:
            raise DVIError("check sums do not agree: %d vs. %d" %
                           (self.checksum, c))

        self.tfmdesignsize = round(tfmconv*self.tfmfile.designsizeraw)

        if abs(self.tfmdesignsize - d)>2:
            raise DVIError("design sizes do not agree: %d vs. %d" %
                           (self.tfmdesignsize, d))


        if q<0 or q>134217728:
            raise DVIError("font '%s' not loaded: bad scale" % fontname)

        if d<0 or d>134217728:
            raise DVIError("font '%s' not loaded: bad design size" % fontname)

        self.scale = 1.0*q/d
        self.alpha = 16;
        self.q = self.qorig = q
        while self.q>=8388608:
            self.q = self.q/2
            self.alpha *= 2

        self.beta = 256/self.alpha;
        self.alpha = self.alpha*self.q;

    def __str__(self):
        return "Font(%s, %d)" % (self.name, self.tfmdesignsize)

    __repr__ = __str__

    def convert(self, width):
        b0 = width >> 24
        b1 = (width >> 16) & 0xff
        b2 = (width >> 8 ) & 0xff
        b3 = (width      ) & 0xff
#        print width*self.qorig*16/ 16777216, (((((b3*self.q)/256)+(b2*self.q))/256)+(b1*self.q))/self.beta

        if b0==0:
            return (((((b3*self.q)/256)+(b2*self.q))/256)+(b1*self.q))/self.beta
        elif b0==255:
            return (((((b3*self.q)/256)+(b2*self.q))/256)+(b1*self.q))/self.beta-self.alpha
        else:
            raise TFMError("error in font size")

    def __getattr__(self, attr):
        return self.tfmfile.__dict__[attr]

    def getwidth(self, charcode):
        return self.convert(self.tfmfile.width[self.char_info[charcode].width_index])

    def getheight(self, charcode):
        return self.convert(self.tfmfile.height[self.char_info[charcode].height_index])

    def getdepth(self, charcode):
        return self.convert(self.tfmfile.depth[self.char_info[charcode].depth_index])

    def getitalic(self, charcode):
        return self.convert(self.tfmfile.italic[self.char_info[charcode].italic_index])


class DVIFile:

    def flushout(self):
        if self.actoutstart:
            if self.debug:
                print "[%s]" % self.actoutstring
            self.actpage.append(("c",
                                 self.actoutstart[0], self.actoutstart[1],
                                 self.actoutstring))
            self.actoutstart = None

    def putchar(self, char, inch=1):
        x = self.pos[_POS_H] * self.conv / 100000
        y = -self.pos[_POS_V] * self.conv / 100000
        dx = inch and self.fonts[self.activefont].getwidth(char) or 0

        if self.debug:
            print ("%d: %schar%d h:=%d+%d=%d, hh:=%d" %
                   (self.filepos,
                    inch and "set" or "put",
                    char,
                    self.pos[_POS_H], dx, self.pos[_POS_H]+dx,
                    0))

        self.pos[_POS_H] += dx

        ascii = (char > 32 and char < 128) and "%s" % chr(char) or "\\%03o" % char

        if self.actoutstart is None:
            self.actoutstart = unit.t_cm(x), unit.t_cm(y)
            self.actoutstring = ""
        self.actoutstring = self.actoutstring + ascii

        if not inch:
            # XXX: correct !?
            self.flushout()

    def putrule(self, height, width, inch=1):
        self.flushout()
        if height > 0 and width > 0:
            x1 = self.pos[_POS_H] * self.conv * 1e-5
            y1 = -self.pos[_POS_V] * self.conv * 1e-5
            w = width * self.conv * 1e-5
            h = height * self.conv * 1e-5
            if self.debug:
                print "%d: putrule height %d, width %d" % (self.filepos, height, width)
            self.actpage.append(("r",
                                 unit.t_cm(x1), unit.t_cm(y1),
                                 unit.t_cm(w), unit.t_cm(h)))
        if inch:
            pass # TODO: increment h

    def usefont(self, fontnum):
        self.flushout()
        self.activefont = fontnum
        self.actpage.append(("f", self.fonts[fontnum]))
        if self.debug:
            print ("%d: fntnum%i current font is %s" %
                   (self.filepos,
                    self.activefont, self.fonts[fontnum].name))

    def definefont(self, num, c, q, d, fontname):
        # c: checksum
        # q: scaling factor
        #    Note that q is actually s in large parts of the documentation.
        # d: design size

        self.fonts[num] =  Font(fontname, c, q, d, self.tfmconv)

        scale = round((1000.0*self.conv*q)/(self.trueconv*d))
        m = 1.0*q/d

        if self.debug:
            print "%d: fntdefx %i: %s" % (self.filepos, num, fontname)

#            scalestring = scale!=1000 and " scaled %d" % scale or ""
#            print ("Font %i: %s%s---loaded at size %d DVI units" %
#                   (num, fontname, scalestring, q))
#            if scale!=1000:
#                print " (this font is magnified %d%%)" % round(scale/10)

    def __init__(self, filename, debug=0):

        self.filename = filename
        self.debug = debug
        file = binfile(self.filename, "rb")
        state = _READ_PRE
        stack = []

        # XXX max number of fonts
        self.fonts = [None for i in range(64)]
        self.activefont = None

        # here goes the result, for each page one list.
        self.pages = []

        # pointer to currently active page
        self.actpage = None

        # currently active output: position and content
        self.actoutstart = None
        self.actoutstring = ""

        while state != _READ_DONE:
            self.filepos = file.tell()
            cmd = file.readuchar()
            if cmd == _DVI_NOP: pass

            elif state == _READ_PRE:
                if cmd == _DVI_PRE:
                    if file.readuchar() != _DVI_VERSION: raise DVIError
                    num = file.readuint32()
                    den = file.readuint32()
                    mag = file.readuint32()

                    # self.trueconv = conv in DVIType docu
                    # if resolution = 254000.0

                    self.tfmconv = (25400000.0/num)*(den/473628672)/16.0;
                    self.trueconv = 1.0*num/den
                    self.conv = self.trueconv*(mag/1000.0)

                    comment = file.read(file.readuchar())
                    state = _READ_NOPAGE
                else: raise DVIError
            elif state == _READ_NOPAGE:
                if cmd == _DVI_BOP:
                    self.flushout()
                    if self.debug:
                        print "%d: beginning of page" % self.filepos,
                        print file.readuint32()
                        for i in range(9): file.readuint32(),
                    else:
                        for i in range(10): file.readuint32(),
                    file.readuint32()

                    self.pos = [0, 0, 0, 0, 0, 0]
                    self.pages.append([])
                    self.actpage = self.pages[-1]
                    state = _READ_PAGE
                elif cmd == _DVI_POST:
                    state = _READ_DONE # we skip the rest
                else: raise DVIError
            elif state == _READ_PAGE:
               if cmd >= _DVI_CHARMIN and cmd <= _DVI_CHARMAX:
                   self.putchar(cmd)
               elif cmd >= _DVI_SET1234 and cmd < _DVI_SET1234 + 4:
                   self.putchar(file.readint(cmd - _DVI_SET1234 + 1))
               elif cmd == _DVI_SETRULE:
                   self.putrule(file.readint32(), file.readint32())
               elif cmd >= _DVI_PUT1234 and cmd < _DVI_PUT1234 + 4:
                   self.putchar(file.readint(cmd - _DVI_PUT1234 + 1), inch=0)
               elif cmd == _DVI_PUTRULE:
                   self.putrule(file.readint32(), file.readint32(), 0)
               elif cmd == _DVI_EOP:
                   self.flushout()
                   state = _READ_NOPAGE
                   if self.debug:
                       print "%d: eop" % self.filepos
                       print
               elif cmd == _DVI_PUSH:
                   stack.append(tuple(self.pos))
                   if self.debug:
                       print "%d: push" % self.filepos
                       print ("level %d:(h=%d,v=%d,w=%d,x=%d,y=%d,z=%d,hh=,vv=)" %
                              (( len(stack)-1,)+tuple(self.pos)))
               elif cmd == _DVI_POP:
                   self.flushout()
                   self.pos = list(stack[-1])
                   del stack[-1]
                   if self.debug:
                       print "%d: pop" % self.filepos
                       print ("level %d:(h=%d,v=%d,w=%d,x=%d,y=%d,z=%d,hh=,vv=)" %
                              (( len(stack),)+tuple(self.pos)))

               elif cmd >= _DVI_RIGHT1234 and cmd < _DVI_RIGHT1234 + 4:
                   self.flushout()
                   dh = file.readint(cmd - _DVI_RIGHT1234 + 1, 1)
                   if self.debug:
                       print ("%d: right%d %d h:=%d%+d=%d, hh:=" %
                              (self.filepos,
                               cmd - _DVI_RIGHT1234 + 1,
                               dh,
                               self.pos[_POS_H],
                               dh,
                               self.pos[_POS_H]+dh))
                   self.pos[_POS_H] += dh
               elif cmd == _DVI_W0:
                   self.flushout()
                   if self.debug:
                       print ("%d: w0 %d h:=%d%+d=%d, hh:=" %
                              (self.filepos,
                               self.pos[_POS_W],
                               self.pos[_POS_H],
                               self.pos[_POS_W],
                               self.pos[_POS_H]+self.pos[_POS_W]))
                   self.pos[_POS_H] += self.pos[_POS_W]
               elif cmd >= _DVI_W1234 and cmd < _DVI_W1234 + 4:
                   self.flushout()
                   self.pos[_POS_W] = file.readint(cmd - _DVI_W1234 + 1, 1)
                   if self.debug:
                       print ("%d: w%d %d h:=%d%+d=%d, hh:=" %
                              (self.filepos,
                               cmd - _DVI_W1234 + 1,
                               self.pos[_POS_W],
                               self.pos[_POS_H],
                               self.pos[_POS_W],
                               self.pos[_POS_H]+self.pos[_POS_W]))
                   self.pos[_POS_H] += self.pos[_POS_W]
               elif cmd == _DVI_X0:
                   self.flushout()
                   self.pos[_POS_H] += self.pos[_POS_X]
               elif cmd >= _DVI_X1234 and cmd < _DVI_X1234 + 4:
                   self.flushout()
                   self.pos[_POS_X] = file.readint(cmd - _DVI_X1234 + 1, 1)
                   self.pos[_POS_H] += self.pos[_POS_X]
               elif cmd >= _DVI_DOWN1234 and cmd < _DVI_DOWN1234 + 4:
                   self.flushout()
                   dv = file.readint(cmd - _DVI_DOWN1234 + 1, 1)
                   if self.debug:
                       print ("%d: down%d %d v:=%d%+d=%d, vv:=" %
                              (self.filepos,
                               cmd - _DVI_DOWN1234 + 1,
                               dv,
                               self.pos[_POS_V],
                               dv,
                               self.pos[_POS_V]+dv))
                   self.pos[_POS_V] += dv
               elif cmd == _DVI_Y0:
                   self.flushout()
                   self.pos[_POS_V] += self.pos[_POS_Y]
               elif cmd >= _DVI_Y1234 and cmd < _DVI_Y1234 + 4:
                   self.flushout()
                   self.pos[_POS_Y] = file.readint(cmd - _DVI_Y1234 + 1, 1)
                   self.pos[_POS_V] += self.pos[_POS_Y]
               elif cmd == _DVI_Z0:
                   self.flushout()
                   self.pos[_POS_V] += self.pos[_POS_Z]
               elif cmd >= _DVI_Z1234 and cmd < _DVI_Z1234 + 4:
                   self.flushout()
                   self.pos[_POS_Z] = file.readint(cmd - _DVI_Z1234 + 1, 1)
                   self.pos[_POS_V] += self.pos[_POS_Z]
               elif cmd >= _DVI_FNTNUMMIN and cmd <= _DVI_FNTNUMMAX:
                   self.usefont(cmd - _DVI_FNTNUMMIN)
               elif cmd >= _DVI_FNT1234 and cmd < _DVI_FNT1234 + 4:
                   self.usefont(file.readint(cmd - _DVI_FNT1234 + 1, 1))
               elif cmd >= _DVI_SPECIAL1234 and cmd < _DVI_SPECIAL1234 + 4:
                   print "special %s" % file.read(file.readint(cmd - _DVI_SPECIAL1234 + 1))
                   raise RuntimeError("specials are not yet handled, abort")
               elif cmd >= _DVI_FNTDEF1234 and cmd < _DVI_FNTDEF1234 + 4:
                   if cmd==_DVI_FNTDEF1234:
                       num=file.readuchar()
                   elif cmd==_DVI_FNTDEF1234+1:
                       num=file.readuint16()
                   elif cmd==_DVI_FNTDEF1234+2:
                       num=file.readuint24()
                   elif cmd==_DVI_FNTDEF1234+3:
                       # Cool, here we have according to docu a signed int. Why?
                       num=file.readint32()

                   self.definefont(num,
                                   file.readint32(),
                                   file.readint32(),
                                   file.readint32(),
                                   file.read(file.readuchar()+file.readuchar()))
               else: raise DVIError

            else: raise DVIError # unexpected reader state
        self.flushout()

    def writeheader(self, file):
        """write PostScript font header"""
        for font in self.fonts:
            if font:
                file.write("%%%%BeginFont: %s\n" % font.name.upper())

                tmpfilename = tempfile.mktemp(suffix=".pfa")
                pfbfilename = os.popen("kpsewhich %s.pfb" % font.name).readlines()[-1][:-1]
                os.system("pfb2pfa %s %s" % (pfbfilename, tmpfilename))

                pfa = open(tmpfilename, "r")
                file.write(pfa.read())
                pfa.close()
                os.unlink(tmpfilename)

                file.write("%%EndFont\n")

    FontSizePattern= re.compile(r"([0-9]+)$")

    def write(self, file, page):
        """write PostScript code for page into file"""
        if self.debug:
            print "dvifile(\"%s\").write() for page %s called" % (self.filename, page)
        for el in self.pages[page-1]:
            command, arg = el[0], el[1:]
            if command=="c":
                x, y, c = arg
                file.write("%f %f moveto (%s) show\n" % (unit.topt(x), unit.topt(y), c))
            if command=="r":
                x1, y1, w, h = arg
                file.write("%f %f moveto %f 0 rlineto 0 %f rlineto %f 0 rlineto closepath fill\n" %
                           (unit.topt(x1), unit.topt(y1),
                            unit.topt(w),
                            unit.topt(h),
                            -unit.topt(w)))
            elif command=="f":
                fontname = arg[0].name
                fontscale = arg[0].scale
                match = self.FontSizePattern.search(fontname)
                if match:
                    file.write("/%s %f selectfont\n" % (fontname.upper(),
                                                        int(match.group(1))*fontscale))
                else:
                    raise RuntimeError("cannot determine font size from name '%s'" % fontname)


#if __name__=="__main__":
#    cmr10 = Font("cmr10")
#    print cmr10.charcoding
#    print cmr10.fontfamily
#    print cmr10.face
#    for charcode in range(cmr10.bc, cmr10.ec+1):
#       print "%d\th=%f\tw=%f\td=%f\ti=%f" % (
#            charcode,
#            cmr10.getwidth(charcode),
#            cmr10.getheight(charcode),
#            cmr10.getdepth(charcode),
#            cmr10.getitalic(charcode))

#    dvifile = DVIFile("test.dvi")
#    print [font for font in dvifile.fonts if font]

# end of old stuff
###############################################################################

###############################################################################
# wobsta would mainly work here ...

class TexResultError(Exception):

    def __init__(self, description, texrunner):
        self.description = description
        self.texrunner = texrunner

    def __str__(self):
        return ("%s\n" % self.description +
                "The expression passed to TeX was:\n" +
                "  %s\n" % self.texrunner.expr.replace("\n", "\n  ").rstrip() +
                "The return message from TeX was:\n" +
                "  %s\n" % self.texrunner.texmsg.replace("\n", "\n  ").rstrip() +
                "After parsing this message, the following was left:\n" +
                "  %s" % self.texrunner.texmsgparsed.replace("\n", "\n  ").rstrip())


class TexResultWarning(TexResultError): pass


###############################################################################
# checkmsg
############################################################################{{{


class checkmsg: pass


class _checkmsgstart(checkmsg):

    startpattern = re.compile(r"This is [0-9a-zA-Z\s_]*TeX")

    def check(self, texrunner):
        m = self.startpattern.search(texrunner.texmsgparsed)
        if not m:
            raise TexResultError("TeX startup failed", texrunner)
        texrunner.texmsgparsed = texrunner.texmsgparsed[m.end():]
        try:
            texrunner.texmsgparsed = texrunner.texmsgparsed.split("%s.tex" % texrunner.texfilename, 1)[1]
        except IndexError:
            raise TexResultError("TeX running startup file failed", texrunner)
        try:
            texrunner.texmsgparsed = texrunner.texmsgparsed.split("*! Undefined control sequence.\n<*> \\raiseerror\n               %\n? OK, entering \\scrollmode...\n\n", 1)[1]
        except IndexError:
            raise TexResultError("TeX switch to scrollmode failed", texrunner)


class _checkmsgnoaux(checkmsg):

    def check(self, texrunner):
        try:
            texrunner.texmsgparsed = texrunner.texmsgparsed.split("No file %s.aux." % texrunner.texfilename, 1)[1]
        except IndexError:
            pass


class _checkmsginputmarker(checkmsg):

    def check(self, texrunner):
        try:
            s1, s2 = texrunner.texmsgparsed.split("PyXInputMarker(%s)" % texrunner.executeid, 1)
            texrunner.texmsgparsed = s1 + s2
        except IndexError:
            raise TexResultError("PyXInputMarker expected", texrunner)


class _checkmsgpyxbox(checkmsg):

    pattern = re.compile(r"PyXBox\(page=(?P<page>\d+),wd=-?\d*((\d\.?)|(\.?\d))\d*pt,ht=-?\d*((\d\.?)|(\.?\d))\d*pt,dp=-?\d*((\d\.?)|(\.?\d))\d*pt\)")

    def check(self, texrunner):
        m = self.pattern.search(texrunner.texmsgparsed)
        if m and m.group("page") == str(texrunner.page):
            texrunner.texmsgparsed = texrunner.texmsgparsed[:m.start()] + texrunner.texmsgparsed[m.end():]
        else:
            raise TexResultError("PyXBox expected", texrunner)


class _checkmsgpyxpageout(checkmsg):

    def check(self, texrunner):
        try:
            s1, s2 = texrunner.texmsgparsed.split("[80.121.88.%s]" % texrunner.page, 1)
            texrunner.texmsgparsed = s1 + s2
        except IndexError:
            raise TexResultError("PyXPageOutMarker expected", texrunner)


class _checkmsgtexend(checkmsg):

    auxpattern = re.compile(r"\([^()]*\.aux\)")
    dvipattern = re.compile(r"Output written on (?P<texfilename>[a-z]+).dvi \((?P<page>\d+) pages?, \d+ bytes\)\.")

    def check(self, texrunner):
        m = self.auxpattern.search(texrunner.texmsgparsed)
        if m:
            texrunner.texmsgparsed = texrunner.texmsgparsed[:m.start()] + texrunner.texmsgparsed[m.end():]
        try:
            s1, s2 = texrunner.texmsgparsed.split("(see the transcript file for additional information)", 1)
            texrunner.texmsgparsed = s1 + s2
        except IndexError:
            pass
        m = self.dvipattern.search(texrunner.texmsgparsed)
        if texrunner.page:
            if not m:
                raise TexResultError("TeX dvifile messages expected", texrunner)
            if m.group("page") != str(texrunner.page):
                raise TexResultError("wrong number of pages reported", texrunner)
            if m.group("texfilename") != texrunner.texfilename:
                raise TexResultError("wrong filename of the dvifile reported", texrunner)
            texrunner.texmsgparsed = texrunner.texmsgparsed[:m.start()] + texrunner.texmsgparsed[m.end():]
        else:
            try:
                s1, s2 = texrunner.texmsgparsed.split("No pages of output.", 1)
                texrunner.texmsgparsed = s1 + s2
            except IndexError:
                raise TexResultError("no dvifile expected")
        try:
            s1, s2 = texrunner.texmsgparsed.split("Transcript written on %s.log." % texrunner.texfilename, 1)
            texrunner.texmsgparsed = s1 + s2
        except IndexError:
            raise TexResultError("TeX logfile message expected")


class _checkmsgemptylines(checkmsg):

    pattern = re.compile(r"^\*?\n", re.M)

    def check(self, texrunner):
        m = self.pattern.search(texrunner.texmsgparsed)
        while m:
            texrunner.texmsgparsed = texrunner.texmsgparsed[:m.start()] + texrunner.texmsgparsed[m.end():]
            m = self.pattern.search(texrunner.texmsgparsed)


class _checkmsgload(checkmsg):

    pattern = re.compile(r"\((?P<filename>[^()\s\n]+)[^()]*\)")

    def baselevels(self, s, maxlevel=1, brackets="()"):
        level = 0
        highestlevel = 0
        res = ""
        for c in s:
            if c == brackets[0]:
                level += 1
                if level > highestlevel:
                    highestlevel = level
            if level <= maxlevel:
                res += c
            if c == brackets[1]:
                level -= 1
        if not level and highestlevel > 0:
            return res

    def check(self, texrunner):
        lowestbracketlevel = self.baselevels(texrunner.texmsgparsed)
        if lowestbracketlevel is not None:
            m = self.pattern.search(lowestbracketlevel)
            while m:
                if os.access(m.group("filename"), os.R_OK):
                    lowestbracketlevel = lowestbracketlevel[:m.start()] + lowestbracketlevel[m.end():]
                else:
                    break
                m = self.pattern.match(lowestbracketlevel)
            else:
                texrunner.texmsgparsed = lowestbracketlevel


class _checkmsggraphicsload(_checkmsgload):

    def baselevels(self, s, brackets="<>", **args):
        _checkmsgload.baselevels(self, s, brackets=brackets, **args)



class _checkmsgignore(_checkmsgload):

    def check(self, texrunner):
        texrunner.texmsgparsed = ""


checkmsg.start = _checkmsgstart()
checkmsg.noaux = _checkmsgnoaux()
checkmsg.inputmarker = _checkmsginputmarker()
checkmsg.pyxbox = _checkmsgpyxbox()
checkmsg.pyxpageout = _checkmsgpyxpageout()
checkmsg.texend = _checkmsgtexend()
checkmsg.emptylines = _checkmsgemptylines()
checkmsg.load = _checkmsgload()
checkmsg.graphicsload = _checkmsggraphicsload()
checkmsg.ignore = _checkmsgignore()

# }}}


###############################################################################
# texsettings
############################################################################{{{


class halign: # horizontal alignment

    def __init__(self, hratio):
        self.hratio = hratio


halign.left = halign(0)
halign.right = halign(1)
halign.center = halign(0.5)


class _texsetting: # generic tex settings (modifications of the tex expression)

    def modifyexpr(self, expr):
        return expr


class valign(_texsetting):

    def __init__(self, width):
        self.width_str = width

    def modifyexpr(self, expr):
        return r"\%s{\hsize%.5fpt{%s}}" % (self.vkind, unit.topt(self.width_str)*72.27/72.0, expr)


class _valigntopline(valign):

    vkind = "vtop"


class _valignbottomline(valign):

    vkind = "vbox"


class _valigncenterline(valign):

    def __init__(self, heightstr="0", lowerratio=0.5):
        self.heightstr = heightstr
        self.lowerratio = lowerratio

    def modifyexpr(self, expr):
        return r"\setbox0\hbox{%s}\lower%.5f\ht0\hbox{%s}" % (self.heightstr, self.lowerratio, expr)


valign.topline = _valigntopline
valign.bottomline = _valignbottomline
valign.centerline = _valigncenterline


class _mathmode(_texsetting):

    def modifyexpr(self, expr):
        return r"\hbox{$\displaystyle{%s}$}" % expr

mathmode = _mathmode()


defaultsizelist = ["normalsize", "large", "Large", "LARGE", "huge", "Huge", None, "tiny", "scriptsize", "footnotesize", "small"]

class size(_texsetting):

    def __init__(self, expr, sizelist=defaultsizelist):
        if helper.isinteger(expr):
            if expr >= 0 and expr < sizelist.index(None):
                self.size = sizelist[expr]
            elif expr < 0 and expr + len(sizelist) > sizelist.index(None):
                self.size = sizelist[expr]
            else:
                raise IndexError("index out of sizelist range")
        else:
            self.size = expr

    def modifyexpr(self, expr):
        return r"\%s{%s}" % (self.size, expr)

for s in defaultsizelist:
    if s is not None:
        size.__dict__[s] = size(s)

# }}}


class _readpipe(threading.Thread):

    def __init__(self, pipe, expectqueue, gotevent, gotqueue):
        threading.Thread.__init__(self)
        self.setDaemon(1)
        self.pipe = pipe
        self.expectqueue = expectqueue
        self.gotevent = gotevent
        self.gotqueue = gotqueue
        self.start()

    def run(self):
        read = self.pipe.readline()
        while len(read):
            read.replace("\r", "")
            if not len(read) or read[-1] != "\n":
                read += "\n"
            self.gotqueue.put(read)
            try:
                self.expect = self.expectqueue.get_nowait()
            except Queue.Empty:
                pass
            if read.find(self.expect) != -1:
                self.gotevent.set()
            read = self.pipe.readline()
        if self.expect.find("PyXInputMarker") != -1:
            raise RuntimeError("TeX finished unexpectedly")



class _textbox(box._rect, base.PSText):

    def __init__(self, x, y, left, right, height, depth, texrunner, page):
        self.trafo = trafo._translate(-left, 0)
        box._rect.__init__(self, -left, -depth, left + right, depth + height, abscenter = (left, depth), trafo=trafo._translate(x, y))
        self.texrunner = texrunner
        self.page = page

    def transform(self, trafo):
        box._rect.transform(self, trafo)
        self.trafo = trafo * self.trafo

    def writefontheader(self, file, containsfonts):
        self.texrunner.writefontheader(file, containsfonts)

    def write(self, file):
        canvas._gsave().write(file) # XXX: canvas?, constructor call needed?
        self.trafo.write(file)
        self.texrunner.write(file, self.page)
        canvas._grestore().write(file)



class textbox(_textbox):

    def __init__(self, x, y, left, right, height, depth, texrunner, page):
        _textbox.__init__(unit.topt(x), unit.topt(y), unit.topt(left), unit.topt(right),
                          unit.topt(height), unit.topt(depth), texrunner, page)



class TexRunsError(Exception): pass
class TexDoneError(Exception): pass
class TexNotInDefineModeError(Exception): pass


class texrunner(attrlist.attrlist):

    def __init__(self, mode="tex",
                       docclass="article",
                       docopt=None,
                       usefiles=[],
                       waitfortex=5,
                       texdebug=0,
                       dvidebug=0,
                       checkmsgstart=checkmsg.start,
                       checkmsgdocclass=checkmsg.load,
                       checkmsgbegindoc=(checkmsg.load, checkmsg.noaux),
                       checkmsgend=checkmsg.texend,
                       checkmsgdefaultdefine=(),
                       checkmsgdefaultrun=()):
        self.mode = mode
        self.docclass = docclass
        self.docopt = docopt
        self.usefiles = usefiles
        self.waitfortex = waitfortex
        self.texdebug = texdebug
        self.dvidebug = dvidebug
        self.checkmsgstart = helper.ensuresequence(checkmsgstart)
        self.checkmsgdocclass = helper.ensuresequence(checkmsgdocclass)
        self.checkmsgbegindoc = helper.ensuresequence(checkmsgbegindoc)
        self.checkmsgend = helper.ensuresequence(checkmsgend)
        self.checkmsgdefaultdefine = helper.ensuresequence(checkmsgdefaultdefine)
        self.checkmsgdefaultrun = helper.ensuresequence(checkmsgdefaultrun)

        self.texruns = 0
        self.texdone = 0
        self.definemode = 1
        self.executeid = 0
        self.page = 0
        self.texfilename = "text"

    def execute(self, expr, *checks):
        if not self.texruns:
            texfile = open("%s.tex" % self.texfilename, "w") # start with filename -> creates dvi file with that name
            texfile.write("\\relax\n")
            texfile.close()
            self.texinput, self.texoutput = os.popen4("%s %s" % (self.mode, self.texfilename), "t", 0)
            self.expectqueue = Queue.Queue(1) # allow for a single entry only
            self.gotevent = threading.Event()
            self.gotqueue = Queue.Queue(0) # allow arbitrary number of entries
            self.readoutput = _readpipe(self.texoutput, self.expectqueue, self.gotevent, self.gotqueue)
            self.texruns = 1
            olddefinemode = self.definemode
            self.definemode = 1
            # self.execute("\\raiseerror") # timeout test
            self.execute("\\raiseerror%\ns\n" + # switch to nonstop-mode
                         "\\def\\PyX{P\\kern-.3em\\lower.5ex\hbox{Y}\kern-.18em X}%\n" +
                         "\\newbox\\PyXBox%\n" +
                         "\\def\\ProcessPyXBox#1#2{%\n" +
                         "\\setbox\\PyXBox=\\hbox{{#1}}%\n" +
                         "\\immediate\\write16{PyXBox(page=#2," +
                                                     "wd=\\the\\wd\\PyXBox," +
                                                     "ht=\\the\\ht\\PyXBox," +
                                                     "dp=\\the\\dp\\PyXBox)}%\n" +
                         "\\ht\\PyXBox0pt%\n" +
                         "{\\count0=80\\count1=121\\count2=88\\count3=#2\\shipout\\copy\\PyXBox}}%\n" +
                         "\\def\\PyXInput#1{\\immediate\\write16{PyXInputMarker(#1)}}",
                         *self.checkmsgstart)
            os.remove("%s.tex" % self.texfilename)
            if self.mode == "latex":
                if self.docopt is not None:
                    self.execute("\\documentclass[%s]{%s}" % (self.docopt, self.docclass), *self.checkmsgdocclass)
                else:
                    self.execute("\\documentclass{%s}" % self.docclass, *self.checkmsgdocclass)
            self.definemode = olddefinemode
        self.executeid += 1
        if expr is not None:
            self.expectqueue.put_nowait("PyXInputMarker(%i)" % self.executeid)
            if self.definemode:
                self.expr = ("%s%%\n" % expr +
                                   "\\PyXInput{%i}%%\n" % self.executeid)
            else:
                self.page += 1
                self.expr = ("\\ProcessPyXBox{%s}{%i}%%\n" % (expr, self.page) +
                                   "\\PyXInput{%i}%%\n" % self.executeid)
        else:
            self.expectqueue.put_nowait("Transcript written on %s.log" % self.texfilename)
            if self.mode == "latex":
                self.expr = "\\end{document}\n"
            else:
                self.expr = "\\end\n"
        if self.texdebug:
            print "pass the following expression to (La)TeX:\n  %s" % self.expr.replace("\n", "\n  ").rstrip()
        self.texinput.write(self.expr)
        self.gotevent.wait(self.waitfortex)
        nogotevent = not self.gotevent.isSet()
        self.gotevent.clear()
        try:
            self.texmsg = ""
            while 1:
                self.texmsg += self.gotqueue.get_nowait()
        except Queue.Empty:
            pass
        self.texmsgparsed = self.texmsg
        if nogotevent:
            raise TexResultError("TeX didn't respond as expected within the timeout period (%i seconds)." % self.waitfortex, self)
        else:
            if expr is not None:
                checkmsg.inputmarker.check(self)
                if not self.definemode:
                    checkmsg.pyxbox.check(self)
                    checkmsg.pyxpageout.check(self)
            for check in checks:
                try:
                    check.check(self)
                except TexResultWarning:
                    traceback.print_exc()
            checkmsg.emptylines.check(self)
            if len(self.texmsgparsed):
                raise TexResultError("unhandled TeX response (might be an error)", self)
        if expr is None:
            self.texruns = 0
            self.texdone = 1

    def writefontheader(self, file, containsfonts):
        if not self.texdone:
            _default.execute(None, *self.checkmsgend)
            self.dvifile = DVIFile("%s.dvi" % self.texfilename, debug=self.dvidebug)
        if self not in containsfonts:
            self.dvifile.writeheader(file)
            containsfonts.append(self)
            # TODO: - containfonts should contain font/glyph information instead of texrunner references

    def write(self, file, page):
        if not self.texdone:
            _default.execute(None, *self.checkmsgend)
            self.dvifile = DVIFile("%s.dvi" % self.texfilename)
        return self.dvifile.write(file, page)

    def settex(self, mode=None, waitfortex=None):
        if self.texruns:
            raise TexRunsError
        if mode is not None:
            mode = mode.lower()
            if mode != "tex" and mode != "latex":
                raise ValueError("mode \"TeX\" or \"LaTeX\" expected")
            self.mode = mode
        if waitfortex is not None:
            self.waitfortex = waitfortex

    def set(self, texdebug=None, dvidebug=None, **args):
        if self.texdone:
            raise TexDoneError
        if texdebug is not None:
            self.texdebug = texdebug
        if dvidebug is not None:
            self.dvidebug = dvidebug
        if len(args.keys()):
            self.settex(**args)

    def bracketcheck(self, expr):
        depth = 0
        esc = 0
        for c in expr:
            if c == "{" and not esc:
                depth = depth + 1
            if c == "}" and not esc:
                depth = depth - 1
                if depth < 0:
                    raise ValueError("unmatched '}'")
            if c == "\\":
                esc = (esc + 1) % 2
            else:
                esc = 0
        if depth > 0:
            raise ValueError("unmatched '{'")

    def define(self, expr, *args):
        if self.texdone:
            raise TexDoneError
        if not self.definemode:
            raise TexNotInDefineModeError
        self.bracketcheck(expr)
        self.execute(expr, *self.attrgetall(args, checkmsg, default=self.checkmsgdefaultdefine))

    PyXBoxPattern = re.compile(r"PyXBox\(page=(?P<page>\d+),wd=(?P<wd>-?\d*((\d\.?)|(\.?\d))\d*)pt,ht=(?P<ht>-?\d*((\d\.?)|(\.?\d))\d*)pt,dp=(?P<dp>-?\d*((\d\.?)|(\.?\d))\d*)pt\)")

    def text(self, x, y, expr, *args):
        if expr is None:
            raise ValueError("None is invalid")
        if self.texdone:
            raise TexDoneError
        if self.definemode:
            if self.mode == "latex":
                self.execute("\\begin{document}", *self.checkmsgbegindoc)
            self.definemode = 0
        self.attrcheck(args, allowmulti=(halign, _texsetting, checkmsg, trafo._trafo))
        for texsetting in self.attrgetall(args, _texsetting, default=()):
            expr = texsetting.modifyexpr(expr)
        self.bracketcheck(expr)
        self.execute(expr, *self.attrgetall(args, checkmsg, default=self.checkmsgdefaultrun))
        match = self.PyXBoxPattern.search(self.texmsg)
        if not match or int(match.group("page")) != self.page:
            raise TexResultError("box extents not found", self)
        width, height, depth = map(lambda x: float(x) * 72.0 / 72.27, match.group("wd", "ht", "dp"))
        hratio = self.attrgetall(args, halign, default=(halign.left,))[0].hratio
        textbox = _textbox(unit.topt(x), unit.topt(y), hratio * width, (1 - hratio) * width, height, depth, self, self.page)
        for t in self.attrgetall(args, trafo._trafo, default=()):
            textbox.transform(t)
        return textbox


_default = texrunner()
set = _default.set
define = _default.define
text = _default.text

# vim: fdm=marker
