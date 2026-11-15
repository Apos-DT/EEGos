# -*- coding: utf-8 -*-
import urllib.request

DOIS = [
    "10.1145/3524499", "10.1145/3666002", "10.1016/j.neucom.2025.130418",
    "10.1109/JBHI.2022.3210158", "10.1109/TIM.2025.3551924", "10.1016/j.eswa.2025.130843",
    "10.1109/TAFFC.2018.2885474", "10.1109/TAFFC.2025.3588873", "10.1109/TIM.2025.3553234",
    "10.1016/j.neunet.2024.106742", "10.1145/3746027.3754775", "10.1109/TAFFC.2025.3608571",
    "10.1109/TAFFC.2026.3671020", "10.1109/TAFFC.2025.3580787", "10.1109/TAFFC.2022.3164516",
    "10.1109/TAFFC.2022.3170428", "10.1609/aaai.v38i1.27819", "10.1109/TAFFC.2025.3535542",
    "10.1016/j.inffus.2026.104224", "10.1109/TAFFC.2024.3485057",
    "10.1109/TAMD.2015.2431497", "10.1109/TCYB.2018.2797176", "10.1109/T-AFFC.2011.15",
    "10.1109/ACCESS.2019.2891579", "10.1109/JBHI.2017.2688239", "10.1038/s41597-023-02650-w",
    "10.1109/T-AFFC.2011.25",
]

for doi in DOIS:
    url = "https://doi.org/" + doi
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            print("OK", r.status, doi, "->", r.geturl()[:110])
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, doi, e.geturl()[:110] if e.geturl() else "")
    except Exception as e:
        print("ERR", doi, e)

for aid in ["2203.11279", "2512.13458", "2501.16230", "2109.09559", "2205.01030"]:
    try:
        req = urllib.request.Request("https://arxiv.org/abs/" + aid, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            print("ARXIV OK", aid, r.status)
    except Exception as e:
        print("ARXIV ERR", aid, e)
