from pyx import *

text.set(mode="latex")
text.preamble(r"\usepackage{palatino}")

c = canvas.canvas()
c.text(0, 0, r"\LaTeX{} doesn't need to look like \LaTeX{} all the time.")
c.writeEPSfile("font")
c.writePDFfile("font")
