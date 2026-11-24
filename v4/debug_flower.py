import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import new_engine as E
import gen_v2 as G

NM = {0: "草", 1: "土", 2: "石", 3: "沙", 4: "泥", 5: "雪", 7: "水", 8: "海",
      9: "洋", 11: "岩浆", 12: "高草", 14: "高石", 23: "浅滩"}

for name, builder in [("图一", G.build_1), ("图二", G.build_2), ("图三", G.build_3),
                      ("图五", G.build_5), ("图七", G.build_7), ("图八", G.build_8)]:
    cv, sp, nm = builder(120)
    H = W = 120
    WAT = {7, 8, 9, 23}
    canon = lambda t: 70 if t in WAT else t
    bad = []
    for r in range(H - 1):
        for c in range(W - 1):
            s = {canon(cv.g[r][c]), canon(cv.g[r + 1][c]), canon(cv.g[r][c + 1]), canon(cv.g[r + 1][c + 1])}
            if len(s) > 2:
                bad.append((r, c))
    from collections import Counter
    cats = Counter()
    for (r, c) in bad[:200]:
        blk = [cv.g[r][c], cv.g[r + 1][c], cv.g[r][c + 1], cv.g[r + 1][c + 1]]
        cats[tuple(sorted(NM.get(x, x) for x in blk))] += 1
    print(f"\n=== {name} 花屏 {len(bad)} 处，前若干 2x2 类别组合 ===")
    for k, v in cats.most_common(8):
        print("   ", k, "x", v)
