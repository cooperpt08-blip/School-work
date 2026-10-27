#!/usr/bin/env python3
"""Regression tests: run the BCALC programs in the simulator on every
problem type from the MATH 1309 Test 2 review and check the screens.

Each case = (name, key presses / typed inputs, strings that must appear
on the screens).  Run:  python3 tests/test_review.py [-v]
Writes tests/RESULTS.md with every screen for the documentation."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import tisim  # noqa: E402

N, E = "⁻", "𝑒^("   # negation key, e^( key

CASES = [
    # ---------------- Q1 derivatives: CHECK MY F' with correct answers
    ("Q1a d/dx ln x/x", [1, 2, "ln(X)/X", 1, "(1-ln(X))/X²"], ["ALL MATCH!"]),
    ("Q1b d/dx x/e^x", [1, 2, f"X/{E}X)", 1, f"(1-X)/{E}X)"], ["ALL MATCH!"]),
    ("Q1c (5x+sqrt x)e^4x", [1, 2, f"(5X+√(X)){E}4X)", 1,
                              f"(5+1/(2√(X))){E}4X)+4(5X+√(X)){E}4X)"], ["ALL MATCH!"]),
    ("Q1d (x^2-4)ln x  (correct +)", [1, 2, "(X²-4)ln(X)", 1, "2Xln(X)+(X²-4)/X"], ["ALL MATCH!"]),
    ("Q1d key's answer (sign error)", [1, 2, "(X²-4)ln(X)", 1, "(X²-4)/X-2Xln(X)"], ["MISMATCH"]),
    ("Q1e e^(3x^2-5)", [1, 2, f"{E}3X²-5)", 1, f"6X{E}3X²-5)"], ["ALL MATCH!"]),
    ("Q1f ln(w^3-5)/6", [1, 2, "ln(X³-5)/6", 1, "3X²/(6(X³-5))"], ["ALL MATCH!"]),
    ("Q1g ln(x^2)", [1, 2, "ln(X²)", 1, "2/X"], ["ALL MATCH!"]),
    ("Q1h (ln x)^2", [1, 2, "(ln(X))²", 1, "2ln(X)/X"], ["ALL MATCH!"]),
    ("Q1i e^x/x", [1, 2, f"{E}X)/X", 1, f"{E}X)(X-1)/X²"], ["ALL MATCH!"]),
    ("Q1 f,f',f'' at x (ln x/x, x=1)", [1, 1, "ln(X)/X", 1],
     ["F(X)=0", "F'(X)~1", "F''(X)~⁻3"]),
    ("Q1 derivative formula x/(x^2+1)", [1, 3, "X/(X²+1)"],
     ["(X²+1-X*(2X))/(X²+1)²", "CHECKED: CORRECT"]),
    ("f'' check x/(x^2+1)", [1, 2, "X/(X²+1)", 2, "2X(X²-3)/(X²+1)³"], ["ALL MATCH!"]),
    # ---------------- symbolic derivative formulas (any f)
    ("formula Q1a ln x/x", [1, 3, "ln(X)/X"], ["F'(X)=", "(1/X*X-ln(X))/X²", "CHECKED: CORRECT"]),
    ("formula Q1c", [1, 3, f"(5X+√(X)){E}4X)"], ["(5+1/(2√(X)))*", "(4e^(4X))", "CHECKED: CORRECT"]),
    ("formula Q1d", [1, 3, "(X²-4)ln(X)"], ["2X*ln(X)+(X²-4)*(1/X)", "CHECKED: CORRECT"]),
    ("formula Q1e", [1, 3, f"{E}3X²-5)"], ["e^(3X²-5)*(6X)", "CHECKED: CORRECT"]),
    ("formula Q1h", [1, 3, "(ln(X))²"], ["2ln(X)*(1/X)", "CHECKED: CORRECT"]),
    ("formula poly + f''", [1, 3, "X³-6X²+9X", 1], ["3X²-12X+9", "F''(X)=", "6X-12"]),
    ("formula f'' of e^x/x", [1, 3, f"{E}X)/X", 1], ["F''(X)=", "CHECKED: CORRECT"]),
    ("formula refuses abs", [1, 3, "abs(X)"], ["CAN'T DO THIS F"]),
    ("Q2 formulas a", [2, 1, "³√(4X^5-7YX+2)"], ["FX=", "(20X^4-7Y)/(3", "FY=", "CHECKED: CORRECT"]),
    ("Q2 formulas b", [2, 1, "(3X^5Y²+2X-5Y)^4"], ["(3X^5*(2Y)-", "CHECKED: CORRECT"]),
    ("Q2 formulas f", [2, 1, f"Y{E}2X-4Y)"], ["e^(2X-4Y)+Y*(⁻4e^(2X-4Y))", "CHECKED: CORRECT"]),
    ("Cobb formula", [2, 1, "10X^.75Y^.25"], ["7.5X^(⁻.25)*Y^.25", "CHECKED: CORRECT"]),
    # ---------------- Q2 partial derivatives
    ("Q2a fx cube root", [2, 3, "³√(4X^5-7YX+2)", 1,
                          "(20X^4-7Y)/(3(4X^5-7YX+2)^(2/3))"], ["ALL MATCH!"]),
    ("Q2b fy  key answer (missing -5)", [2, 3, "(3X^5Y²+2X-5Y)^4", 2,
                                          "4(3X^5Y²+2X-5Y)³(6X^5Y)"], ["MISMATCH"]),
    ("Q2b fy  correct", [2, 3, "(3X^5Y²+2X-5Y)^4", 2,
                         "4(3X^5Y²+2X-5Y)³(6X^5Y-5)"], ["ALL MATCH!"]),
    ("Q2c fx", [2, 3, "(2X³-2Y³)/(4Y)", 1, "3X²/(2Y)"], ["ALL MATCH!"]),
    ("Q2d fy", [2, 3, "(2X³-2Y³)/(4Y)", 2, f"{N}X³/(2Y²)-Y"], ["ALL MATCH!"]),
    ("Q2e fx", [2, 3, f"{N}10ln((X+7)/Y)", 1, f"{N}10/(X+7)"], ["ALL MATCH!"]),
    ("Q2f fy", [2, 3, f"Y{E}2X-4Y)", 2, f"(1-4Y){E}2X-4Y)"], ["ALL MATCH!"]),
    ("Q2 values at (1,2)", [2, 2, f"Y{E}2X-4Y)", 1, 2],
     ["F(X,Y)=.004958", "FX~.009915", "FY~⁻.017351"]),
    # ---------------- Q3 sales S=200t/(t+1)^2
    ("Q3 S(2), S'(2)", [5, 2, "200X/(X+1)²", 2],
     ["F(X)=44.444444", "=400/9", "F'(X)~⁻7.407407", "=⁻200/27", "F DECREASING AT"]),
    # ---------------- Q5 graphing, exact poly/rational mode
    ("Q5a x/(x^2+1) rational", [3, 2, "X", "X²+1"],
     ["LOC MIN (⁻1,⁻.5)", "LOC MAX (1,.5)", "INFL PT (0,0)", "X=√(3) Y=√(3/16)",
      " (⁻1,1)", "HA: Y=0"]),
    ("Q5b -x^4+6x^2 poly", [3, 2, f"{N}X^4+6X²", 1],
     ["X-INT (0,0)", "X=√(6)", "LOC MAX (1.7321,", "LOC MIN (0,0)",
      "INFL PT (⁻1,5)", "INFL PT (1,5)", "F->-INF"]),
    ("Q5c x^3-6x^2+9x poly", [3, 2, "X³-6X²+9X", 1],
     ["LOC MAX (1,4)", "LOC MIN (3,0)", "INFL PT (2,2)", "X-INT (3,0)"]),
    ("Q5d (x+1)/(x^2-4) rational", [3, 2, "X+1", "X²-4"],
     ["VERT ASYMP X=⁻2", "VERT ASYMP X=2", "Y-INT (0,⁻.25)", "X-INT (⁻1,0)",
      "NONE FOUND", " (⁻2,2)", "INFL PT (⁻.3622,", "HA: Y=0"]),
    ("hole: (x^2-1)/(x-1)", [3, 2, "X²-1", "X-1"],
     ["HOLE PT (1,2)", "(F IS THIS LINE", "Y-INT (0,1)"]),
    ("slant asymptote (x^2+1)/x", [3, 2, "X²+1", "X"],
     ["VERT ASYMP X=0", "LOC MIN (1,2)", "LOC MAX (⁻1,⁻2)", "SLANT Y=MX+B, M=1", "B=0"]),
    ("not a polynomial is rejected", [3, 2, "ln(X+20)", 1], ["N,D MUST BE"]),
    ("reuse last f (BCINF)", [1, 1, "X³", 2, 2, 1, 1, 3], ["F(X)=8", "F(X)=27", "F'(X)~27"]),
    # ---------------- Q5: type f(x) once (auto exact/numeric + sketch)
    ("Q5a one input", [3, 1, "X/(X²+1)"],
     ["NUM=-X^2+1", "NUM=2X^3-6X", "LOC MAX (1,.5)", "INFL PT (0,0)", "HA: Y=0",
      "GRAPH: PRESS"]),
    ("Q5b one input", [3, 1, f"{N}X^4+6X²"],
     ["F'(X)=-4X^3+12X", "F''(X)=-12X^2+12", "LOC MIN (0,0)", "INFL PT (1,5)"]),
    ("Q5c one input", [3, 1, "X³-6X²+9X"],
     ["F'(X)=3X^2-12X+9", "F''(X)=6X-12", "LOC MAX (1,4)", "INFL PT (2,2)"]),
    ("Q5d one input", [3, 1, "(X+1)/(X²-4)"],
     ["NUM=-X^2-2X-4", "DEN=(X^2-4)²", "VERT ASYMP X=2", "INFL PT (⁻.3622,"]),
    ("one input, not rational -> numeric", [3, 1, "ln(X)/X"],
     ["VERT ASYMP X=0", "LOC MAX (2.7183,", "GRAPH: PRESS"]),
    ("one input, 1/x+x is not split wrongly", [3, 1, "1/X+X"],
     ["VERT ASYMP X=0", "LOC MIN (1,2)", "LOC MAX (⁻1,⁻2)"]),
    # ---------------- Q5 again with the numeric ANY F(X) scanner
    ("Q5a numeric", [3, 3, "X/(X²+1)", f"{N}10", 10],
     ["LOC MIN (⁻1,⁻.5)", "LOC MAX (1,.5)", "INFL PT (0,0)", "HA Y~0"]),
    ("Q5b numeric", [3, 3, f"{N}X^4+6X²", f"{N}10", 10],
     ["LOC MIN (0,0)", "INFL PT (1,5)", "X=√(6)"]),
    ("Q5c numeric", [3, 3, "X³-6X²+9X", f"{N}10", 10],
     ["LOC MAX (1,4)", "LOC MIN (3,0)", "INFL PT (2,2)"]),
    ("Q5d numeric", [3, 3, "(X+1)/(X²-4)", f"{N}10", 10],
     ["VERT ASYMP X=⁻2", "VERT ASYMP X=2", "INFL PT (⁻.3622,"]),
    ("extra: e^(-x^2) numeric", [3, 3, f"{E}{N}X²)", f"{N}4", 10],
     ["LOC MAX (0,1)", "INFL PT (⁻.7071,", "INFL PT (.7071,"]),
    ("extra: ln x / x numeric", [3, 3, "ln(X)/X", f"{N}4", 10],
     ["VERT ASYMP X=0", "LOC MAX (2.7183,", "INFL PT (4.4817,"]),
    ("extra: cusp cbrt(x)^2", [3, 3, "³√(X)²", f"{N}4", 10],
     ["LOC MIN (0,0)", "(UNDEFINED)"]),
    # ---------------- Q6 limits (L'Hopital module)
    ("Q6a (e^x-1)/x, x->0", [4, 3, f"{E}X)-1", "X", 1, 0, 1],
     ["L'HOPITAL OK", "LIM N/D~1", "LIM N'/D'~1"]),
    ("Q6b ln x/(x-1), x->1", [4, 3, "ln(X)", "X-1", 1, 1, 1], ["L'HOPITAL OK", "LIM N/D~1"]),
    ("Q6c ln x/(x-1), x->0+", [4, 3, "ln(X)", "X-1", 1, 0, 2],
     ["NO L'HOPITAL", "LIM N/D=+INF"]),
    ("Q6d x^2/ln x, x->1", [4, 3, "X²", "ln(X)", 1, 1, 1],
     ["LIM N/D DNE", "RIGHT:=+INF", "LEFT:=-INF"]),
    ("Q6e x^2/ln x, x->0+", [4, 3, "X²", "ln(X)", 1, 0, 2], ["LIM N/D~0"]),
    ("Q6f e^x/sqrt x, x->inf", [4, 3, f"{E}X)", "√(X)", 2],
     ["L'HOPITAL OK", "LIM N/D=+INF"]),
    ("Q6g e^x/sqrt x, x->0+", [4, 3, f"{E}X)", "√(X)", 1, 0, 2], ["LIM N/D=+INF"]),
    ("Q6h e^x/sqrt(-x), x->-inf", [4, 3, f"{E}X)", f"√({N}X)", 3], ["LIM N/D~0"]),
    ("Q6i x^2/ln x, x->inf", [4, 3, "X²", "ln(X)", 2], ["LIM N/D=+INF"]),
    ("limit of one f: ln x, x->0", [4, 1, "ln(X)", 0, 1],
     ["RIGHT:=-INF", "LEFT: UNDEFINED", "2-SIDED: DNE"]),
    # ---------------- marginal analysis
    ("marginal C,R,P at x=1000", [5, 1, 2, ".001X", "", ], []),
    # ---------------- optimization
    ("max profit p=10-.001x, C=5000+2x", [6, 2, 2, "10-.001X", "5000+2X", 0, 10000],
     ["ABS MAX (4000,11000)", "PRICE=6", "MC~2"]),
    ("abs extrema x^3-6x^2+9x on [0,5]", [6, 1, "X³-6X²+9X", 0, 5, 1],
     ["ABS MAX (5,20)", "ABS MIN (0,0)", "CRIT (1,4)"]),
    ("min average cost", [6, 3, ".1X²+10X+1000", 0, 500], ["ABS MIN (100,30)"]),
    ("price steps (rent)", [6, 4, 1, 80, 300, 1, 3, 10, 0],
     ["BEST STEPS N=15", "PRICE=95", "MAX PROFIT=21675"]),
    ("open box 15x8", [6, 4, 2, 15, 8], ["=5/3", "=2450/27"]),
    ("inventory EOQ", [6, 4, 3, 2500, 40, 2], ["ORDER SIZE X=316"]),
    # ---------------- diminishing returns, Cobb-Douglas
    ("diminishing returns", [7, 1, 1, f"{N}.25X^4+11X³-108X²+3000", 9, 24],
     ["DIMINISHING RET.", "AT (18,5916)", "F'(X)~972"]),
    ("Cobb-Douglas 10L^.75K^.25 at (600,100)", [7, 2, 1, 10, .75, .25, 600, 100],
     ["P=3833.658625", "MPL=PL~4.792073", "MPK=PK~9.584147", "CONSTANT RTS"]),
    # ---------------- sign chart tool, quick tools
    ("sign chart f'", [7, 3, 1, f"{{{N}1,0,2}}", f"{{1,{N}1,{N}1,1}}", "{1,1,1}", "{0}"],
     ["LOC MAX X=⁻1", "LOC MIN X=2", "NO EXTREMUM X=0"]),
    ("sign chart f''", [7, 3, 2, "{0,2}", f"{{1,{N}1,1}}", "{1,0}", "{0}"],
     ["INFL PT X=0", "NOT IN DOMAIN"]),
    ("formula sheet opens", [7, 5, 1], ["(F/G)'="]),
    ("quadratic", [7, 4, 1, 1, f"{N}2", f"{N}2"], ["X1=⁻.732051", "X2=2.732051"]),
    ("poly roots", [7, 4, 2, "X³-6X²+9X"], ["X=0", "X=3"]),
    ("solve f(x)=c", [7, 4, 3, "200X/(X+1)²", 20, 0, 20], ["X=.127017", "X=7.872983"]),
    ("decimal to exact", [7, 4, 4, ".4330127019"], ["=√(3/16)"]),
]

# marginal case defined explicitly (needs a revenue sub-menu choice)
CASES[[c[0] for c in CASES].index("marginal C,R,P at x=1000")] = (
    "marginal p=10-.001x, C=5000+2x at x=1000",
    [5, 1, 2, "10-.001X", "5000+2X", 1000],
    ["C(X)=7000", "MC=C'(X)~2", "R(X)=9000", "MR=R'(X)~8", "P(X)=R-C=2000",
     "AVG COST C/X=7"])


def run_case(inputs):
    calc = tisim.Calc(tisim.load_programs.cache, [str(x) for x in inputs])
    err = None
    try:
        calc.run("BCALC")
    except tisim.NeedInput:
        pass
    except tisim.TIError as e:
        err = str(e)
    text = "\n".join(calc.pages)
    flat = "".join(text.split("\n"))
    return calc, err, text, flat


def main():
    if "--onefile" in sys.argv:       # the merged single-program build
        import onefile
        tisim.load_programs.cache = {"BCALC": onefile.main()}
    else:
        tisim.load_programs.cache = tisim.load_programs()
    verbose = "-v" in sys.argv
    fails = 0
    peak = 0
    md = ["# Simulator test results", "",
          "Generated by `tests/test_review.py` (TI-BASIC simulator, not real hardware).", ""]
    for name, inputs, expect in CASES:
        calc, err, text, flat = run_case(inputs)
        nospace = flat.replace(" ", "")
        missing = [e for e in expect if e not in flat and e not in text
                   and e.replace(" ", "") not in nospace]
        ok = not err and not missing and not calc.warnings
        fails += not ok
        status = "PASS" if ok else "FAIL"
        peak = max(peak, calc.peak_mem)
        print(f"{status}  {name}" + (f"  missing={missing}" if missing else "")
              + (f"  ERROR={err}" if err else "")
              + (f"  warn={calc.warnings}" if calc.warnings else ""))
        if verbose:
            print(text)
        md += [f"## {name} — {status}", "",
               "Keys/inputs: `" + " → ".join(str(x) for x in inputs) + "`", "",
               f"Interpreter steps: {calc.steps}, function evaluations: {calc.yevals}, "
               f"peak variable memory ≈ {calc.peak_mem} bytes", "",
               "```", text.rstrip(), "```", ""]
    if "--onefile" not in sys.argv:
        (ROOT / "tests" / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n{len(CASES) - fails}/{len(CASES)} passed; peak variable memory {peak} bytes")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
