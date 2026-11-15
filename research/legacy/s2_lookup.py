# -*- coding: utf-8 -*-
import json
import urllib.request
import time

DOIS = {
    "Tutorial": "10.1145/3524499",
    "Survey": "10.1145/3666002",
    "StateOfArt": "10.1016/j.neucom.2025.130418",
    "DDA": "10.1109/JBHI.2022.3210158",
    "CMJDA": "10.1109/TIM.2025.3551924",
    "SSAS": "10.1016/j.eswa.2025.130843",
    "BiDANN": "10.1109/TAFFC.2018.2885474",
    "TT-CDAN": "10.1109/TAFFC.2025.3588873",
    "DAPLP": "10.1109/TIM.2025.3553234",
    "MSGDAN": "10.1016/j.neunet.2024.106742",
    "Sera": "10.1145/3746027.3754775",
    "MIND-EEG": "10.1109/TAFFC.2025.3608571",
    "PCL-TDGCN": "10.1109/TAFFC.2026.3671020",
    "TAHAG": "10.1109/TAFFC.2025.3580787",
    "CLISA": "10.1109/TAFFC.2022.3164516",
    "GMSS": "10.1109/TAFFC.2022.3170428",
    "DMMR": "10.1609/aaai.v38i1.27819",
    "MSHCL": "10.1109/TAFFC.2025.3535542",
    "InfoFusion": "10.1016/j.inffus.2026.104224",
    "SEED-VII": "10.1109/TAFFC.2024.3485057",
}

for name, doi in DOIS.items():
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=title,venue,year,externalIds,openAccessPdf"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "research-agent"})
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.load(r)
        print(f"{name}\t{d.get('year')}\t{d.get('venue')}\t{d.get('externalIds')}\t{d.get('openAccessPdf')}")
    except Exception as e:
        print(f"{name}\tERR\t{e}")
    time.sleep(1.2)
