# BCALC — TI-84 Plus Business Calculus Exam 2 Solver (MATH 1309)

A menu-driven TI-BASIC program set for a **standard TI-84 Plus** (monochrome,
OS 2.x). You type the function from the problem, with your own numbers, and the
calculator works out the answer. It covers every problem type on the MATH 1309
Review for Test #2.

> **How this was tested.** I couldn't run it on a real TI-84 Plus or in a TI
> emulator, since an emulator needs a TI ROM I can't legally get. Instead, the
> programs were checked two ways:
>
> 1. A static checker (`tools/build.py`) compiles them with the official
>    TI-84 Plus token tables and rejects tokens that don't exist on the
>    TI-84 Plus. It also checks block structure, labels and screen widths.
> 2. A TI-BASIC simulator I wrote (`tools/tisim.py`) runs the *exact* token
>    stream in the `.8xp` files. It mimics 14-digit math, Real vs a+bi mode
>    errors, the 16×8 screen, menus and Input.
>
> All 63 simulator tests pass (`tests/RESULTS.md` shows every screen). Please
> still run the 2-minute check in §5 on your calculator before the exam.

---

## 1. Files

| File | What it is |
|---|---|
| `build/*.8xp` | **The programs to send to your calculator** (49 files) |
| **`dist/BCALC.8xp`** | **TI-84 Plus CE: the one file to upload** (everything merged into one program) |
| `dist/BCALC.8xg` (= `build/BCALC.8xg`) | Black & white TI-84 Plus: every core program in one group file |
| `build/BCEXTRA.8xg` | Optional extras (sign charts, quick tools, formula sheets, templates) as one group file |
| `build/*.txt` | Readable listing of each program, in case you ever need to type one in |
| `src/*.tib` | Commented source code |
| `tools/build.py` | Compiler and checker (`pip install tivars`, then `python3 tools/build.py`) |
| `tools/tisim.py`, `tests/test_review.py` | Simulator and test suite |
| `tests/RESULTS.md` | Every simulated screen for every test case |

**Core pack (keep in RAM, about 18.5 KB):** `BCALC` (the one you run),
`BCDERIV`, `BCPART`, `BCGRAPH`, `BCLIMIT`, `BCMARG`, `BCOPT`, `BCDIMIN`,
`BCCOBB`, and the 36 helper programs whose names start with **Z** (`ZA`…`ZZ`,
`Z0`…`Z9`). Never run the Z programs directly; BCALC calls them.

**Extras (about 4 KB, keep in Archive until needed):** `BCSIGN` (sign charts),
`BCTOOLS` (quick tools), `BCFORM` (formula sheets), `BCOPT2` (optimization
templates).

Why the split: a TI-84 Plus has about 24 KB of usable RAM. Programs must be in
RAM to run, and a running program can't unarchive another one. The core pack
plus about 3.5 KB of working space fits comfortably. All 49 programs at once
(22.5 KB plus working space) would not fit.

---

## 2. Install on a MacBook (TI Connect CE)

### TI-84 Plus CE (color screen) — ONE file: `dist/BCALC.8xp`

`dist/BCALC.8xp` is a single program containing **everything** (all modules
and all extras; ~29 KB, the CE has ~150 KB RAM). Built by
`tools/onefile.py`; it passes the same 63 simulator tests.

1. Install **TI Connect™ CE** (free, education.ti.com), open it, connect the
   calculator with its USB cable.
2. Drag **`BCALC.8xp`** onto the calculator and click Send (location RAM).
3. `PRGM` → **BCALC** → `ENTER` `ENTER`.

The CE's screen is bigger (26×10), so reports use only the top-left 16×8
part of it — that's expected.

### Original black & white TI-84 Plus

1. Install **TI Connect™ CE** (free, education.ti.com), open it, and connect
   the calculator with its USB cable.
2. **Free up RAM first.** On the calculator: `2nd` `+` (MEM) →
   `2:Mem Mgmt/Del…` → `1:All…`. Archive or delete what you don't need until
   free RAM (top of that screen) is about **23 KB**.
3. Drag **`BCALC.8xg`** onto the calculator in TI Connect CE and click Send.
   That's the only file you need.
4. TI Connect CE may unpack the group for you. Check `PRGM`: if you see
   **BCALC** (plus programs starting with **Z**), you're done.
   If not, the calculator stored it as a group. Unpack it once:
   `2nd` `+` → `8:Group…` → **`UNGROUP`** tab (right arrow) → choose
   **BCALC** → `ENTER` → if asked about duplicates choose `Overwrite All`.

The extras (sign charts, quick tools, formula sheets, optimization templates)
are **not** in this file. They're in `build/BCEXTRA.8xg`. After sending it,
ungroup it the same way and archive those four programs (they don't fit in
RAM together with the core).

### Run it

`PRGM` → choose **BCALC** → `ENTER` → `ENTER`. Every other program is called
from BCALC's menus. `BACK` returns to the previous menu. `MORE...` → `QUIT`
leaves cleanly.

### Using an extra (e.g. SIGN CHARTS)

`2nd` `+` → `2:Mem Mgmt/Del` → `7:Prgm` → move to `BCSIGN` → `ENTER` (the `*`
disappears, meaning it's in RAM now). If RAM is low, archive another extra
first. Picking an extra that is still archived gives `ERR:ARCHIVED`; choose
`1:Quit`, unarchive it, and run BCALC again.

---

## 3. Typing functions (important)

* Use `X,T,θ,n` for **X**. For two-variable functions **Y** is `ALPHA` `1`.
* Negative sign: use the **(−) key** (bottom row). The minus key gives
  `ERR:SYNTAX` at the start of an expression, e.g. `(−)X^4+6X²`.
* `ln(` is the LN key. `e^(` is `2nd` `LN`. `√(` is `2nd` `x²`.
* **Cube roots / odd roots of negatives:** use `MATH` `4:³√(`, e.g. `³√(X)²`
  for x^(2/3). The program evaluates in complex mode to detect "undefined",
  and there `X^(2/3)` counts as undefined for X < 0.
* Use parentheses generously: `200X/(X+1)²`, `(1-ln(X))/X²`.
* "TYPE F USING X" questions are answered with an expression. Lists (sign
  chart tool) are typed with braces: `{⁻1,0,2}`.
* The program writes your function into **Y1–Y5** and Y0, and uses lists
  L1–L6 plus a few named lists. Don't keep data you need there.

### Reading the output

* `~` means **numerical estimate** (numeric derivative, limit table,
  root by bisection). Values are rounded to 6 decimals (coordinates to 4).
* A line like `  =⁻200/27`, `X=√(3) Y=√(3/16)` or `  =√(1/2)` is an
  **exact-form hint**. The program found a fraction (denominator ≤ 1000) or
  the square root of one that matches the decimal. Use it to write exact
  answers, but treat it as "very likely", not proven.
* `-INF` / `INF` in intervals means "to the edge of the scanned window" in
  ANY F(X) mode, and true ±∞ in POLY/RATIONAL mode.
* `[ENTER] MORE` = press ENTER for the next page.

---

## 4. Menu guide: which option solves which review question

Main menu: `1 DERIVATIVES · 2 PARTIAL DERIVS · 3 GRAPH ANALYZER · 4 LIMITS/L'HOP · 5 MARGINAL/RATES · 6 OPTIMIZATION · 7 MORE...`
(`MORE...` = `1 DIM. RETURNS · 2 COBB-DOUGLAS · 3 SIGN CHARTS* · 4 QUICK TOOLS* · 5 FORMULA SHEETS* · 6 MAIN · 7 QUIT`; * = extra)

| Review item | Use | What you get |
|---|---|---|
| **Q1** product/quotient/chain derivatives | `1 DERIVATIVES → 2 CHECK MY F'` | Type f, then **your** derivative. It is compared with the true derivative at 10 x-values: `ALL MATCH!` or the x where it fails, with both values. Works for any form (unsimplified is fine). Also checks f''. |
| Q1 (value of f′ or f″ at a number) | `1 → 1 F,F',F'' AT X` | f(a), f′(a)~, f″(a)~ with exact hints |
| Q1/Q5 symbolic derivative of a polynomial or rational function | `1 → 3 EXACT POLY/RAT` | **Exact** f′ = NUM/DEN and f″ = NUM/DEN (coefficient algebra, not numeric) |
| **Q2** partial derivatives (all six) | `2 PARTIAL → 2 CHECK FX/FY` | Same answer checker for fx, fy, fxx, fyy, fxy at 8 (x,y) points |
| Q2 values at a point | `2 → 1 FX,FY AT (X,Y)` | f, fx, fy, fxx, fyy, fxy |
| **Q3** sales S(t)=200t/(t+1)² | `5 MARGINAL → 2 RATE OF CHANGE` | S(2)=44.444444 (=400/9), S′(2)~−7.407407 (=−200/27), "F DECREASING AT RATE 7.407407" |
| **Q4 / Q8 (14.2 #89, 90)** Cobb-Douglas | `7 MORE → 2 COBB-DOUGLAS` | P, MPL, MPK (exact formulas), symbolic PL and PK, returns to scale, MPL/MPK, % change, ΔP approx vs exact |
| Q4 other applied partials | `2 → 1` (enter the business function in X,Y) | partial values plus interpretation |
| **Q5a, Q5d** rational graphs | `3 GRAPH → 1 POLY/RATIONAL`, N(X) and D(X) | VA with side behavior, holes, intercepts, critical points as (x,y) with max/min, inc/dec intervals, inflection points vs. "not inflection", concavity, HA/slant |
| **Q5b, Q5c** polynomial graphs | `3 → 1`, D(X)=1 | same, plus end behavior |
| Graphs with ln, e^, roots | `3 → 2 ANY F(X)` + window | numeric version of the same report |
| **Q6** limits / L'Hôpital | `4 LIMITS → 3 L'HOPITAL N/D` | limits of N and D, the form (0/0, ∞/∞, c/0…), whether L'Hôpital applies, lim N/D, and lim N′/D′ as a cross-check; left/right results when DNE |
| Q6 single-function limit | `4 → 1` (x→a, choose side) or `4 → 2` (x→±∞) | finite / +INF / −INF / DNE / UNDEFINED / UNCLEAR plus the value table |
| **Q7 (11.2 #44, 46)** graphs from sign charts | `7 → 3 SIGN CHARTS*` | Enter partition numbers, interval signs and domain flags: get inc/dec or concavity intervals and max/min/IP (with coordinates if you give f values) |
| **Q8 (11.2 #87, 92, 93)** diminishing returns | `7 → 1 DIM. RETURNS` | f″ sign changes in [a,b]; reports **POINT OF DIMINISHING RETURNS only where f″ goes + → −**, the point (x, f(x)), the max rate f′, and where the rate rises/falls |
| **Q9 (11.6 #20, 26)** optimization | `6 OPTIMIZATION` | `1` absolute max/min on [a,b] (endpoints and critical points table, 2nd-derivative test); `2` max profit or revenue from R(x) or price p(x) and C(x) (shows R, MR, price, C, MC, whole-unit check); `3` min average cost; `4 TEMPLATES*` price/rent steps, open box, inventory EOQ |
| Marginal cost/revenue/profit | `5 → 1 C,R,P,AVG COST` | C, MC, exact next-unit cost C(x+1)−C(x), R, MR, P, MP, average cost and its derivative |
| Quadratic, polynomial roots, solve f(x)=c, decimal→exact | `7 → 4 QUICK TOOLS*` | |
| Rules / formulas | `7 → 5 FORMULA SHEETS*` | derivative rules, log rules, L'Hôpital, graphing steps, business formulas, partials/Cobb-Douglas |

### Worked examples (all from the simulator, `tests/RESULTS.md`)

**Q3.** `5 → 2`, F(X)=`200X/(X+1)²`, X=`2` →
```
F(X)=44.444444
  =400/9
F'(X)~⁻7.407407
  =⁻200/27
F DECREASING AT
RATE 7.407407
```

**Q5d.** `3 → 1`, N=`X+1`, D=`X²-4` →
```
VERT ASYMP X=⁻2      L:-INF  R:+INF
VERT ASYMP X=2       L:-INF  R:+INF
Y-INT (0,⁻.25)   X-INT (⁻1,0)
=CRITICAL PTS=  NONE FOUND
DECREASING ON: (-INF,⁻2) (⁻2,2) (2,INF)
INFL PT (⁻.3622,⁻.1649)  (F''=0)
CONCAVE UP ON: (⁻2,⁻.3622) (2,INF)
CONCAVE DOWN ON: (-INF,⁻2) (⁻.3622,2)
HA: Y=0
```

**Q6d.** `4 → 3`, N=`X²`, D=`ln(X)`, `A NUMBER`, A=`1`, `BOTH SIDES` →
`LIM N~1`, `LIM D~0`, `NOT 0/0,INF/INF: NO L'HOPITAL`, `C/0: +-INF OR DNE`,
`LIM N/D DNE`, `RIGHT:=+INF`, `LEFT:=-INF`.

**Q2b, answer key version.** `2 → 2`, F=`(3X^5Y²+2X-5Y)^4`, `FY`,
ANS=`4(3X^5Y²+2X-5Y)³(6X^5Y)` → `8 MISMATCH(ES)`. With `(6X^5Y-5)` →
`ALL MATCH!`.

---

## 5. Verify the installation (2 minutes)

Run each line; the expected result is on the right.

1. `1 → 1`, F(X)=`X³`, X=`2` → `F(X)=8`, `F'(X)~12`, `F''(X)~12`.
2. `1 → 2`, F=`ln(X)/X`, `MY F'(X)`, ANS=`(1-ln(X))/X²` → `ALL MATCH!`.
3. `3 → 1`, N=`X³-6X²+9X`, D=`1` → `LOC MAX (1,4)`, `LOC MIN (3,0)`, `INFL PT (2,2)`.
4. `4 → 3`, N=`e^(X)-1`, D=`X`, A=`0`, both sides → `L'HOPITAL OK`, `LIM N/D~1`.
5. `5 → 2`, F=`200X/(X+1)²`, X=`2` → `F(X)=44.444444`.

If (1) shows the numbers but they look odd, check that MODE is Float and Func
(BCALC sets this itself on start).

**Timing:** I couldn't measure on hardware. Judging from the operation counts
in the simulator, expect POLY/RATIONAL analysis and limits to take about
5–30 s, and ANY F(X) graph analysis 30–60 s. A moving bar in the top right
corner means it's working; `ON` aborts.

---

## 6. What the TI-84 Plus can and cannot do here (honest limits)

The TI-84 Plus has **no computer algebra system**. Here is what the program
does about that:

| Capability | Exact / symbolic? | How |
|---|---|---|
| Derivative of polynomials and rational functions | **Exact symbolic** (coefficients) | Option `EXACT POLY/RAT`. Coefficients come from exact interpolation; f′=(N′D−ND′)/D², f″=(P′D−2PD′)/D³ |
| Derivative of anything else (ln, e^, roots, products…) | **Numeric only** (~ marked, ~10 digits) | 5-point central differences. Use `CHECK MY F'`: you do the symbolic work, the calculator verifies it |
| Partial derivatives | Numeric (~); Cobb-Douglas exact formulas | 5-point stencils in x and y |
| Critical points, inflection points (poly/rational) | Roots by a guaranteed method (bisection between roots of the next derivative), about 12 digits | All real roots found, double roots too |
| Critical points, inflection points (ANY F) | Numeric scan of a window you choose (64 cells) plus bisection, about 6–10 digits | Can miss features narrower than one cell (window width/64), and anything outside the window |
| Asymptotes | Poly/rational exact (degree rules, slant by division, holes detected); ANY F numeric | |
| Limits | Numeric tables (x = a ± 10⁻ᵏ, x = 10ᵏ) with classification | Clear finite/±∞/DNE/undefined/unclear labels; "UNCLEAR" is shown rather than a guess |
| L'Hôpital | Detects the form from the limits of N and D | Never says "L'Hôpital OK" for c/0, 0/∞, etc. |
| Exact forms (fractions, √) | Hints only | Continued fractions; denominator ≤1000 within 1E-9, or ≤100 within 1E-7 |

Known limitations and workarounds:

* **ANY F(X) needs a sensible window.** Use the domain from the problem, or
  −10…10. Critical points outside the window are not seen. Re-run with a
  wider window if the graph clearly does more.
* **Removable discontinuities (holes) are only detected in POLY/RATIONAL
  mode.** In ANY F mode, a hole exactly at x=0 can cause `ERR:DIVIDE BY 0`
  when the y-intercept is computed. Use POLY/RATIONAL for rational functions.
* **Very fast-growing functions** such as e^(X²) can give `ERR:OVERFLOW`
  during end-behavior or limit tables. The limit is then +∞ for practical
  purposes.
* An f′ or f″ value at a point where f is undefined gives `ERR:DIVIDE BY 0`
  or the message "F UNDEFINED HERE". Choose `1:Quit` and pick a different x.
* Numeric derivatives near the edge of the domain (within 0.002) are
  reported as undefined (e.g. f′ of √x at x=0.001).
* x^(p/q) with X<0: type `³√(X)` etc. (see §3).
* The program can't write the symbolic derivative of ln/e^/root expressions.
  Use `CHECK MY F'` instead; it reliably catches sign errors, missing chain
  factors and wrong rules.

**Errors and fixes**

| Message | Meaning / fix |
|---|---|
| `ERR:SYNTAX` right after typing a function | Used the minus key instead of (−), unbalanced parentheses, or `2(` typed oddly. Quit and retype |
| `ERR:ARCHIVED` | An extra module is still archived (see §2) |
| `ERR:MEMORY` | Not enough RAM: archive the extras and other programs, or delete lists |
| `ERR:UNDEFINED` | A helper Z-program is missing. Re-send the core pack |
| `ERR:DIVIDE BY 0` / `ERR:DOMAIN` | f is undefined at a point the program had to evaluate (see above) |
| `NOT A POLYNOMIAL` | POLY/RATIONAL mode only takes polynomials for N and D; use ANY F(X) |
| `TOO FEW VALID X` (answer checker) | Your function's domain excludes most test x-values (they are 0.7–5.3 and some negatives) |
| Wrong-looking "LAST F" offered | Choose 0 to type a new function |

---

## 7. Review sheet analysis and coverage checklist

### Topics on the review
1. Product, quotient, chain rules (with ln, e^, √, powers)
2. Partial derivatives (product/quotient/chain, ln, e^, roots)
3. Business applications of partial derivatives, Cobb-Douglas
4. Graphing with f′ and f″: critical points, inc/dec, concavity, inflection,
   intercepts, asymptotes
5. L'Hôpital's rule (0/0, ∞/∞) and limits (±∞, one-sided, DNE)
6. Marginal analysis and optimization
7. Second derivative applications: points of diminishing returns

### Coverage

| Question | Status | Notes |
|---|---|---|
| Q1 a–i | **Full check** | `CHECK MY F'` verifies any written answer; f′(a) numeric |
| Q2 a–f | **Full check** | `CHECK FX/FY` |
| Q3 a, b | **Full** | Rate of change module |
| Q4 (14.2 #89–90) | **Full** for Cobb-Douglas and any f(x,y) | I don't have the textbook text; the module handles the general form |
| Q5 a–d | **Full** | Exact poly/rational analyzer |
| Q6 a–i | **Full** | L'Hôpital module classifies the form and finds the limit |
| Q7 (11.2 #44, 46) | **Full** given the chart | Sign chart tool |
| Q8 (11.2 #87, 92, 93) | **Full** | Diminishing returns module |
| Q9 (11.6 #20, 26) | **Full** once you set up f(x) | Profit/revenue/avg-cost optimizers plus templates (price steps / rent, open box, EOQ). You still write the function from the word problem |
| Writing symbolic derivatives of non-polynomials | **Partial** | The calculator verifies your answer; it can't write it |
| Sketching the graph | **Instructions/points** | The report gives all labeled points; plot them by hand (or use the TI's own GRAPH with Y1, which the program leaves set to your f) |

### Independent check of the answer key (worth knowing!)

I recomputed every printed answer:

* **Q1d is printed with the wrong sign.** d/dx[(x²−4)ln x] = (x²−4)/x **+**
  2x ln x. The key shows "− 2x ln x". The simulator's checker flags the key
  version as a mismatch.
* **Q2b is missing a term.** ∂/∂y (3x⁵y²+2x−5y)⁴ = 4(3x⁵y²+2x−5y)³(6x⁵y **− 5**).
* Q1c (blank in key): (5 + 1/(2√x))e^{4x} + 4(5x+√x)e^{4x}.
* Q6c = +∞, Q6d = DNE (left −∞, right +∞), Q6f = +∞ (these were blank).
* Everything else matches: Q1a, b, e–i; Q2a, c–f; Q3: S(2)=400/9≈44.44,
  S′(2)=−200/27≈−7.41 (decreasing); Q6a=1, b=1, e=0, g=+∞, h=0, i=+∞.
* Q5 (no key given), confirmed by the program:
  * a) max (1, ½), min (−1, −½), IP at 0 and ±√3 (y=±√3/4), HA y=0.
  * b) max (±√3, 9), min (0,0), IP (±1, 5), x-ints 0, ±√6.
  * c) max (1,4), min (3,0), IP (2,2).
  * d) VA x=±2, HA y=0, always decreasing, IP ≈ (−0.3622, −0.1649) (real root
    of x³+3x²+12x+4), intercepts (−1,0), (0,−¼).

---

## 8. Rebuilding / testing (optional, on a computer)

```
pip install tivars
python3 tools/build.py        # compile + lint -> build/
python3 tests/test_review.py  # 63 simulated exam scenarios -> tests/RESULTS.md
python3 tools/session.py 5 2 "200X/(X+1)²" 2   # try any key sequence
```
