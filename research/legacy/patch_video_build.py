# -*- coding: utf-8 -*-
import re

p = r"C:\Users\24114\Desktop\EEG Emotion Recognition\research\legacy\生成视频交付物.py"
s = open(p, encoding="utf-8").read()
repl = [
    ("research/quality/audio", "research/quality/video"),
    ("音乐歌曲质量评分与排序.xlsx", "视频质量评分与排序.xlsx"),
    ("音乐歌曲质量排序.csv", "视频质量排序.csv"),
    ("离散情绪分类排序.csv", "视频离散情绪分类排序.csv"),
    ("质量排序_Top18_Bottom18.png", "视频质量排序_Top18_Bottom18.png"),
    ("音乐歌曲编号", "视频编号"),
    ("歌曲数", "视频数"),
    ("山科音乐数据集", "山科视频数据集"),
    ("单曲质量评分排序（共 120 首）", "视频质量评分排序（共 120 条）"),
    ("含无效评分者", "剔除部分评分者赵瀚"),
    ("歌曲", "视频"),
    ("音乐", "视频"),
]
for a, b in repl:
    s = s.replace(a, b)
open(p, "w", encoding="utf-8").write(s)
for kw in ["音乐", "歌曲", "歌词", "音质"]:
    print(kw, [m.start() for m in re.finditer(kw, s)][:10])
print("done")
