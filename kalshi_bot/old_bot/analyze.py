import csv
from collections import defaultdict
rows=[r for r in csv.DictReader(open(__import__("pathlib").Path(__file__).parent / "old_picks_graded.csv")) if r["result"]]
for r in rows:
    for k in ("model","kalshi","edge"): r[k]=float(r[k])
    r["w"]=r["result"]=="W"; r["pnl"]=(1-r["kalshi"]) if r["w"] else -r["kalshi"]
def line(name, rs):
    n=len(rs); w=sum(r["w"] for r in rs)
    if not n: return
    print(f"{name:<34}{w:>4}-{n-w:<4}{w/n:6.1%}  model said {sum(r['model'] for r in rs)/n:6.1%}  market said {sum(r['kalshi'] for r in rs)/n:6.1%}  P/L ${sum(r['pnl'] for r in rs):+7.2f}  ROI {sum(r['pnl'] for r in rs)/sum(r['kalshi'] for r in rs):+6.1%}")
def group(title,key):
    print(f"\n== {title}"); g=defaultdict(list)
    for r in rows: g[key(r)].append(r)
    for k in sorted(g): line(str(k), g[k])
line("ALL (1 contract per pick)", rows)
group("Sport", lambda r:r["sport"])
group("Bet type", lambda r:r["type"])
group("Sport+type", lambda r:f'{r["sport"]} {r["type"]}')
group("Edge size", lambda r:"a <8%" if r["edge"]<.08 else "b 8-12%" if r["edge"]<.12 else "c 12-20%" if r["edge"]<.20 else "d 20%+")
group("Model probability", lambda r:"a <40%" if r["model"]<.4 else "b 40-55%" if r["model"]<.55 else "c 55-65%" if r["model"]<.65 else "d 65-80%" if r["model"]<.8 else "e 80%+")
group("Market price (fav/dog)", lambda r:"a dog <45c" if r["kalshi"]<.45 else "b coinflip 45-55c" if r["kalshi"]<.55 else "c fav 55-70c" if r["kalshi"]<.7 else "d big fav 70c+")
print("\n== MLB moneyline only, by market price")
g=defaultdict(list)
for r in rows:
    if r["sport"]=="MLB" and r["type"]=="Moneyline": g["dog" if r["kalshi"]<.5 else "fav"].append(r)
for k in g: line(k,g[k])
print("\n== MLB totals: Over vs Under")
g=defaultdict(list)
for r in rows:
    if r["sport"]=="MLB" and r["type"]=="Total": g[r["selection"].split()[0]].append(r)
for k in g: line(k,g[k])
print("\nBiggest-edge losers:")
for r in sorted(rows,key=lambda r:-r["edge"])[:12]: print(f'  {r["result"]} {r["edge"]:+.1%} model {r["model"]:.0%} vs {r["kalshi"]:.0%}  {r["sport"]} {r["selection"]} | {r["score"]}')
