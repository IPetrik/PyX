#!/usr/bin/env python
import sys
sys.path.append("..")
from pyx import *

c = canvas.canvas()
c.fill(path.rect(0, 0, 7, 3), color.grey(0.8))
c.fill(path.rect(1, 1, 1, 1), color.rgb.red)
c.fill(path.rect(3, 1, 1, 1), color.rgb.green)
c.fill(path.rect(5, 1, 1, 1), color.rgb.blue)
c.writetofile("color")

