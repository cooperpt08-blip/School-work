#!/usr/bin/env python3
"""Compile src/*.tib (TI-BASIC source, Unicode token names) into TI-84 Plus
.8xp program files, plus one .8xg group file holding all of them.

Also runs static checks that catch the mistakes that are easy to make in
TI-BASIC and hard to see on a calculator:
  * every token exists on the TI-84 Plus (tokenised with the TI-84+ table)
  * no lowercase-letter tokens (sign of a mistyped command name)
  * If/Then/For/While/Repeat ... End balance, Else placement
  * Goto / Menu( never executed from inside an open block (memory leak)
  * every Goto / Menu( label exists, labels are 1-2 chars and unique
  * every prgmNAME called exists
  * Menu( title <= 16 chars, item text <= 14 chars, <= 7 items
  * Disp / Output( string literals fit the 16-column screen

Usage: python3 tools/build.py   (needs `pip install tivars`)
"""
import pathlib
import re
import sys

from tivars.models import TI_84P
from tivars.types import TIGroup, TIProgram

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUT = ROOT / "build"

# commands whose token text ends in a space; a bare line needs it added back
BARE_FIX = {"Pause": "Pause ", "FnOff": "FnOff ", "PlotsOff": "PlotsOff "}

BLOCK_OPENERS = ("For(", "While ", "Repeat ")

# Internal helper programs get 2-letter names on the calculator (each call
# then costs 3 bytes instead of 6-8).  Source files keep readable names.
SHORT = {
    "BCADD": "ZA", "BCBIS": "ZB", "BCCHT": "ZC", "BCCLS": "ZK",
    "BCCOEF": "ZN", "BCDIF": "ZJ", "BCEB": "Z9", "BCEND": "ZE",
    "BCEXT": "ZO", "BCFD": "ZD", "BCFRC": "ZF", "BCGOLD": "ZG",
    "BCHNT": "ZH", "BCIN2": "Z2", "BCINF": "ZI", "BCIV": "ZW",
    "BCLIM1": "Z1", "BCLIMQ": "ZQ", "BCLIMS": "Z3", "BCLPR": "ZL",
    "BCLTB": "Z4", "BCMUL": "ZM", "BCPD": "Z5", "BCPEV": "Z6",
    "BCPR": "ZP", "BCPSTR": "ZT", "BCPV": "ZV", "BCRAT": "Z7",
    "BCROOT": "ZR", "BCRPT": "Z8", "BCSCAN": "ZZ", "BCSETY": "ZY",
    "BCSTR": "ZS", "BCTRIM": "Z0", "BCVA": "ZU", "BCXY": "ZX",
}
# optional modules: keep them in Archive unless you need them
EXTRAS = {"BCSIGN", "BCTOOLS", "BCFORM", "BCOPT2"}
CALL_RE = re.compile(r"prgm(BC[A-Z0-9]*)")


def ti_name(stem):
    return SHORT.get(stem, stem)


def source_lines(path):
    """Program lines with comments and indentation removed."""
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = CALL_RE.sub(lambda m: "prgm" + ti_name(m.group(1)), line)
        lines.append(BARE_FIX.get(line, line))
    return lines


ALLOWED_MODELS = ("TI-82", "TI-83", "TI-83+", "TI-84+")


def _token_tables():
    """name -> token bytes, for tokens that exist on a TI-84 Plus."""
    table, single = {}, {}
    for bits, tok in TI_84P.tokens.bytes.items():
        if tok.since.model not in ALLOWED_MODELS:
            continue
        for name in [tok.display] + list(tok.names()):
            table.setdefault(name, bits)
        single.setdefault(tok.display, bits)
    for bits, tok in TI_84P.tokens.bytes.items():
        if tok.since.model in ALLOWED_MODELS:
            for name in tok.names():
                if len(name) == 1:
                    single.setdefault(name, bits)
    # inside strings "~" must be the tilde character, not negation
    single["~"] = b"\xbb\xcf"
    return table, single


TABLE, SINGLE = _token_tables()
MAXLEN = max(len(n) for n in TABLE)
# multi-character tokens that are allowed inside string literals
STRING_TOKENS = [f"Y{c}" for c in "₀₁₂₃₄₅₆₇₈₉"] + ["³√(", "√(", "𝑒^(", "𝑒",
                                                    "ln(", "log(", "abs(", "⁻¹"]
CLOSERS = (")", "}")


def tokenize_line(line):
    """Tokenize one source line -> list of (text, bytes)."""
    toks, i, in_str = [], 0, False
    while i < len(line):
        if in_str:
            for name in STRING_TOKENS:
                if line.startswith(name, i):
                    toks.append((name, TABLE[name]))
                    i += len(name)
                    break
            else:
                ch = line[i]
                if ch not in SINGLE:
                    raise ValueError(f"no token for {ch!r} in string")
                toks.append((ch, SINGLE[ch]))
                if ch == '"':
                    in_str = False
                i += 1
            continue
        if toks and toks[-1][0] in ("ʟ", "prgm", "Lbl ", "Goto "):
            # names: one token per character (avoid e.g. ʟPV -> TVM "PV")
            j = i
            while j < len(line) and (line[j].isupper() or line[j].isdigit()
                                     or line[j] == "θ") and j - i < 8:
                toks.append((line[j], TABLE[line[j]]))
                j += 1
            if j > i:
                i = j
                continue
        for n in range(min(MAXLEN, len(line) - i), 0, -1):
            name = line[i:i + n]
            if name in TABLE:
                toks.append((name, TABLE[name]))
                if name == '"':
                    in_str = True
                i += n
                break
        else:
            raise ValueError(f"cannot tokenize {line[i:i+12]!r}")
    return toks


def strip_closers(toks):
    """Drop closing ) } and " that TI-BASIC does not need: at the end of
    a line and right before a store arrow.  (Not on For( lines.)"""
    if toks and toks[0][0] == "For(":
        return toks
    out, in_str = [], False

    def trim():
        while out:
            last = out[-1][0]
            if last in CLOSERS and not in_string(out):
                out.pop()
            elif last == '"' and closing_quote(out):
                out.pop()      # string closed; stop: the rest is text
                return
            else:
                return

    for text, bits in toks:
        if text == '"':
            in_str = not in_str
        if text == "→" and not in_str:
            trim()
        out.append((text, bits))
    trim()
    return out


def in_string(toks):
    """True if the end of toks is inside an unclosed string literal."""
    return sum(1 for t, _ in toks if t == '"') % 2 == 1


def closing_quote(toks):
    """True if the last token (a quote) closes a string."""
    return sum(1 for t, _ in toks if t == '"') % 2 == 0


def tokenize(name, lines, strip=True):
    token_lines = [tokenize_line(l) for l in lines]
    if strip:
        token_lines = [strip_closers(t) for t in token_lines]
    data = b"\x3f".join(b"".join(b for _, b in t) for t in token_lines)
    prog = TIProgram(name=name)
    prog.data = data
    return prog, [[t for t, _ in tl] for tl in token_lines]


def split_lines(tokens):
    """Token display strings grouped per program line."""
    out, cur = [], []
    for tok in tokens:
        text = str(tok)
        if text == "\n":
            out.append(cur)
            cur = []
        else:
            cur.append(text)
    out.append(cur)
    return out


def string_literals(toks):
    """String literals in a token line (TI closes a string at " or →)."""
    lits, cur, inside = [], None, False
    for t in toks:
        if inside:
            if t in ('"', "→"):
                lits.append(cur)
                inside = False
            else:
                cur.append(t)
        elif t == '"':
            inside, cur = True, []
    if inside:
        lits.append(cur)
    return lits


def split_args(toks):
    """Split a call's argument tokens on top-level commas."""
    args, cur, depth, inside = [], [], 0, False
    for t in toks:
        if t == '"':
            inside = not inside
        if not inside:
            if t.endswith("(") or t in ("{", "["):
                depth += 1
            elif t in (")", "}", "]"):
                depth -= 1
                if depth < 0:
                    break
            elif t == "," and depth == 0:
                args.append(cur)
                cur = []
                continue
        cur.append(t)
    args.append(cur)
    return args


def lint(name, token_lines, programs):
    errs = []
    labels, gotos = {}, []
    stack = []          # open blocks: "If", "For", ...
    pending_if = False  # previous line was a bare If (single-line form)
    for no, toks in enumerate(token_lines, 1):
        where = f"{name}:{no}"
        if not toks:
            continue
        head = toks[0]
        for t in toks:
            if len(t) == 1 and "a" <= t <= "z":
                errs.append(f"{where}: lowercase token {t!r}")
        lits = string_literals(toks)
        if head == "Then":
            if not pending_if:
                errs.append(f"{where}: Then without If")
            stack.append("If")
        elif head == "Else":
            if not stack or stack[-1] != "If":
                errs.append(f"{where}: Else outside If-Then")
        elif head == "End":
            if not stack:
                errs.append(f"{where}: End without block")
            else:
                stack.pop()
        elif head in BLOCK_OPENERS:
            stack.append(head)
        if head in ("Goto ", "Menu(") and stack and not pending_if:
            errs.append(f"{where}: {head.strip()} inside an open block "
                        f"{stack} (memory leak on TI)")
        if head == "Lbl ":
            lab = "".join(toks[1:])
            if not 1 <= len(lab) <= 2:
                errs.append(f"{where}: bad label {lab!r}")
            if lab in labels:
                errs.append(f"{where}: duplicate label {lab!r}")
            labels[lab] = no
        if head == "Goto ":
            gotos.append(("".join(toks[1:]), where))
        if head == "prgm":
            callee = "".join(toks[1:])
            if callee not in programs:
                errs.append(f"{where}: calls missing program {callee}")
        if head == "Menu(":
            args = split_args(toks[1:])
            title = args[0]
            items = args[1:]
            if len(items) % 2 or len(items) // 2 > 7:
                errs.append(f"{where}: Menu( needs <=7 text/label pairs")
            if len(title) - 2 > 16:
                errs.append(f"{where}: Menu title too long")
            for i in range(0, len(items) - 1, 2):
                text, lab = items[i], "".join(items[i + 1])
                if sum(len(t) for t in text) - 2 > 14:
                    errs.append(f"{where}: Menu item {''.join(text)} > 14")
                gotos.append((lab, where))
        if head == "Disp ":
            for lit in lits:
                if sum(len(t) for t in lit) > 16:
                    errs.append(f"{where}: Disp text > 16: {''.join(lit)}")
        if head == "Output(":
            args = split_args(toks[1:])
            if len(args) == 3 and args[2] and args[2][0] == '"':
                col = int("".join(args[1]))
                if col - 1 + len(args[2]) - 2 > 16:
                    errs.append(f"{where}: Output( text runs off screen")
        pending_if = head == "If "
    if stack:
        errs.append(f"{name}: unclosed blocks {stack}")
    for lab, where in gotos:
        if lab not in labels:
            errs.append(f"{where}: no Lbl {lab}")
    return errs


def main():
    OUT.mkdir(exist_ok=True)
    srcs = sorted(SRC.glob("*.tib"))
    programs = {ti_name(p.stem) for p in srcs}
    built, errors, total = [], [], 0
    for path in srcs:
        name = ti_name(path.stem)
        if not re.fullmatch(r"[A-Z][A-Z0-9]{0,7}", name):
            errors.append(f"{name}: invalid TI program name")
        lines = source_lines(path)
        try:
            prog, token_lines = tokenize(name, lines)
            _, full_lines = tokenize(name, lines, strip=False)
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
            continue
        # every byte sequence must decode back to a TI-84 Plus token
        decoded = prog.tokens()
        if len(decoded) != sum(len(t) for t in token_lines) + len(token_lines) - 1:
            errors.append(f"{name}: token round trip mismatch")
        for tok in decoded:
            if tok.since.model not in ALLOWED_MODELS:
                errors.append(f"{name}: token {tok} needs {tok.since}")
        errors += lint(name, full_lines, programs)
        prog.save(str(OUT / f"{name}.8xp"))
        size = len(prog.data)
        total += size
        built.append((name, size, len(lines)))
        (OUT / f"{name}.txt").write_text("\n".join(lines) + "\n", "utf-8")
    sizes = {n: sz for n, sz, _ in built}
    for gname, members in (("BCALC", [n for n in sizes if n not in EXTRAS]),
                           ("BCEXTRA", [n for n in sizes if n in EXTRAS])):
        group = TIGroup.group([TIProgram.open(str(OUT / f"{n}.8xp"))
                               for n in members], name=gname)
        group.save(str(OUT / f"{gname}.8xg"))
        print(f"{gname}.8xg: {len(members)} programs, "
              f"{sum(sizes[n] for n in members)} bytes of program data")
    for name, size, nlines in built:
        print(f"{name:8s} {size:6d} bytes {nlines:5d} lines")
    print(f"TOTAL    {total:6d} bytes in {len(built)} programs")
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    print("lint: OK")


if __name__ == "__main__":
    main()
