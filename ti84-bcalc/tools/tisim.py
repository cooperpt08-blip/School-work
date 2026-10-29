#!/usr/bin/env python3
"""A small TI-84 Plus TI-BASIC simulator used to test the BCALC programs.

It executes exactly the token stream that build.py writes into the .8xp
files (closing parentheses/quotes already stripped), and models the parts
of the calculator the programs rely on:

  * 14-significant-digit arithmetic, TI error conditions (DIVIDE BY 0,
    DOMAIN, NONREAL ANS in Real mode, OVERFLOW, DATA TYPE, INVALID DIM)
  * Real / a+bi modes (sqrt, ln, powers of negatives behave per mode)
  * real vars, lists (L1-L6 and named), strings, Y-vars with Y1(x) calls
  * If/Then/Else/End, For, While, Repeat, Lbl/Goto, Menu(, prgm calls
  * home screen 16x8: Disp, Output(, ClrHome, Pause, Input, scrolling
  * LinReg(ax+b) + Equ>String (number -> string trick), String>Equ

It is NOT an emulator of the real calculator ROM: timings are not modelled
and float behaviour is approximated with Python floats rounded to 14
significant digits.  Its purpose is to catch logic, syntax and numeric
mistakes before the programs ever reach a calculator.
"""
import cmath
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build  # noqa: E402


class TIError(Exception):
    pass


class NeedInput(Exception):
    pass


DIGITS = set("0123456789")
LETTERS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZθ")
SUBS = "₀₁₂₃₄₅₆₇₈₉"
LISTS = {f"L{SUBS[i]}" for i in range(1, 7)}
YVARS = {f"Y{c}" for c in SUBS}
STRS = {f"Str{i}" for i in range(10)}
WINDOW = {"Xmin", "Xmax", "Ymin", "Ymax", "Xscl", "Yscl"}


# ---------------------------------------------------------------- numbers
def r14(x):
    if isinstance(x, complex):
        if x.imag == 0:
            return r14(x.real)
        return complex(r14(x.real), r14(x.imag))
    if x == 0 or math.isinf(x) or math.isnan(x):
        if math.isinf(x) or math.isnan(x):
            raise TIError("OVERFLOW")
        return 0.0
    e = math.floor(math.log10(abs(x)))
    v = round(x, 13 - e)
    if abs(v) >= 1e100:
        raise TIError("OVERFLOW")
    if abs(v) < 1e-99:
        return 0.0
    return float(v)


def fmt(x):
    """TI home-screen number format (Float mode, 10 significant digits)."""
    if isinstance(x, complex):
        a, b = fmt(x.real), fmt(abs(x.imag))
        return f"{a}{'-' if x.imag < 0 else '+'}{b}i"
    if x == 0:
        return "0"
    neg = x < 0
    a = abs(x)
    if 1e-3 <= a < 1e10:
        s = f"{a:.10g}"
        if "e" in s:  # rounding pushed it to 1e10
            s = f"{a:.10e}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        if s.startswith("0."):
            s = s[1:]
        out = s
    else:
        m, e = f"{a:.9e}".split("e")
        m = m.rstrip("0").rstrip(".")
        e = int(e)
        out = f"{m}ᴇ{'⁻' if e < 0 else ''}{abs(e)}"
    return ("⁻" if neg else "") + out


def is_list(v):
    return isinstance(v, list)


def is_str(v):
    return isinstance(v, tuple)


# ------------------------------------------------------------------ parser
FUNCS1 = {"abs(", "int(", "iPart(", "fPart(", "√(", "³√(", "ln(", "log(",
          "𝑒^(", "real(", "imag(", "not(", "sum(", "dim(", "cumSum(",
          "ΔList(", "length(", "expr(", "round(", "max(", "min(", "sub(",
          "inString(", "augment(", "seq(", "remainder("}
PREFIX_START = DIGITS | {".", "(", "{", '"', "π", "𝑒", "Ans", "ʟ"} | LETTERS \
    | LISTS | YVARS | STRS | FUNCS1


class Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else None

    def take(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def close(self, tok):
        """consume a closing token if present (TI allows omitting it)"""
        if self.peek() == tok:
            self.i += 1

    def parse(self):
        node = self.expr(0)
        if self.i != len(self.t):
            raise TIError(f"SYNTAX at {self.t[self.i:]}")
        return node

    BIN = {" or ": 10, " xor ": 10, " and ": 20, "=": 30, "≠": 30, "<": 30,
           ">": 30, "≤": 30, "≥": 30, "+": 40, "-": 40, "*": 50, "/": 50}

    def expr(self, minp):
        left = self.unary()
        while True:
            tok = self.peek()
            if tok in self.BIN and self.BIN[tok] >= minp:
                p = self.BIN[tok]
                self.take()
                right = self.expr(p + 1)
                left = ("bin", tok, left, right)
            elif tok in PREFIX_START and 50 >= minp:
                right = self.expr(51)          # implied multiplication
                left = ("bin", "*", left, right)
            else:
                return left

    def unary(self):
        if self.peek() == "⁻":
            self.take()
            return ("neg", self.expr_pow_level())
        return self.expr_pow_level()

    def expr_pow_level(self):
        left = self.postfix(self.primary())
        while self.peek() == "^":
            self.take()
            if self.peek() == "⁻":
                self.take()
                right = ("neg", self.postfix(self.primary()))
            else:
                right = self.postfix(self.primary())
            left = ("bin", "^", left, right)
        return left

    def postfix(self, node):
        while self.peek() in ("²", "³", "⁻¹", "!"):
            node = ("post", self.take(), node)
        return node

    def args(self):
        out = [self.expr(0)]
        while self.peek() == ",":
            self.take()
            out.append(self.expr(0))
        self.close(")")
        return out

    def number(self):
        s = ""
        while self.peek() is not None and (self.peek() in DIGITS or self.peek() == "."):
            s += self.take()
        if self.peek() == "ᴇ":
            self.take()
            e = ""
            if self.peek() == "⁻":
                self.take()
                e = "-"
            while self.peek() is not None and self.peek() in DIGITS:
                e += self.take()
            s = (s or "1") + "e" + e
        return ("num", float(s))

    def primary(self):
        tok = self.peek()
        if tok is None:
            raise TIError("SYNTAX: unexpected end")
        if tok in DIGITS or tok == "." or tok == "ᴇ":
            return self.number()
        self.take()
        if tok == "(":
            node = self.expr(0)
            self.close(")")
            return node
        if tok == "{":
            items = [self.expr(0)]
            while self.peek() == ",":
                self.take()
                items.append(self.expr(0))
            self.close("}")
            return ("listlit", items)
        if tok == '"':
            s = []
            while self.peek() is not None and self.peek() != '"':
                s.append(self.take())
            self.close('"')
            return ("str", tuple(s))
        if tok == "π":
            return ("num", math.pi)
        if tok == "𝑒":
            return ("num", math.e)
        if tok == "Ans":
            return ("var", "Ans")
        if tok in LETTERS:
            return ("var", tok)
        if tok in STRS:
            return ("strvar", tok)
        if tok in LISTS or tok == "ʟ":
            name = tok
            if tok == "ʟ":
                name = "ʟ"
                while (self.peek() is not None and len(name) < 6
                       and (self.peek() in LETTERS or self.peek() in DIGITS)):
                    name += self.take()
            if self.peek() == "(":
                self.take()
                idx = self.expr(0)
                self.close(")")
                return ("lidx", name, idx)
            return ("list", name)
        if tok in YVARS:
            if self.peek() == "(":
                self.take()
                arg = self.expr(0)
                self.close(")")
                return ("ycall", tok, arg)
            return ("yvar", tok)
        if tok in FUNCS1:
            return ("call", tok, self.args())
        raise TIError(f"SYNTAX: token {tok!r}")


# --------------------------------------------------------------- interpreter
class Calc:
    def __init__(self, programs, inputs=(), max_steps=5_000_000, trace=False):
        self.programs = programs          # name -> list of token lines
        self.inputs = list(inputs)
        self.vars = {}
        self.lists = {}
        self.strs = {}
        self.yvars = {}
        self.complex_mode = False
        self.screen = [[" "] * 16 for _ in range(8)]
        self.cur_row = 0                  # next Disp row (0-based)
        self.pages = []                   # screen snapshots at Pause
        self.log = []                     # everything shown, in order
        self.steps = 0
        self.yevals = 0
        self.max_steps = max_steps
        self.warnings = []
        self.cache = {}
        self.trace = trace
        self.peak_mem = 0
        self.window = {}
        self.drawing = []                 # graph-screen commands, in order

    def mem_used(self):
        """approximate bytes of variables (data only, no VAT entries)"""
        b = 9 * len(self.vars)
        for v in self.lists.values():
            b += 2 + sum(18 if isinstance(x, complex) else 9 for x in v)
        for v in list(self.strs.values()) + list(self.yvars.values()):
            b += 2 + len(v)
        return b

    # ---- screen
    def snapshot(self):
        return "\n".join("".join(r) for r in self.screen)

    def clr(self):
        self.screen = [[" "] * 16 for _ in range(8)]
        self.cur_row = 0

    def put(self, row, col, chars):
        r, c = row, col
        for ch in chars:
            if r >= 8:
                break
            self.screen[r][c] = ch
            c += 1
            if c >= 16:
                c, r = 0, r + 1

    def scroll(self):
        self.screen = self.screen[1:] + [[" "] * 16]
        self.cur_row = 7

    def disp_line(self, chars, right=False):
        if self.cur_row >= 8:
            self.scroll()
        chars = list(chars)
        if len(chars) > 16:
            chars = chars[:15] + ["…"]
        line = [" "] * 16
        start = 16 - len(chars) if right else 0
        for k, ch in enumerate(chars):
            line[start + k] = ch
        self.screen[self.cur_row] = line
        self.log.append("".join(chars))
        self.cur_row += 1

    @staticmethod
    def chars(tokens):
        out = []
        for t in tokens:
            out.extend(list(t if t != "𝑒^(" else "e^("))
        return out

    # ---- numbers
    def num(self, v):
        if is_list(v) or is_str(v):
            raise TIError("DATA TYPE")
        return v

    def real(self, v):
        v = self.num(v)
        if isinstance(v, complex):
            if v.imag != 0:
                raise TIError("DATA TYPE")
            return v.real
        return v

    def fix(self, z):
        if isinstance(z, complex):
            if z.imag == 0:
                return r14(z.real)
            if not self.complex_mode:
                raise TIError("NONREAL ANS")
            return r14(z)
        return r14(z)

    def elementwise(self, f, *vals):
        lens = [len(v) for v in vals if is_list(v)]
        if not lens:
            return f(*vals)
        if len(set(lens)) > 1:
            raise TIError("DIM MISMATCH")
        n = lens[0]
        return [f(*[(v[i] if is_list(v) else v) for v in vals]) for i in range(n)]

    def binop(self, op, a, b):
        if op == "+" and is_str(a) and is_str(b):
            return a + b
        if is_str(a) and is_str(b) and op in ("=", "≠"):
            return float((a == b) == (op == "="))
        if is_str(a) or is_str(b):
            raise TIError("DATA TYPE")
        return self.elementwise(lambda x, y: self.scalar_bin(op, x, y), a, b)

    def scalar_bin(self, op, x, y):
        if op == "+":
            return self.fix(x + y)
        if op == "-":
            return self.fix(x - y)
        if op == "*":
            return self.fix(x * y)
        if op == "/":
            if y == 0:
                raise TIError("DIVIDE BY 0")
            return self.fix(x / y)
        if op == "^":
            return self.power(x, y)
        if op in ("=", "≠"):
            eq = x == y
            return float(eq if op == "=" else not eq)
        if op in ("<", ">", "≤", "≥"):
            x, y = self.real(x), self.real(y)
            return float({"<": x < y, ">": x > y, "≤": x <= y, "≥": x >= y}[op])
        if op == " and ":
            return float(x != 0 and y != 0)
        if op == " or ":
            return float(x != 0 or y != 0)
        if op == " xor ":
            return float((x != 0) != (y != 0))
        raise TIError("SYNTAX op " + op)

    def power(self, x, y):
        if x == 0 and y == 0:
            raise TIError("DOMAIN")
        if x == 0:
            if self.real(y) < 0:
                raise TIError("DIVIDE BY 0")
            return 0.0
        if isinstance(x, complex) or isinstance(y, complex):
            return self.fix(complex(x) ** complex(y))
        if x < 0 and y != int(y):
            if self.complex_mode:
                return self.fix(complex(x) ** y)
            from fractions import Fraction
            fr = Fraction(y).limit_denominator(1000)
            if abs(float(fr) - y) < 1e-12 and fr.denominator % 2 == 1:
                mag = abs(x) ** y
                return self.fix(-mag if fr.numerator % 2 else mag)
            raise TIError("NONREAL ANS")
        try:
            return self.fix(x ** y)
        except OverflowError:
            raise TIError("OVERFLOW")

    # ---- evaluation
    def ast(self, toks):
        key = tuple(toks)
        if key not in self.cache:
            self.cache[key] = Parser(list(toks)).parse()
        return self.cache[key]

    def ev(self, n):
        k = n[0]
        if k == "num":
            return n[1]
        if k == "var":
            return self.vars.get(n[1], 0.0)
        if k == "str":
            return n[1]
        if k == "strvar":
            if n[1] not in self.strs:
                raise TIError("UNDEFINED " + n[1])
            return self.strs[n[1]]
        if k == "listlit":
            out = []
            for item in n[1]:
                v = self.ev(item)
                if is_list(v) or is_str(v):
                    raise TIError("DATA TYPE")
                out.append(v)
            return out
        if k == "list":
            if n[1] not in self.lists:
                raise TIError("UNDEFINED " + n[1])
            return list(self.lists[n[1]])
        if k == "lidx":
            lst = self.lists.get(n[1])
            if lst is None:
                raise TIError("UNDEFINED " + n[1])
            i = self.real(self.ev(n[2]))
            if i != int(i) or not 1 <= i <= len(lst):
                raise TIError(f"INVALID DIM {n[1]}({i}) dim={len(lst)}")
            return lst[int(i) - 1]
        if k == "yvar":
            return self.eval_y(n[1])
        if k == "ycall":
            arg = self.ev(n[2])
            if is_list(arg):
                return [self.ycall(n[1], a) for a in arg]
            return self.ycall(n[1], arg)
        if k == "neg":
            return self.elementwise(lambda x: self.fix(-x), self.ev(n[1]))
        if k == "post":
            v = self.ev(n[2])
            op = n[1]
            if op == "²":
                return self.elementwise(lambda x: self.fix(x * x), v)
            if op == "³":
                return self.elementwise(lambda x: self.fix(x * x * x), v)
            if op == "⁻¹":
                return self.elementwise(lambda x: self.scalar_bin("/", 1.0, x), v)
            if op == "!":
                def fact(x):
                    x = self.real(x)
                    if x != int(x) or x < 0 or x > 69:
                        raise TIError("DOMAIN")
                    return float(math.factorial(int(x)))
                return self.elementwise(fact, v)
        if k == "bin":
            op = n[1]
            a = self.ev(n[2])
            b = self.ev(n[3])
            return self.binop(op, a, b)
        if k == "call":
            return self.call(n[1], n[2])
        raise TIError("eval " + k)

    def eval_y(self, name):
        if name not in self.yvars:
            raise TIError("UNDEFINED " + name)
        self.yevals += 1
        return self.ev(self.ast(self.yvars[name]))

    def ycall(self, name, arg):
        old = self.vars.get("X", 0.0)
        self.vars["X"] = arg
        try:
            return self.eval_y(name)
        finally:
            self.vars["X"] = old

    def call(self, f, args):
        if f == "seq(":
            expr, var = args[0], args[1]
            if var[0] != "var":
                raise TIError("SYNTAX seq var")
            a = self.real(self.ev(args[2]))
            b = self.real(self.ev(args[3]))
            st = self.real(self.ev(args[4])) if len(args) > 4 else 1.0
            old = self.vars.get(var[1], 0.0)
            out, k = [], 0
            while True:
                x = r14(a + k * st)
                if (st > 0 and x > b) or (st < 0 and x < b):
                    break
                self.vars[var[1]] = x
                v = self.ev(expr)
                if is_list(v) or is_str(v):
                    raise TIError("DATA TYPE")
                out.append(v)
                k += 1
                if k > 999:
                    raise TIError("INVALID DIM seq")
            self.vars[var[1]] = old
            if not out:
                raise TIError("INVALID DIM empty seq")
            return out
        vals = [self.ev(a) for a in args]
        v = vals[0]
        ew = self.elementwise
        if f == "abs(":
            return ew(lambda x: r14(abs(x)), v)
        if f == "int(":
            return ew(lambda x: float(math.floor(self.real(x))), v)
        if f == "iPart(":
            return ew(lambda x: float(math.trunc(self.real(x))), v)
        if f == "fPart(":
            return ew(lambda x: r14(self.real(x) - math.trunc(self.real(x))), v)
        if f == "round(":
            d = int(self.real(vals[1])) if len(vals) > 1 else 9
            def rnd(x):
                x = self.real(x)
                q = abs(x) * 10 ** d
                return r14(math.copysign(math.floor(q + 0.5) / 10 ** d, x))
            return ew(rnd, v)
        if f == "√(":
            def sq(x):
                if isinstance(x, complex) or x < 0:
                    if not self.complex_mode:
                        raise TIError("NONREAL ANS")
                    return self.fix(cmath.sqrt(x))
                return r14(math.sqrt(x))
            return ew(sq, v)
        if f == "³√(":
            def cb(x):
                if isinstance(x, complex):
                    return self.fix(x ** (1 / 3))
                return r14(math.copysign(abs(x) ** (1 / 3), x))
            return ew(cb, v)
        if f in ("ln(", "log(") :
            def lg(x):
                if x == 0:
                    raise TIError("DOMAIN")
                if isinstance(x, complex) or x < 0:
                    if not self.complex_mode:
                        raise TIError("NONREAL ANS")
                    z = cmath.log(x)
                    return self.fix(z if f == "ln(" else z / math.log(10))
                return r14(math.log(x) if f == "ln(" else math.log10(x))
            return ew(lg, v)
        if f == "𝑒^(":
            def ex(x):
                try:
                    return self.fix(cmath.exp(x) if isinstance(x, complex) else math.exp(x))
                except OverflowError:
                    raise TIError("OVERFLOW")
            return ew(ex, v)
        if f == "real(":
            return ew(lambda x: float(x.real) if isinstance(x, complex) else x, v)
        if f == "imag(":
            return ew(lambda x: float(x.imag) if isinstance(x, complex) else 0.0, v)
        if f == "not(":
            return ew(lambda x: float(x == 0), v)
        if f == "sum(":
            s = 0.0
            for x in v:
                s = self.fix(s + x)
            return s
        if f == "dim(":
            if not is_list(v):
                raise TIError("DATA TYPE dim")
            return float(len(v))
        if f == "cumSum(":
            out, s = [], 0.0
            for x in v:
                s = self.fix(s + x)
                out.append(s)
            return out
        if f == "ΔList(":
            if len(v) < 2:
                raise TIError("INVALID DIM ΔList")
            return [self.fix(v[i + 1] - v[i]) for i in range(len(v) - 1)]
        if f in ("max(", "min("):
            pick = max if f == "max(" else min
            if len(vals) == 1:
                return pick(self.real(x) for x in v)
            return ew(lambda x, y: pick(self.real(x), self.real(y)), vals[0], vals[1])
        if f == "augment(":
            if is_list(vals[0]) and is_list(vals[1]):
                return vals[0] + vals[1]
            raise TIError("DATA TYPE augment")
        if f == "length(":
            return float(len(v))
        if f == "sub(":
            s, a, n = v, int(self.real(vals[1])), int(self.real(vals[2]))
            if a < 1 or n < 1 or a + n - 1 > len(s):
                raise TIError("INVALID DIM sub(")
            return s[a - 1:a - 1 + n]
        if f == "inString(":
            s, t = vals[0], vals[1]
            start = int(self.real(vals[2])) if len(vals) > 2 else 1
            for i in range(start - 1, len(s) - len(t) + 1):
                if s[i:i + len(t)] == t:
                    return float(i + 1)
            return 0.0
        if f == "expr(":
            return self.ev(self.ast(v))
        raise TIError("unknown function " + f)

    # ---- storing
    def store(self, target, val):
        if len(target) == 1 and target[0] in WINDOW:
            self.window[target[0]] = self.real(val)
            return
        if len(target) == 1 and target[0] in LETTERS:
            if is_list(val) or is_str(val):
                raise TIError("DATA TYPE store")
            self.vars[target[0]] = val
            return
        if len(target) == 1 and target[0] in STRS:
            if not is_str(val):
                raise TIError("DATA TYPE store str")
            self.strs[target[0]] = val
            return
        raise TIError(f"bad store target {target}")

    def store_tokens(self, target, val):
        self._store_tokens(target, val)
        if is_list(val) or target[0] == "dim(":
            self.peak_mem = max(self.peak_mem, self.mem_used())

    def _store_tokens(self, target, val):
        t = list(target)
        if t[0] == "dim(":
            name = self.list_name(t[1:])
            n = int(self.real(val))
            lst = self.lists.get(name, [])
            self.lists[name] = (lst + [0.0] * n)[:n]
            return
        if t[0] in LISTS or t[0] == "ʟ":
            p = Parser(t)
            node = p.primary()
            if p.i != len(t):
                raise TIError(f"SYNTAX store {t}")
            if node[0] == "list":
                if not is_list(val):
                    raise TIError("DATA TYPE store list")
                self.lists[node[1]] = list(val)
                return
            if node[0] == "lidx":
                if is_list(val) or is_str(val):
                    raise TIError("DATA TYPE")
                i = int(self.real(self.ev(node[2])))
                lst = self.lists.setdefault(node[1], [])
                if i == len(lst) + 1:
                    lst.append(val)
                elif 1 <= i <= len(lst):
                    lst[i - 1] = val
                else:
                    raise TIError(f"INVALID DIM store {node[1]}({i})")
                return
        self.store(t, val)

    @staticmethod
    def list_name(t):
        if t[0] == "ʟ":
            return "ʟ" + "".join(x for x in t[1:] if x not in (")",))
        return t[0]

    # ---- program execution
    def run(self, name):
        self.frames = [[name, 0, []]]
        while self.frames:
            frame = self.frames[-1]
            prog = self.programs[frame[0]]
            if frame[1] >= len(prog):
                self.frames.pop()
                continue
            line = prog[frame[1]]
            frame[1] += 1
            self.steps += 1
            if self.steps > self.max_steps:
                raise TIError("step limit (infinite loop?)")
            try:
                self.exec_line(frame, line)
            except TIError as e:
                raise TIError(f"ERR:{e} in {frame[0]} line {frame[1]}: {''.join(line)}")
        self.disp_line(list("Done"), right=True)

    def find_label(self, prog, lab):
        for i, line in enumerate(self.programs[prog]):
            if line and line[0] == "Lbl " and "".join(line[1:]) == lab:
                return i + 1
        raise TIError("LABEL " + lab)

    def skip_block(self, frame, stop_at_else):
        """Skip forward past the matching End (or to a matching Else)."""
        prog = self.programs[frame[0]]
        depth = 0
        prev_if = False
        while frame[1] < len(prog):
            line = prog[frame[1]]
            frame[1] += 1
            head = line[0] if line else ""
            if head in ("For(", "While ", "Repeat ") or (head == "Then" and prev_if):
                depth += 1
            elif head == "End":
                if depth == 0:
                    return "End"
                depth -= 1
            elif head == "Else" and depth == 0 and stop_at_else:
                return "Else"
            prev_if = head == "If "
        raise TIError("missing End")

    def cond(self, toks):
        v = self.ev(self.ast(toks))
        if is_list(v) or is_str(v):
            raise TIError("DATA TYPE cond")
        return self.real(v) != 0

    def exec_line(self, frame, line):
        if not line:
            return
        head = line[0]
        rest = line[1:]
        prog = self.programs[frame[0]]
        blocks = frame[2]
        if head == "If ":
            ok = self.cond(rest)
            nxt = prog[frame[1]] if frame[1] < len(prog) else []
            if nxt and nxt[0] == "Then":
                frame[1] += 1
                if ok:
                    blocks.append(["If"])
                else:
                    where = self.skip_block(frame, True)
                    if where == "Else":
                        blocks.append(["If"])
            elif not ok:
                frame[1] += 1
            return
        if head == "Else":
            if not blocks or blocks[-1][0] != "If":
                raise TIError("Else without If")
            blocks.pop()
            self.skip_block(frame, False)
            return
        if head == "End":
            if not blocks:
                raise TIError("End without block")
            b = blocks[-1]
            if b[0] == "If":
                blocks.pop()
            elif b[0] == "For":
                _, var, end, step, start_pc = b
                v = r14(self.vars[var] + step)
                self.vars[var] = v
                if (step > 0 and v <= end) or (step < 0 and v >= end):
                    frame[1] = start_pc
                else:
                    blocks.pop()
            elif b[0] == "While":
                if self.cond(b[1]):
                    frame[1] = b[2]
                else:
                    blocks.pop()
            elif b[0] == "Repeat":
                if not self.cond(b[1]):
                    frame[1] = b[2]
                else:
                    blocks.pop()
            return
        if head == "For(":
            args = build.split_args(rest)
            var = args[0][0]
            start = self.real(self.ev(self.ast(args[1])))
            end = self.real(self.ev(self.ast(args[2])))
            step = self.real(self.ev(self.ast(args[3]))) if len(args) > 3 else 1.0
            self.vars[var] = start
            if (step > 0 and start > end) or (step < 0 and start < end):
                self.skip_block(frame, False)
            else:
                blocks.append(["For", var, end, step, frame[1]])
            return
        if head == "While ":
            if self.cond(rest):
                blocks.append(["While", rest, frame[1]])
            else:
                self.skip_block(frame, False)
            return
        if head == "Repeat ":
            blocks.append(["Repeat", rest, frame[1]])
            return
        if head == "Lbl ":
            return
        if head == "Goto ":
            if blocks:
                self.warnings.append(f"Goto out of block in {frame[0]}")
                frame[2] = []
            frame[1] = self.find_label(frame[0], "".join(rest))
            return
        if head == "Return":
            self.frames.pop()
            return
        if head == "Stop":
            self.frames = []
            return
        if head == "prgm":
            name = "".join(rest)
            if name not in self.programs:
                raise TIError("UNDEFINED prgm" + name)
            self.frames.append([name, 0, []])
            return
        if head == "Menu(":
            if blocks:
                self.warnings.append(f"Menu inside block in {frame[0]}")
                frame[2] = []
            args = build.split_args(rest)
            title = args[0][1:]
            items = [(args[i][1:], "".join(args[i + 1]))
                     for i in range(1, len(args) - 1, 2)]
            self.log.append("[MENU " + "".join(t for t in title if t != '"') + ": "
                            + " | ".join(f"{k+1}:{''.join(x for x in t if x != chr(34))}"
                                         for k, (t, _) in enumerate(items)) + "]")
            choice = self.next_input()
            k = int(choice) - 1
            if not 0 <= k < len(items):
                raise TIError(f"bad menu choice {choice}")
            self.log.append(f"  > {choice}")
            self.clr()
            frame[1] = self.find_label(frame[0], items[k][1])
            return
        if head == "ClrHome":
            self.clr()
            return
        if head == "Pause ":
            if rest:
                v = self.ev(self.ast(rest))
                self.show_value(v)
            self.pages.append(self.snapshot())
            self.log.append("[PAUSE]")
            return
        if head == "Disp ":
            for a in build.split_args(rest):
                v = self.ev(self.ast(a))
                self.show_value(v)
            return
        if head == "Output(":
            a = build.split_args(rest)
            r = int(self.real(self.ev(self.ast(a[0]))))
            c = int(self.real(self.ev(self.ast(a[1]))))
            v = self.ev(self.ast(a[2]))
            if not (1 <= r <= 8 and 1 <= c <= 16):
                raise TIError("DOMAIN Output")
            text = self.chars(v) if is_str(v) else list(fmt(v))
            self.put(r - 1, c - 1, text)
            self.log.append("".join(text))
            return
        if head in ("Input ", "Prompt "):
            self.do_input(head, rest)
            return
        if head in ("FnOn ", "PlotsOff ", "ClrDraw"):
            if head == "ClrDraw":
                self.drawing = []
            return
        if head == "DispGraph":
            w = self.window
            if not (w.get("Xmin", 0) < w.get("Xmax", 0) and w.get("Ymin", 0) < w.get("Ymax", 0)):
                raise TIError("WINDOW RANGE")
            self.drawing.append("GRAPH Y1 on " + str(w))
            return
        if head == "Text(":
            a = build.split_args(rest)
            r = self.real(self.ev(self.ast(a[0])))
            c = self.real(self.ev(self.ast(a[1])))
            v = self.ev(self.ast(a[2]))
            if not (0 <= r <= 164 and 0 <= c <= 264):   # TI-84 Plus CE graph
                raise TIError(f"DOMAIN Text({r},{c})")
            text = "".join(self.chars(v)) if is_str(v) else fmt(v)
            self.drawing.append(f"Text {int(r)},{int(c)} {text}")
            return
        if head in ("Pt-On(", "Vertical ", "Horizontal "):
            vals = [self.real(self.ev(self.ast(a))) for a in build.split_args(rest)]
            self.drawing.append(head.strip() + " " + ",".join(fmt(v) for v in vals))
            return
        if head in ("Real", "a+b𝑖", "Float", "Func", "FnOff "):
            if head == "Real":
                self.complex_mode = False
            if head == "a+b𝑖":
                self.complex_mode = True
            return
        if head == "DelVar ":
            name = "".join(rest)
            self.lists.pop(name, None)
            self.vars.pop(name, None)
            return
        if head == "SortA(":
            names = [self.list_name(a) for a in build.split_args(rest)]
            keys = self.lists[names[0]]
            order = sorted(range(len(keys)), key=lambda i: self.real(keys[i]))
            for nm in names:
                lst = self.lists[nm]
                if len(lst) != len(keys):
                    raise TIError("DIM MISMATCH SortA")
                self.lists[nm] = [lst[i] for i in order]
            return
        if head == "LinReg(ax+b) ":
            a = build.split_args(rest)
            xs = self.lists[self.list_name(a[0])]
            ys = self.lists[self.list_name(a[1])]
            n = len(xs)
            mx, my = sum(xs) / n, sum(ys) / n
            sxx = sum((x - mx) ** 2 for x in xs)
            sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            sl = r14(sxy / sxx)
            ic = r14(my - sl * mx)
            eq = list(fmt(sl)) + ["X", "+"] + list(fmt(ic))
            self.yvars[a[2][0]] = tuple(eq)
            return
        if head == "Equ►String(":
            a = build.split_args(rest)
            self.strs[a[1][0]] = tuple(self.yvars[a[0][0]])
            return
        if head == "String►Equ(":
            a = build.split_args(rest)
            v = self.ev(self.ast(a[0]))
            if not is_str(v):
                raise TIError("DATA TYPE String>Equ")
            self.yvars[a[1][0]] = tuple(v)
            self.cache.pop(tuple(v), None)
            return
        # expression [→ target]
        if "→" in line:
            k = len(line) - 1 - line[::-1].index("→")
            # a store arrow inside a string literal would have closed it
            val = self.ev(self.ast(line[:k]))
            self.store_tokens(line[k + 1:], val)
            self.vars["Ans"] = val if not (is_list(val) or is_str(val)) else self.vars.get("Ans", 0.0)
        else:
            self.vars["Ans"] = self.ev(self.ast(line))

    def show_value(self, v):
        if is_str(v):
            self.disp_line(self.chars(v))
        elif is_list(v):
            self.disp_line(list("{" + " ".join(fmt(x) for x in v) + "}"))
        else:
            self.disp_line(list(fmt(v)), right=True)

    def next_input(self):
        if not self.inputs:
            raise NeedInput(self.snapshot())
        return self.inputs.pop(0)

    def do_input(self, head, rest):
        args = build.split_args(rest)
        if len(args) == 2 or (len(args) == 1 and rest[0] == '"'):
            prompt = self.chars(self.ev(self.ast(args[0])))
            target = args[1] if len(args) == 2 else None
        else:
            prompt = list("?")
            target = args[0]
        text = self.next_input()
        self.disp_line(prompt + list(text))
        toks = [t for t, _ in build.tokenize_line(text)]
        if target[0] in STRS:
            self.strs[target[0]] = tuple(toks)
        else:
            val = self.ev(self.ast(toks))
            self.store_tokens(target, val)


def load_programs(src_dir=None):
    src = pathlib.Path(src_dir or build.SRC)
    progs = {}
    for path in sorted(src.glob("*.tib")):
        name = build.ti_name(path.stem)
        _, token_lines = build.tokenize(name, build.source_lines(path))
        progs[name] = token_lines
    return progs


def run(inputs, start="BCALC", programs=None, **kw):
    calc = Calc(programs or load_programs(), inputs, **kw)
    try:
        calc.run(start)
        calc.finished = True
    except NeedInput:
        calc.finished = False
    return calc


if __name__ == "__main__":
    c = run(sys.argv[1:])
    print("\n".join(c.log))
