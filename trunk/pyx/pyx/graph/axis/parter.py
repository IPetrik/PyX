#!/usr/bin/env python
# -*- coding: ISO-8859-1 -*-
#
#
# Copyright (C) 2002-2004 J�rg Lehmann <joergl@users.sourceforge.net>
# Copyright (C) 2003-2004 Michael Schindler <m-schindler@users.sourceforge.net>
# Copyright (C) 2002-2004 Andr� Wobst <wobsta@users.sourceforge.net>
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


import math
from pyx import helper # TODO to be removed
from pyx.graph.axis import tick


# Note: A partition is a list of ticks.

class _partdata:
    """state storage class for a partfunction

    partdata is used to keep local data and a current state to emulate
    generators. In the future we might use yield statements within a
    partfunction. Currently we add partdata by a lambda construct and
    do inplace modifications within partdata to keep track of the state.
    """

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _parter:
    """interface of a partitioner"""

    def partfunctions(self, min, max, extendmin, extendmax):
        """returns a list of partfunctions

        A partfunction can be called without further arguments and
        it will return a new partition each time, or None. Several
        partfunctions are used to walk in different "directions"
        (like more and less partitions).

        Note that we do not alternate walking in different directions
        (i.e. alternate the partfunction calls). Instead we first walk
        into one direction (which should give less and less ticks) until
        the rating becomes bad and when try more ticks. We want to keep
        the number of ticks small compared to a simple alternate search.
        """
        # This is a (useless) empty partitioner.
        return []


class linear(_parter):
    """partitioner to create a single linear parition"""

    def __init__(self, tickdist=None, labeldist=None, extendtick=0, extendlabel=None, epsilon=1e-10):
        if tickdist is None and labeldist is not None:
            self.ticklist = (tick.rational(helper.ensuresequence(labeldist)[0]),)
        else:
            self.ticklist = map(tick.rational, helper.ensuresequence(tickdist))
        if labeldist is None and tickdist is not None:
            self.labellist = (tick.rational(helper.ensuresequence(tickdist)[0]),)
        else:
            self.labellist = map(tick.rational, helper.ensuresequence(labeldist))
        self.extendtick = extendtick
        self.extendlabel = extendlabel
        self.epsilon = epsilon

    def extendminmax(self, min, max, dist, extendmin, extendmax):
        """return new min, max tuple extending the range min, max
        - dist is the tick distance to be used
        - extendmin and extendmax are booleans to allow for the extension"""
        if extendmin:
            min = float(dist) * math.floor(min / float(dist) + self.epsilon)
        if extendmax:
            max = float(dist) * math.ceil(max / float(dist) - self.epsilon)
        return min, max

    def getticks(self, min, max, dist, ticklevel=None, labellevel=None):
        """return a list of equal spaced ticks
        - the tick distance is dist, the ticklevel is set to ticklevel and
          the labellevel is set to labellevel
        - min, max is the range where ticks should be placed"""
        imin = int(math.ceil(min/float(dist) - 0.5*self.epsilon))
        imax = int(math.floor(max/float(dist) + 0.5*self.epsilon))
        ticks = []
        for i in range(imin, imax + 1):
            ticks.append(tick.tick((i*dist.num, dist.denom), ticklevel=ticklevel, labellevel=labellevel))
        return ticks

    def partfunction(self, data):
        if data.first:
            data.first = 0
            min = data.min
            max = data.max
            if self.extendtick is not None and len(self.ticklist) > self.extendtick:
                min, max = self.extendminmax(min, max, self.ticklist[self.extendtick], data.extendmin, data.extendmax)
            if self.extendlabel is not None and len(self.labellist) > self.extendlabel:
                min, max = self.extendminmax(min, max, self.labellist[self.extendlabel], data.extendmin, data.extendmax)

            ticks = []
            for i in range(len(self.ticklist)):
                ticks = tick.mergeticklists(ticks, self.getticks(min, max, self.ticklist[i], ticklevel = i))
            for i in range(len(self.labellist)):
                ticks = tick.mergeticklists(ticks, self.getticks(min, max, self.labellist[i], labellevel = i))

            return ticks

        return None

    def partfunctions(self, min, max, extendmin, extendmax):
        return [lambda d=_partdata(first=1, min=min, max=max, extendmin=extendmin, extendmax=extendmax):
                       self.partfunction(d)]

lin = linear


class autolinear(_parter):
    """partitioner to create an arbitrary number of linear paritions"""

    defaultvariants = [[tick.rational((1, 1)), tick.rational((1, 2))],
                       [tick.rational((2, 1)), tick.rational((1, 1))],
                       [tick.rational((5, 2)), tick.rational((5, 4))],
                       [tick.rational((5, 1)), tick.rational((5, 2))]]

    def __init__(self, variants=defaultvariants, extendtick=0, epsilon=1e-10):
        self.variants = variants
        self.extendtick = extendtick
        self.epsilon = epsilon
        self.state_less = 1
        self.state_more = 2
        self.state_done = 3

    def partfunctions(self, min, max, extendmin, extendmax):
        logmm = math.log(max - min) / math.log(10)
        if logmm < 0: # correction for rounding towards zero of the int routine
            base = tick.rational((10, 1), power=int(logmm-1))
        else:
            base = tick.rational((10, 1), power=int(logmm))
        ticks = map(tick.rational, self.variants[0])
        useticks = [t * base for t in ticks]

        return [lambda d=_partdata(min=min, max=max, extendmin=extendmin, extendmax=extendmax,
                                   sign=1, tickindex=-1, base=tick.rational(base)):
                       self.partfunction(d),
                lambda d=_partdata(min=min, max=max, extendmin=extendmin, extendmax=extendmax,
                                   sign=-1, tickindex=0, base=tick.rational(base)):
                       self.partfunction(d)]

    def partfunction(self, data):
        if data.sign == 1:
            if data.tickindex < len(self.variants) - 1:
                data.tickindex += 1
            else:
                data.tickindex = 0
                data.base.num *= 10
        else:
            if data.tickindex:
                data.tickindex -= 1
            else:
                data.tickindex = len(self.variants) - 1
                data.base.denom *= 10
        tickdist = [tick.rational(t) * data.base for t in self.variants[data.tickindex]]
        linearparter = linear(tickdist=tickdist, extendtick=self.extendtick, epsilon=self.epsilon)
        return linearparter.partfunctions(min=data.min, max=data.max, extendmin=data.extendmin, extendmax=data.extendmax)[0]()

autolin = autolinear


class preexp:
    """definition of a logarithmic partition

    exp is an integer, which defines multiplicator (usually 10).
    pres are a list of tick positions (rational numbers, e.g.
    instances of rational). possible positions are the tick
    positions and arbitrary divisions and multiplications of
    the tick positions by exp."""

    def __init__(self, pres, exp):
         self.pres = pres
         self.exp = exp


class logarithmic(linear):
    """partitioner to create a single logarithmic parition"""

    # define some useful constants
    pre1exp5   = preexp([tick.rational((1, 1))], 100000)
    pre1exp4   = preexp([tick.rational((1, 1))], 10000)
    pre1exp3   = preexp([tick.rational((1, 1))], 1000)
    pre1exp2   = preexp([tick.rational((1, 1))], 100)
    pre1exp    = preexp([tick.rational((1, 1))], 10)
    pre125exp  = preexp([tick.rational((1, 1)), tick.rational((2, 1)), tick.rational((5, 1))], 10)
    pre1to9exp = preexp([tick.rational((x, 1)) for x in range(1, 10)], 10)
    #  ^- we always include 1 in order to get extendto(tick|label)level to work as expected

    def __init__(self, tickpos=None, labelpos=None, extendtick=0, extendlabel=None, epsilon=1e-10):
        if tickpos is None and labelpos is not None:
            self.ticklist = (helper.ensuresequence(labelpos)[0],)
        else:
            self.ticklist = helper.ensuresequence(tickpos)

        if labelpos is None and tickpos is not None:
            self.labellist = (helper.ensuresequence(tickpos)[0],)
        else:
            self.labellist = helper.ensuresequence(labelpos)
        self.extendtick = extendtick
        self.extendlabel = extendlabel
        self.epsilon = epsilon

    def extendminmax(self, min, max, preexp, extendmin, extendmax):
        minpower = None
        maxpower = None
        for i in xrange(len(preexp.pres)):
            imin = int(math.floor(math.log(min / float(preexp.pres[i])) /
                                  math.log(preexp.exp) + self.epsilon)) + 1
            imax = int(math.ceil(math.log(max / float(preexp.pres[i])) /
                                 math.log(preexp.exp) - self.epsilon)) - 1
            if minpower is None or imin < minpower:
                minpower, minindex = imin, i
            if maxpower is None or imax >= maxpower:
                maxpower, maxindex = imax, i
        if minindex:
            minrational = preexp.pres[minindex - 1]
        else:
            minrational = preexp.pres[-1]
            minpower -= 1
        if maxindex != len(preexp.pres) - 1:
            maxrational = preexp.pres[maxindex + 1]
        else:
            maxrational = preexp.pres[0]
            maxpower += 1
        if extendmin:
            min = float(minrational) * float(preexp.exp) ** minpower
        if extendmax:
            max = float(maxrational) * float(preexp.exp) ** maxpower
        return min, max

    def getticks(self, min, max, preexp, ticklevel=None, labellevel=None):
        ticks = []
        minimin = 0
        maximax = 0
        for f in preexp.pres:
            thisticks = []
            imin = int(math.ceil(math.log(min / float(f)) /
                                 math.log(preexp.exp) - 0.5 * self.epsilon))
            imax = int(math.floor(math.log(max / float(f)) /
                                  math.log(preexp.exp) + 0.5 * self.epsilon))
            for i in range(imin, imax + 1):
                pos = f * tick.rational((preexp.exp, 1), power=i)
                thisticks.append(tick.tick((pos.num, pos.denom), ticklevel = ticklevel, labellevel = labellevel))
            ticks = tick.mergeticklists(ticks, thisticks)
        return ticks

log = logarithmic


class autologarithmic(logarithmic):
    """partitioner to create several logarithmic paritions"""

    defaultvariants = [([logarithmic.pre1exp,      # ticks
                         logarithmic.pre1to9exp],  # subticks
                        [logarithmic.pre1exp,      # labels
                         logarithmic.pre125exp]),  # sublevels

                       ([logarithmic.pre1exp,      # ticks
                         logarithmic.pre1to9exp],  # subticks
                        None),                     # labels like ticks

                       ([logarithmic.pre1exp2,     # ticks
                         logarithmic.pre1exp],     # subticks
                        None),                     # labels like ticks

                       ([logarithmic.pre1exp3,     # ticks
                         logarithmic.pre1exp],     # subticks
                        None),                     # labels like ticks

                       ([logarithmic.pre1exp4,     # ticks
                         logarithmic.pre1exp],     # subticks
                        None),                     # labels like ticks

                       ([logarithmic.pre1exp5,     # ticks
                         logarithmic.pre1exp],     # subticks
                        None)]                     # labels like ticks

    def __init__(self, variants=defaultvariants, extendtick=0, extendlabel=None, epsilon=1e-10):
        self.variants = variants
        if len(variants) > 2:
            self.variantsindex = divmod(len(variants), 2)[0]
        else:
            self.variantsindex = 0
        self.extendtick = extendtick
        self.extendlabel = extendlabel
        self.epsilon = epsilon

    def partfunctions(self, min, max, extendmin, extendmax):
        return [lambda d=_partdata(min=min, max=max, extendmin=extendmin, extendmax=extendmax,
                                   sign=1, variantsindex=self.variantsindex-1):
                       self.partfunction(d),
                lambda d=_partdata(min=min, max=max, extendmin=extendmin, extendmax=extendmax,
                                   sign=-1, variantsindex=self.variantsindex):
                       self.partfunction(d)]

    def partfunction(self, data):
        data.variantsindex += data.sign
        logarithmicparter= logarithmic(tickpos=self.variants[data.variantsindex][0], labelpos=self.variants[data.variantsindex][1],
                                       extendtick=self.extendtick, extendlabel=self.extendlabel, epsilon=self.epsilon)
        return logarithmicparter.partfunctions(min=data.min, max=data.max, extendmin=data.extendmin, extendmax=data.extendmax)[0]()

autolog = autologarithmic
