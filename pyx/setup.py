#!/usr/bin/env python
# -*- coding: ISO-8859-1 -*-

"""Python package for the generation of encapsulated PostScript figures

PyX is a Python package for the creation of encapsulated PostScript figures.
It provides both an abstraction of PostScript and a TeX/LaTeX interface.
Complex tasks like 2d and 3d plots in publication-ready quality are built out
of these primitives.
"""

from distutils import log
from distutils.core import setup, Extension
from distutils.command.build_py import build_py
from distutils.command.install_data import install_data
from distutils.command.install_lib import install_lib
import ConfigParser
import sys, os
import pyx

#
# build list of extension modules
#

ext_modules = []
pykpathsea_ext_module = Extension("pyx.pykpathsea._pykpathsea",
                                  sources=["pyx/pykpathsea/pykpathsea.c"],
                                  libraries=["kpathsea"])
t1strip_ext_module = Extension("pyx.t1strip._t1strip",
                               sources=["pyx/t1strip/t1strip.c", "pyx/t1strip/writet1.c"])

# obtain information on which modules have to be built from setup.cfg file
cfg = ConfigParser.ConfigParser()
cfg.read("setup.cfg")
if cfg.has_section("PyX"):
    if cfg.has_option("PyX", "build_pykpathsea") and cfg.getboolean("PyX", "build_pykpathsea"):
        ext_modules.append(pykpathsea_ext_module)
    if cfg.has_option("PyX", "build_t1strip") and cfg.getboolean("PyX", "build_t1strip"):
        ext_modules.append(t1strip_ext_module)

#
# data files
#

data_files = [# share/pyx is taken relative to "setup.py install --home=..."
              ("share/pyx", ["pyx/lfs/10pt.lfs",
                             "pyx/lfs/11pt.lfs",
                             "pyx/lfs/12pt.lfs",
                             "pyx/lfs/10ptex.lfs",
                             "pyx/lfs/11ptex.lfs",
                             "pyx/lfs/12ptex.lfs",
                             "pyx/lfs/foils17pt.lfs",
                             "pyx/lfs/foils20pt.lfs",
                             "pyx/lfs/foils25pt.lfs",
                             "pyx/lfs/foils30pt.lfs",
                             "contrib/pyx.def"]),
              # /etc is taken relative to "setup.py install --root=..."
              ("/etc", ["pyxrc"])]

#
# extend install commands to overwrite the original siteconfig.py
#

class pyx_build_py(build_py):

    def build_module(self, module, module_file, package):
        if module == "siteconfig":
            # generate path information as the original build_module does it
            outfile = self.get_module_outfile(self.build_lib, [package], module)
            outdir = os.path.dirname(outfile)
            self.mkpath(outdir)

            log.info("creating proper %s" % outfile)

            indir = os.path.dirname(module_file)
            addjoinstring = ", ".join(["'..'" for d in outdir.split(os.path.sep)] +
                                      ["'%s'" % d for d in indir.split(os.path.sep)])
            fin = open(module_file, "r")
            fout = open(outfile, "w")
            for line in fin.readlines():
                fout.write(line.replace("os.path.join(os.path.dirname(__file__), ",
                                        "os.path.join(os.path.dirname(__file__), %s, " % addjoinstring))
            fin.close()
            fout.close()
        else:
            return build_py.build_module(self, module, module_file, package)

class pyx_install_data(install_data):

    def run(self):
        self.pyx_lfsdir = self.pyx_sharedir = os.path.join(self.install_dir, "share", "pyx")
        self.pyx_pyxrc = os.path.join(self.root or "/", "etc", "pyxrc")
        install_data.run(self)

class pyx_install_lib(install_lib):

    def run(self):
        # siteconfig.py depends on install_data:
        self.run_command('install_data')
        install_lib.run(self)

    def install(self):
        result = install_lib.install(self)
        install_data = self.distribution.command_obj["install_data"]
        outfile = os.path.join(self.install_dir, "pyx", "siteconfig.py")
        log.info("creating proper %s" % outfile)
        f = open(outfile, "w")
        f.write("lfsdir = %r\n" % install_data.pyx_lfsdir)
        f.write("sharedir = %r\n" % install_data.pyx_sharedir)
        f.write("pyxrc = %r\n" % install_data.pyx_pyxrc)
        f.close()
        return result

#
# additional package metadata (only available in Python 2.3 and above)
#

if sys.version_info >= (2, 3):
    addargs = { "classifiers":
                    [ "Development Status :: 3 - Alpha",
                      "Intended Audience :: Developers",
                      "Intended Audience :: End Users/Desktop",
                      "License :: OSI Approved :: GNU General Public License (GPL)",
                      "Operating System :: OS Independent",
                      "Programming Language :: Python",
                      "Topic :: Multimedia :: Graphics",
                      "Topic :: Scientific/Engineering :: Visualization",
                      "Topic :: Software Development :: Libraries :: Python Modules" ],
                "download_url":
                    "http://sourceforge.net/project/showfiles.php?group_id=45430",
                "platforms":
                    "OS independent",
              }
else:
    addargs = {}

# We're using the module docstring as the distutils descriptions. (seen in Zope3 setup.py)
doclines = __doc__.split("\n")

setup(name="PyX",
      version=pyx.__version__,
      author="J�rg Lehmann, Andr� Wobst",
      author_email="pyx-devel@lists.sourceforge.net",
      url="http://pyx.sourceforge.net/",
      description=doclines[0],
      long_description="\n".join(doclines[2:]),
      license="GPL",
      packages=["pyx", "pyx/graph", "pyx/graph/axis", "pyx/t1strip", "pyx/pykpathsea"],
      ext_modules=ext_modules,
      data_files=data_files,
      cmdclass = {"build_py": pyx_build_py,
                  "install_data": pyx_install_data,
                  "install_lib": pyx_install_lib},
      **addargs)
