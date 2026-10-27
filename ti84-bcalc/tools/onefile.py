#!/usr/bin/env python3
"""Merge all BCALC programs into ONE program, build/onefile/BCALC.8xp.

TI-BASIC has no subroutines inside a program, so every former program
becomes a labelled section of BCALC and a call becomes a recursive call of
BCALC itself:

    prgmZP          ->   1309.001→V        (section code in V)
                         prgmBCALC
    top of BCALC:   If V=1309.001  /  Goto <section label>   (dispatch)
    section:        Lbl <label> / 0→V / ...body... / Return

V is free for this: the only other use of V is inside the print helper,
which never calls anything.  Labels of every section are renamed to
unique two-character labels.

Meant for the TI-84 Plus CE (plenty of RAM; .8xg groups are not accepted
there).  Usage: python3 tools/onefile.py
"""
import itertools
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build  # noqa: E402

OUT = build.OUT / "onefile"
LABEL_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
# most frequently called sections first: their dispatch test runs first
HOT = ["ZP", "ZS", "ZV", "ZE", "ZX", "ZH", "ZF", "ZW", "ZY", "ZD", "ZA",
       "ZB", "ZK", "ZU", "ZG", "ZL", "Z1", "Z3", "ZQ", "ZT", "Z6"]


def split_top(text):
    """Split call arguments on top-level commas (quotes respected)."""
    parts, cur, depth, inq = [], "", 0, False
    for ch in text:
        if ch == '"':
            inq = not inq
        elif not inq and ch == "(":
            depth += 1
        elif not inq and ch == ")":
            depth -= 1
        if ch == "," and depth == 0 and not inq:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def merged_lines():
    srcs = {build.ti_name(p.stem): p for p in sorted(build.SRC.glob("*.tib"))}
    names = ["BCALC"] + [n for n in HOT if n in srcs] + \
        sorted(n for n in srcs if n != "BCALC" and n not in HOT)
    pool = ("".join(p) for p in itertools.product(LABEL_CHARS, repeat=2))
    code = {n: f"1309.{i:03d}" for i, n in enumerate(names) if n != "BCALC"}
    entry = {n: next(pool) for n in names if n != "BCALC"}

    out = []
    for n in names[1:]:
        out += [f"If V={code[n]}", f"Goto {entry[n]}"]
    for n in names:
        lines = build.source_lines(srcs[n])
        labels = {l[4:]: next(pool) for l in lines if l.startswith("Lbl ")}
        body = [] if n == "BCALC" else [f"Lbl {entry[n]}", "0→V"]
        for i, line in enumerate(lines):
            if line.startswith("Lbl "):
                line = "Lbl " + labels[line[4:]]
            elif line.startswith("Goto "):
                line = "Goto " + labels[line[5:]]
            elif line.startswith("Menu("):
                args = split_top(line[len("Menu("):].rstrip(")"))
                for k in range(2, len(args), 2):
                    args[k] = labels[args[k]]
                line = "Menu(" + ",".join(args) + ")"
            if line.startswith("prgm"):
                call = [f"{code[line[4:]]}→V", "prgmBCALC"]
                prev = lines[i - 1] if i else ""
                if prev.startswith("If "):        # single-line If guard
                    call = ["Then"] + call + ["End"]
                body += call
            else:
                body.append(line)
        body.append("Return")
        out += body
    return out


def main():
    lines = merged_lines()
    prog, token_lines = build.tokenize("BCALC", lines)
    _, full = build.tokenize("BCALC", lines, strip=False)
    errs = build.lint("BCALC", full, {"BCALC"})
    OUT.mkdir(parents=True, exist_ok=True)
    prog.save(str(OUT / "BCALC.8xp"))
    (OUT / "BCALC.txt").write_text("\n".join(lines) + "\n", "utf-8")
    print(f"BCALC.8xp: {len(prog.data)} bytes, {len(lines)} lines")
    if errs:
        print("\n".join(errs))
        sys.exit(1)
    print("lint: OK")
    return token_lines


if __name__ == "__main__":
    main()
