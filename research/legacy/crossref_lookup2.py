# -*- coding: utf-8 -*-
import json
import urllib.parse
import urllib.request

for q in ["A Novel Conditional Adversarial Domain Adaptation Network for EEG Cross-Subject Emotion Recognition",
          "SEED-VII emotion dataset",
          "EEG Based Emotion Recognition A Tutorial and Review"]:
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode({
        "query.bibliographic": q, "rows": 4,
        "select": "DOI,title,container-title,issued,author,type",
    })
    with urllib.request.urlopen(url, timeout=20) as r:
        d = json.load(r)
    print("\n###", q)
    for it in d["message"]["items"]:
        title = (it.get("title") or [""])[0]
        cont = (it.get("container-title") or [""])[0]
        year = it.get("issued", {}).get("date-parts", [[None]])[0][0]
        authors = ", ".join(a.get("family", "") for a in it.get("author", [])[:5])
        print(f"  - {title} | {cont} | {year} | {authors} | https://doi.org/{it['DOI']}")
