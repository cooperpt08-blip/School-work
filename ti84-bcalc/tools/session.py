#!/usr/bin/env python3
"""Run one simulated key session and print the screens shown at each Pause.
usage: session.py input1 input2 ...   (menu choices / typed text)
The session simply stops when it needs more input than was given."""
import sys
import tisim

c = tisim.Calc(tisim.load_programs(), sys.argv[1:])
err = None
try:
    c.run("BCALC")
except tisim.NeedInput:
    pass
except tisim.TIError as e:
    err = e
for p in c.pages:
    print(p)
    print("-" * 16)
if err:
    print("\n".join(c.log[-15:]))
    print("ERROR:", err)
print(f"steps={c.steps} yevals={c.yevals} warnings={c.warnings}")
