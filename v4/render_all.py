import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import new_engine as E

OUT = "/workspace/重做地图/原版向"
PNG = "/workspace/重做地图/原版向_预览"
os.makedirs(PNG, exist_ok=True)
CN = ["一", "二", "三", "四", "五", "六", "七", "八"]
for i in range(1, 9):
    name = f"图{CN[i-1]}"
    tmx = os.path.join(OUT, f"{name}.tmx")
    png = os.path.join(PNG, f"{name}.png")
    if os.path.exists(tmx):
        E.render(tmx, png, scale=2)
        print("rendered", png)
    else:
        print("MISSING", tmx)
