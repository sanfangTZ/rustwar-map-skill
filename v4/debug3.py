import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import new_engine as E
import gen_v2 as G
import gen_5v5_common as G5

NM = {0:"草",1:"土",2:"石",3:"沙",4:"泥",5:"雪",7:"水",8:"海",9:"洋",11:"岩浆",12:"高草",14:"高石",23:"浅滩"}

def pipeline(builder, name, n=120):
    cv, sp, nm = builder(n)
    rngt = random.Random((hash(name)&0xffff)^0x9e37)
    if cv.base == G.SNOW:
        G.texture_pass(cv, rngt, G.SNOW, [(G.STONE,6),(G.MUD,1)], density=0.05, rlo=2.4, rhi=4.2)
    else:
        G.texture_pass(cv, rngt, G.GRASS, [(G.DIRT,3),(G.STONE,2),(G.SAND,1),(G.MUD,1)], density=0.10)
    E.connect_all(cv, sp)
    for _ in range(2):
        try: G5.edge_auto_fix(cv.g, threshold=99.5, max_iters=10)
        except RuntimeError: pass
        G.enforce_2type_v2(cv.g)
    try: G5.edge_auto_fix(cv.g, threshold=99.0, max_iters=30)
    except RuntimeError: pass
    G.enforce_2type_v2(cv.g)
    return cv

for name, builder in [("图三",G.build_3),("图四",G.build_4),("图五",G.build_5),("图七",G.build_7),("图八",G.build_8)]:
    cv = pipeline(builder, name)
    H=W=120; WAT={7,8,9,23}
    canon=lambda t:70 if t in WAT else t
    bad=[]
    for r in range(H-1):
        for c in range(W-1):
            s={canon(cv.g[r][c]),canon(cv.g[r+1][c]),canon(cv.g[r][c+1]),canon(cv.g[r+1][c+1])}
            if len(s)>2: bad.append((r,c))
    from collections import Counter
    cats=Counter()
    locs=[]
    for (r,c) in bad[:300]:
        blk=[cv.g[r][c],cv.g[r+1][c],cv.g[r][c+1],cv.g[r+1][c+1]]
        cats[tuple(sorted(NM.get(x,x) for x in blk))]+=1
        locs.append((r,c))
    print(f"\n=== {name} 残留花屏 {len(bad)} 处 ===")
    for k,v in cats.most_common(10): print("   ",k,"x",v)
    print("   位置样本:", locs[:12])
