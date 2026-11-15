# -*- coding: utf-8 -*-
import json
import urllib.parse
import urllib.request
import time

TITLES = [
    "EEG Based Emotion Recognition: A Tutorial and Review",
    "Research Progress of EEG-Based Emotion Recognition: A Survey",
    "Emotion recognition via affective EEG signals: State of the art",
    "SSAS: Cross-subject EEG-based emotion recognition through source selection with adversarial strategy",
    "Prototypical Contrastive Learning With Temporal Dynamic Graph Convolutional Network for EEG-Based Emotion Recognition",
    "Emotion recognition using multimodal physiological signals through regional to global fusion with a spatial-temporal semantic alignment mechanism",
    "A Bi-Hemisphere Domain Adversarial Neural Network Model for EEG Emotion Recognition",
    "Dynamic domain adaptation for class-aware cross-subject and cross-session EEG emotion recognition",
    "Multimodal Semi-Supervised Domain Adaptation Using Cross-Modal Learning and Joint Distribution Alignment for Cross-Subject Emotion Recognition",
    "Unsupervised Domain Adaptation With Pseudo-Label Propagation for Cross-Domain EEG Emotion Recognition",
    "Multi-source Selective Graph Domain Adaptation Network for cross-subject EEG emotion recognition",
    "Sera: Separated Coarse-to-fine Representation Alignment for Cross-subject EEG-based Emotion Recognition",
    "MIND-EEG: Multi-granularity Integration Network with Discrete Codebook for EEG-based Emotion Recognition",
    "TAHAG: Two-Stage Domain Adaptation With Hybrid Adaptive Graph Learning for EEG Emotion Recognition",
    "Contrastive Learning of Subject-Invariant EEG Representations for Cross-Subject Emotion Recognition",
    "GMSS: Graph-Based Multi-Task Self-Supervised Learning for EEG Emotion Recognition",
    "DMMR: Cross-Subject Domain Generalization for EEG-Based Emotion Recognition via Denoising Mixed Mutual Reconstruction",
    "Multi-Scale Hyperbolic Contrastive Learning for Cross-Subject EEG Emotion Recognition",
]

for t in TITLES:
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode({
        "query.bibliographic": t, "rows": 3, "select": "DOI,title,container-title,issued,author,type",
    })
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            d = json.load(r)
        print("\n### QUERY:", t)
        for it in d["message"]["items"]:
            title = (it.get("title") or [""])[0]
            cont = (it.get("container-title") or [""])[0]
            year = it.get("issued", {}).get("date-parts", [[None]])[0][0]
            authors = ", ".join(f"{a.get('family','')}" for a in it.get("author", [])[:4])
            print(f"  - {title} | {cont} | {year} | {authors} | https://doi.org/{it['DOI']}")
    except Exception as e:
        print("ERR", t, e)
    time.sleep(0.3)
