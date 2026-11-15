# -*- coding: utf-8 -*-
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import time

TITLES = [
    "Prototypical Contrastive Learning Temporal Dynamic Graph Convolutional Network EEG Emotion",
    "TAHAG Two-Stage Domain Adaptation Hybrid Adaptive Graph Learning EEG Emotion",
    "MIND-EEG Multi-granularity Integration Network Discrete Codebook",
    "Sera Separated Coarse-to-fine Representation Alignment Cross-subject EEG",
    "SSAS Cross-subject EEG emotion source selection adversarial",
    "Dynamic domain adaptation class-aware cross-subject cross-session EEG emotion",
    "Multimodal Semi-Supervised Domain Adaptation Cross-Modal Joint Distribution Alignment",
    "A Bi-Hemisphere Domain Adversarial Neural Network EEG Emotion",
    "CLISA Contrastive Learning Subject-Invariant EEG",
    "GMSS Graph-Based Multi-Task Self-Supervised Learning EEG",
    "DMMR Denoising Mixed Mutual Reconstruction",
    "Multi-Scale Hyperbolic Contrastive Learning Cross-Subject EEG",
    "SEED-VII multimodal dataset six basic emotions",
]

for t in TITLES:
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode({
        "search_query": f'ti:"{t}"', "max_results": 3,
    })
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            root = ET.fromstring(r.read())
        ns = {"a": "http://www.w3.org/2005/Atom"}
        print("\n###", t)
        for e in root.findall("a:entry", ns):
            title = " ".join(e.find("a:title", ns).text.split())
            link = e.find("a:id", ns).text
            print("  -", title, "|", link)
    except Exception as e:
        print("ERR", t, e)
    time.sleep(1)
