# -*- coding: utf-8 -*-
import json
import urllib.parse
import urllib.request
import time

TITLES = [
    "SEED-V dataset EEG eye movement emotion",
    "MPED A Multi-Modal Physiological Emotion Database for Discrete Emotion Recognition",
    "A large finer-grained affective computing EEG dataset",
    "EmotionMeter A Multimodal Framework for Recognizing Human Emotions",
    "DEAP A Database for Emotion Analysis Using Physiological Signals",
    "DREAMER A Database for Emotion Recognition Through EEG and ECG Signals",
    "A Multimodal Database for Affect Recognition and Implicit Tagging",
    "Investigating critical frequency bands and channels for EEG-based emotion recognition with deep neural networks",
]

for t in TITLES:
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode({
        "query.bibliographic": t, "rows": 2,
        "select": "DOI,title,container-title,issued,author",
    })
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            d = json.load(r)
        print("\n###", t)
        for it in d["message"]["items"]:
            title = (it.get("title") or [""])[0]
            cont = (it.get("container-title") or [""])[0]
            year = it.get("issued", {}).get("date-parts", [[None]])[0][0]
            au = ", ".join(a.get("family", "") for a in it.get("author", [])[:3])
            print(f"  - {title} | {cont} | {year} | {au} | https://doi.org/{it['DOI']}")
    except Exception as e:
        print("ERR", t, e)
    time.sleep(0.4)
