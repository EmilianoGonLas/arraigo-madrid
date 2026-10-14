# -*- coding: utf-8 -*-
"""
Control externo del panel: el total de personas de cada VUPACI tiene que
coincidir con el que ya habíamos bajado y verificado en
salidas/arraigo_por_vupaci.csv.

Es el único control que detecta un cruce de respuestas del INE en el que
TODAS las variables de un grupo vinieron de otra consulta: en ese caso los
totales son consistentes entre sí, pero no son los del grupo que se pidió.

    python3 verificar_panel.py [ruta_al_panel.csv]
"""

import collections
import csv
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
REFERENCIA = os.path.join(RAIZ, "salidas", "arraigo_por_vupaci.csv")


def main():
    panel = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        RAIZ, "datos", "censo2011", "panel_2011.csv")

    ref = {}
    with open(REFERENCIA, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ref[int(r["VUPACI"])] = int(r["Total"])

    tot = collections.defaultdict(set)
    nvar = collections.defaultdict(set)
    with open(panel, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = int(r["VUPACI"])
            nvar[v].add(r["variable"])
            if r["categoria"] == "Total" and r["personas"]:
                tot[v].add(int(r["personas"]))

    internos, externos, ok = [], [], 0
    for v, s in sorted(tot.items()):
        if len(s) > 1:
            internos.append((v, sorted(s)))
        elif ref.get(v) is not None and next(iter(s)) != ref[v]:
            externos.append((v, next(iter(s)), ref[v]))
        else:
            ok += 1

    print(f"panel: {os.path.basename(panel)}")
    print(f"  VUPACI con datos          : {len(tot)}")
    print(f"  variables por VUPACI      : {sorted({len(s) for s in nvar.values()})}")
    print(f"  coinciden con la referencia: {ok}")
    print(f"  totales inconsistentes    : {len(internos)} {internos[:5]}")
    print(f"  NO coinciden (cruce)      : {len(externos)}")
    for v, a, b in externos[:10]:
        print(f"      VUPACI {v}: panel {a} vs referencia {b}")
    return 1 if (internos or externos) else 0


if __name__ == "__main__":
    sys.exit(main())
