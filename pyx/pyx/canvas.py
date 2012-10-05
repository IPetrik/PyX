# -*- encoding: utf-8 -*-
#
#
# Copyright (C) 2002-2011 Jörg Lehmann <joergl@users.sourceforge.net>
# Copyright (C) 2002-2011 André Wobst <wobsta@users.sourceforge.net>
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA

"""The canvas module provides a PostScript canvas class and related classes

A canvas holds a collection of all elements and corresponding attributes to be
displayed. """

import os, tempfile
import attr, canvasitem, deco, deformer, document, font, pycompat, style, trafo
import bbox as bboxmodule


#
# clipping class
#

class clip(canvasitem.canvasitem):

    """class for use in canvas constructor which clips to a path"""

    def __init__(self, path):
        """construct a clip instance for a given path"""
        self.path = path

    def bbox(self):
        # as a canvasitem a clipping path has NO influence on the bbox...
        return bboxmodule.empty()

    def clipbbox(self):
        # ... but for clipping, we nevertheless need the bbox
        return self.path.bbox()

    def processPS(self, file, writer, context, registry, bbox):
        file.write("newpath\n")
        self.path.outputPS(file, writer)
        file.write("clip\n")

    def processPDF(self, file, writer, context, registry, bbox):
        self.path.outputPDF(file, writer)
        file.write("W n\n")


#
# general canvas class
#

class _canvas(canvasitem.canvasitem):

    """a canvas holds a collection of canvasitems"""

    def __init__(self, attrs=None, texrunner=None):

        """construct a canvas

        The canvas can be modfied by supplying a list of attrs, which have
        to be instances of one of the following classes:
         - trafo.trafo (leading to a global transformation of the canvas)
         - canvas.clip (clips the canvas)
         - style.strokestyle, style.fillstyle (sets some global attributes of the canvas)

        Note that, while the first two properties are fixed for the
        whole canvas, the last one can be changed via canvas.set().

        The texrunner instance used for the text method can be specified
        using the texrunner argument. It defaults to text.defaulttexrunner

        """

        self.items     = []
        self.trafo     = trafo.trafo()
        self.clipbbox  = None
        if attrs is None:
            attrs = []
        if texrunner is not None:
            self.texrunner = texrunner
        else:
            # prevent cyclic imports
            import text
            self.texrunner = text.defaulttexrunner

        attr.checkattrs(attrs, [trafo.trafo_pt, clip, style.strokestyle, style.fillstyle])
        # We have to reverse the trafos such that the PostScript concat operators
        # are in the right order. Correspondingly, we below multiply the current self.trafo
        # from the right.
        # Note that while for the stroke and fill styles the order doesn't matter at all,
        # this is not true for the clip operation.
        for aattr in attrs[::-1]:
            if isinstance(aattr, trafo.trafo_pt):
                self.trafo = self.trafo * aattr
            elif isinstance(aattr, clip):
                if self.clipbbox is None:
                    self.clipbbox = aattr.clipbbox().transformed(self.trafo)
                else:
                    self.clippbox *= aattr.clipbbox().transformed(self.trafo)
            self.items.append(aattr)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]

    def bbox(self):
        """returns bounding box of canvas

        Note that this bounding box doesn't take into account the linewidths, so
        is less accurate than the one used when writing the output to a file.
        """
        obbox = bboxmodule.empty()
        for cmd in self.items:
            obbox += cmd.bbox()

        # transform according to our global transformation and
        # intersect with clipping bounding box (which has already been
        # transformed in canvas.__init__())
        obbox.transform(self.trafo)
        if self.clipbbox is not None:
            obbox *= self.clipbbox
        return obbox

    def processPS(self, file, writer, context, registry, bbox):
        context = context()
        if self.items:
            file.write("gsave\n")
            nbbox = bboxmodule.empty()
            for item in self.items:
                item.processPS(file, writer, context, registry, nbbox)
            # update bounding bbox
            nbbox.transform(self.trafo)
            if self.clipbbox is not None:
                nbbox *= self.clipbbox
            bbox += nbbox
            file.write("grestore\n")

    def processPDF(self, file, writer, context, registry, bbox):
        context = context()
        context.trafo = context.trafo * self.trafo
        if self.items:
            file.write("q\n") # gsave
            nbbox = bboxmodule.empty()
            for item in self.items:
                if isinstance(item, style.fillstyle):
                    context.fillstyles.append(item)
                if not writer.text_as_path:
                    if isinstance(item, font.text_pt):
                        if not context.textregion:
                            file.write("BT\n")
                            context.textregion = 1
                    else:
                        if context.textregion:
                            file.write("ET\n")
                            context.textregion = 0
                            context.selectedfont = None
                item.processPDF(file, writer, context, registry, nbbox)
            if context.textregion:
                file.write("ET\n")
                context.textregion = 0
                context.selectedfont = None
            # update bounding bbox
            nbbox.transform(self.trafo)
            if self.clipbbox is not None:
                nbbox *= self.clipbbox
            bbox += nbbox
            file.write("Q\n") # grestore

    def insert(self, item, attrs=None):
        """insert item in the canvas.

        If attrs are passed, a canvas containing the item is inserted applying attrs.

        returns the item, possibly wrapped in canvas

        """

        if not isinstance(item, canvasitem.canvasitem):
            raise RuntimeError("only instances of canvasitem.canvasitem can be inserted into a canvas")

        if attrs:
            sc = _canvas(attrs)
            sc.insert(item)
            item = sc
        self.items.append(item)
        return item

    def draw(self, path, attrs):
        """draw path on canvas using the style given by args

        The argument attrs consists of PathStyles, which modify
        the appearance of the path, PathDecos, which add some new
        visual elements to the path, or trafos, which are applied
        before drawing the path.

        """

        attrs = attr.mergeattrs(attrs)
        attr.checkattrs(attrs, [deco.deco, deformer.deformer, style.fillstyle, style.strokestyle, style.fillrule])

        for adeformer in attr.getattrs(attrs, [deformer.deformer]):
            path = adeformer.deform(path)

        styles = attr.getattrs(attrs, [style.fillstyle, style.strokestyle])
        fillrule, = attr.getattrs(attrs, [style.fillrule]) or [style.fillrule.nonzero_winding]
        dp = deco.decoratedpath(path, styles=styles, fillrule=fillrule)

        # add path decorations and modify path accordingly
        for adeco in attr.getattrs(attrs, [deco.deco]):
            adeco.decorate(dp, self.texrunner)

        self.insert(dp)

    def stroke(self, path, attrs=[]):
        """stroke path on canvas using the style given by args

        The argument attrs consists of PathStyles, which modify
        the appearance of the path, PathDecos, which add some new
        visual elements to the path, or trafos, which are applied
        before drawing the path.

        """

        self.draw(path, [deco.stroked]+list(attrs))

    def fill(self, path, attrs=[]):
        """fill path on canvas using the style given by args

        The argument attrs consists of PathStyles, which modify
        the appearance of the path, PathDecos, which add some new
        visual elements to the path, or trafos, which are applied
        before drawing the path.

        """

        self.draw(path, [deco.filled]+list(attrs))

    def settexrunner(self, texrunner):
        """sets the texrunner to be used to within the text and text_pt methods"""

        self.texrunner = texrunner

    def text(self, x, y, atext, *args, **kwargs):
        """insert a text into the canvas

        inserts a textbox created by self.texrunner.text into the canvas

        returns the inserted textbox"""

        return self.insert(self.texrunner.text(x, y, atext, *args, **kwargs))


    def text_pt(self, x, y, atext, *args):
        """insert a text into the canvas

        inserts a textbox created by self.texrunner.text_pt into the canvas

        returns the inserted textbox"""

        return self.insert(self.texrunner.text_pt(x, y, atext, *args))

#
# user canvas class which adds a few convenience methods for single page output
#

def _wrappedindocument(method):
    def wrappedindocument(self, file=None, **kwargs):
        d = document.document([document.page(self, **kwargs)])
        self.__name__ = method.__name__
        self.__doc__ = method.__doc__
        return method(d, file)
    return wrappedindocument


class canvas(_canvas):

    """a canvas holds a collection of canvasitems"""

    writeEPSfile = _wrappedindocument(document.document.writeEPSfile)
    writePSfile = _wrappedindocument(document.document.writePSfile)
    writePDFfile = _wrappedindocument(document.document.writePDFfile)
    writetofile = _wrappedindocument(document.document.writetofile)

    def pipeGS(self, filename="-", device=None, resolution=100,
               gscommand="gs", gsoptions="",
               textalphabits=4, graphicsalphabits=4,
               ciecolor=False, input="eps", **kwargs):
        if device is None:
            if filename.endswith(".png"):
                device = "png16m"
            if filename.endswith(".jpg"):
                device = "jpeg"
        gscommand += " -dEPSCrop -dNOPAUSE -dQUIET -dBATCH -r%i -sDEVICE=%s -sOutputFile=%s" % (resolution, device, filename)
        if gsoptions:
            gscommand += " %s" % gsoptions
        if textalphabits is not None:
            gscommand += " -dTextAlphaBits=%i" % textalphabits
        if graphicsalphabits is not None:
            gscommand += " -dGraphicsAlphaBits=%i" % graphicsalphabits
        if ciecolor:
            gscommand += " -dUseCIEColor"
        if input == "eps":
            gscommand += " -"
            pipe = pycompat.popen(gscommand, "wb")
            self.writeEPSfile(pipe, **kwargs)
            pipe.close()
        elif input == "pdf":
            fd, fname = tempfile.mkstemp()
            f = os.fdopen(fd, "wb")
            gscommand += " %s" % fname
            self.writePDFfile(f, **kwargs)
            f.close()
            os.system(gscommand)
            os.unlink(fname)
        else:
            raise RuntimeError("input 'eps' or 'pdf' expected")


class layered_canvas(canvas):

    def __init__(self, *args, **kwargs):
        canvas.__init__(self, *args, **kwargs)
        self._layers = {}

    def layer(self, name):
        try:
            group, layer = name.split(".", 1)
        except ValueError:
            if not name in self._layers:
                self._layers[name] = self.insert(layered_canvas(texrunner=self.texrunner))
            return self._layers[name]
        else:
            if not group in self._layers:
                self._layers[group] = self.insert(layered_canvas(texrunner=self.texrunner))
            return self._layers[group].layer(layer)


