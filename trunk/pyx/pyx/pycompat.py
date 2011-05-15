# -*- encoding: utf-8 -*-
#
#
# Copyright (C) 2011 Jörg Lehmann <joergl@users.sourceforge.net>
# Copyright (C) 2011 André Wobst <wobsta@users.sourceforge.net>
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

class _marker: pass

def popen(cmd, mode="r", bufsize=_marker):
    try:
        import subprocess
        if bufsize is _marker:
            return subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE).stdout
        else:
            return subprocess.Popen(cmd, shell=True, bufsize=bufsize, stdout=PIPE).stdout
    except ImportError:
        import os
        if bufsize is _marker:
            return os.popen(cmd, mode)
        else:
            return os.popen(cmd, mode, bufsize)

try:
    any = any
except NameError:
    def any(iterable):
        for element in iterable:
            if element:
                return True
        return False

try:
    set = set
except NameError:
    # Python 2.3
    from sets import Set as set
