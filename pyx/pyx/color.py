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

import base

class color(base.PSAttr):

    """base class for all colors"""
    
    pass


class grey(color):
    
    """grey tones"""
    
    def __init__(self, level):
        assert 0<=level and level<=1, "grey value must be between 0 and 1"
        self.level=level

    def write(self, file):
        file.write("%f setgray\n" % self.level)

grey.black = grey(0.0)
grey.white = grey(1.0)
    

class rgb(color):

    """rgb colors"""
    
    def __init__(self, r=0.0, g=0.0, b=0.0):
        assert 0<=r and r<=1, "red value must be between 0 and 1"
        assert 0<=g and g<=1, "green value must be between 0 and 1"
        assert 0<=b and b<=1, "blue value must be between 0 and 1"
        self.r=r
        self.g=g
        self.b=b

    def write(self, file):
        file.write("%f %f %f setrgbcolor\n" % (self.r, self.g, self.b))

rgb.red   = rgb(1,0,0)
rgb.green = rgb(0,1,0)
yblue     = rgb(0,0,1)
       

class hsb(color):

    """hsb colors"""
    
    def __init__(self, h=0.0, s=0.0, b=0.0):
        assert 0<=h and h<=1, "hue value must be between 0 and 1"
        assert 0<=s and s<=1, "saturation value must be between 0 and 1"
        assert 0<=b and b<=1, "brightness value must be between 0 and 1"
        self.h=h
        self.s=s
        self.b=b

    def write(self, file):
        file.write("%f %f %f sethsbcolor\n" % (self.h, self.s, self.b))
        

class cmyk(color):

    """cmyk colors"""
    
    def __init__(self, c=0.0, m=0.0, y=0.0, k=0.0):
        assert 0<=c and c<=1, "cyan value must be between 0 and 1"
        assert 0<=m and m<=1, "magenta value must be between 0 and 1"
        assert 0<=y and y<=1, "yellow value must be between 0 and 1"
        assert 0<=k and k<=1, "black value must be between 0 and 1"
        self.c=c
        self.m=m
        self.y=y
        self.k=k

    def write(self, file):
        file.write("%f %f %f %f setcmykcolor\n" %
                   (self.c, self.m, self.y, self.k))
