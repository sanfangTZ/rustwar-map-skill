import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import new_engine as E
import gen_v2 as G
from collections import Counter

NM = {0: "草", 1: "土", 2: "石", 3: "沙", 4: "泥", 5: "雪", 7: "水", 8: "海",
      9: "洋", 11: "岩浆", 12: "高草", 14: "高石", 23: "浅滩"}

def flowers(grid):
    H, W = len(grid), len(grid[0])
    WAT = {7,8,9,23}
    canon = lambda t: 70 if t in WAT else t
    out = []
    for r in range(H-1):
        for c in range(W-1):
            s = {canon(grid[r][c]),canon(grid[r+1][c]),canon(grid[r][c+1]),canon(grid[r+1][c+1])}
            if len(s) > 2:
                out.append((r,c))
    return out

cv, sp, nm = G.build_2(120)
print("enforce 前花屏:", len(flowers(cv.g)))
for rnd in (100, 200, 400, 800, 1500):
    G.enforce_2type(cv.g, rounds=rnd)
    print(f"enforce {rnd} 后花屏:", len(flowers(cv.g)))
b = flowers(cv.g)
cats = Counter()
for (r,c) in b[:300]:
    blk = [cv.g[r][c], cv.g[r+1][c], cv.g[r][c+1], cv.g[r+1][c+1]]
    cats[tuple(sorted(NM.get(x,x) for x in blk))] += 1
print("残留 2x2 类别组合:")
for k,v in cats.most_common(10):
    print("   ", k, "x", v)
