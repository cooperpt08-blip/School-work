"""python -m kalshi_bot.research.run_props nba|nfl"""
import json
import sys

from . import analysis as A
from . import props as P

SER = {"nba": ["KXNBAPTS", "KXNBAREB", "KXNBAAST", "KXNBA3PT"], "nfl": ["KXNFLRECYDS", "KXNFLRSHYDS", "KXNFLPASSYDS"]}


def main(league):
    allrows = []
    for s in SER[league]:
        rows = sorted(P.build(s), key=lambda r: r["date"])
        allrows += rows
    allrows.sort(key=lambda r: r["date"])
    hit = sum(r["y"] for r in allrows) / len(allrows)
    print(f"\n{league.upper()} props: {len(allrows)} priced markets; hit rate {hit:.3f}; price said {sum(r['p'] for r in allrows) / len(allrows):.3f}")
    res = A.test_all(allrows, min_n=300)
    print(f"{'factor':<30}{'n':>7}  {'RAW effect':>10}{'z':>7}   {'BEYOND PRICE':>12}{'z':>7}{'q':>7}")
    for r in sorted(res, key=lambda r: r["mkt_q"]):
        flag = "  <== beats price" if r["mkt_q"] < 0.10 else ""
        print(f"{r['factor']:<30}{r['n']:>7}  {r['raw_b'] * 25:>+9.1f}%{r['raw_z']:>+7.1f}   {r['mkt_b'] * 25:>+11.1f}%{r['mkt_z']:>+7.1f}{r['mkt_q']:>7.3f}{flag}")
    k = int(len(allrows) * 0.7)
    tr = A.test_all(allrows[:k], min_n=300)
    chosen = [r["factor"] for r in sorted(tr, key=lambda r: -abs(r["mkt_z"])) if abs(r["mkt_z"]) >= 2.5][:8]
    wf = A.walk_forward(allrows, chosen)
    print("\nwalk-forward factors (chosen on older 70%):", chosen)
    if wf:
        print({k2: (round(v, 4) if isinstance(v, float) else v) for k2, v in wf.items() if k2 not in ("weights", "factors")})
        print("weights:", {k2: round(v, 3) for k2, v in wf["weights"].items()})
    corr = P.correlations(allrows, league)
    print("\nSame-game parlay legs (both hit, vs. what prices imply if independent):")
    for k2, v in sorted(corr.items(), key=lambda kv: -kv[1]["n"]):
        print(f"  {k2:<40} n={v['n']:<6} both hit {v['both_hit']:.3f}  independent {v['if_independent']:.3f}  "
              f"lift x{v['lift_vs_independent']:.2f}  prices imply {v['prices_imply']:.3f}  z {v['z_vs_prices']:+.1f}")
    json.dump({"results": res, "walk_forward": wf, "correlations": corr}, open(f"kalshi_bot/research/data/results_{league}_props.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main(sys.argv[1])
