"""python -m kalshi_bot.research.run_games nba|nfl  -> prints the factor table and walk-forward test."""
import json
import sys

from . import analysis as A


def main(league):
    out = A.run(league)
    res = sorted(out["results"], key=lambda r: r["mkt_q"])
    print(f"\n{league.upper()} - {out['n_priced']} games with a Kalshi price (of {out['n_games']})")
    print(f"{'factor':<36}{'n':>6}  {'RAW: predicts winner?':>22}   {'BEYOND KALSHI PRICE?':>24}")
    print(f"{'':<36}{'':>6}  {'effect':>8}{'z':>7}{'q':>7}   {'effect':>8}{'z':>7}{'q':>7}")
    for r in sorted(out["results"], key=lambda r: -abs(r["raw_z"])):
        flag = "  <== beats price" if r["mkt_q"] < 0.10 else ""
        print(f"{r['factor']:<36}{r['n']:>6}  {r['raw_b'] * 25:>+7.1f}%{r['raw_z']:>+7.1f}{r['raw_q']:>7.3f}   "
              f"{r['mkt_b'] * 25:>+7.1f}%{r['mkt_z']:>+7.1f}{r['mkt_q']:>7.3f}{flag}")
    print("\n(effect = approx. change in win chance per 1 standard deviation of the factor)")
    wf = out["walk_forward"]
    print("\nWalk-forward: factors chosen on the older 70% only:", out["chosen"] or "none passed")
    if wf:
        print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in wf.items() if k != "weights"}, indent=1))
        print("weights:", {k: round(v, 3) for k, v in wf["weights"].items()})
    json.dump({**out, "results": res}, open(f"kalshi_bot/research/data/results_{league}_games.json", "w"), default=str, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
