#!/usr/bin/env python
# -*- coding: ISO-8859-1 -*-

import sys, os.path, codecs, encodings
from zope.pagetemplate.pagetemplate import PageTemplate

class example:
    def __init__(self, name):
        self.name = name
        self.png = "examples/%s.png" % self.name
        self.eps = "examples/%s.eps" % self.name
        self.code = open("../examples/%s.py.html" % name, "r").read()
        self.code = self.code.replace("�", "&auml;")
        self.code = self.code.replace("�", "&Auml;")
        self.code = self.code.replace("�", "&ouml;")
        self.code = self.code.replace("�", "&Ouml;")
        self.code = self.code.replace("�", "&uuml;")
        self.code = self.code.replace("�", "&Uuml;")
        self.code = self.code.replace("�", "&szlig;")
        self.code = self.code.replace("�", "&eacute;")
    def __getattr__(self, attr):
        return self.__dict__[attr]

def PageTemplateFromFile(filename):
    pt = PageTemplate()
    pt.write(open(filename, "r").read())
    return pt

def write_file(filename, string):
    # path = os.path.join(os.path.expanduser(outpath), filename)
    # print "Writing %s ..." % path
    open(filename, "w").write(string)

maintemplate = PageTemplateFromFile("maintemplate.pt")

pagename = sys.argv[1]
if pagename.endswith(".pt"): pagename = pagename[:-3]

examples = [example("hello"),
            example("latex"),
            example("pattern"),
            example("circles"),
            example("vector"),
            example("box"),
            example("connect"),
            example("valign"),
            example("tree"),
            example("sierpinski"),
            example("graphs/minimal"),
            example("graphs/lissajous"),
            example("graphs/piaxis"),
            example("graphs/manyaxes"),
            example("graphs/inset"),
            example("graphs/link"),
            example("graphs/change"),
            example("graphs/bar"),
            example("graphs/arrows"),
            example("graphs/mandel"),
            example("graphs/integral"),
            example("graphs/partialfill"),
            example("graphs/washboard"),
            example("axis/simple"),
            example("axis/painter"),
            example("axis/rating"),
            example("axis/manualticks"),
            example("axis/parter"),
            example("axis/texter"),
            example("axis/log")]

write_file("%s.html" % pagename,
           PageTemplateFromFile("%s.pt" % pagename)(maintemplate=maintemplate,
                                                   pagename="%s.html" % pagename,
                                                   examples=examples))

