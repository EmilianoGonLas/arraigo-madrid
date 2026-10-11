# -*- coding: utf-8 -*-
"""
Rehace el archivo de VUPACI terminados a partir de lo que realmente hay en el
CSV, y limpia las filas de los VUPACI incompletos.

Hace falta porque la primera versión del descargador marcaba un VUPACI como
hecho aunque no hubiera bajado ni una variable: con la caída de internet del
2026-10-09 quedaron 242 marcados y sólo 22 con datos.

    python3 reparar_checkpoint.py
"""

import collections
import csv
import json
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DESTINO = os.path.join(RAIZ, "datos", "censo2011")
SALIDA = os.path.join(DESTINO, "panel_2011.csv")
HECHOS = os.path.join(DESTINO, "panel_2011.hechos.txt")
CONFIG = os.path.join(RAIZ, "datos", "config", "variables_2011.json")
FRACCION_MINIMA = 0.80


def main():
    n_vars = len(json.load(open(CONFIG, encoding="utf-8"))["incluidas"])
    minimo = FRACCION_MINIMA * n_vars

    filas = list(csv.DictReader(open(SALIDA, newline="", encoding="utf-8")))
    cab = filas[0].keys() if filas else []
    vars_por = collections.defaultdict(set)
    tot_por = collections.defaultdict(set)
    for r in filas:
        v = int(r["VUPACI"])
        vars_por[v].add(r["variable"])
        if r["categoria"] == "Total":
            tot_por[v].add(r["personas"])

    buenos, flojos, inconsistentes = [], [], []
    for v, s in vars_por.items():
        if len(tot_por[v]) > 1:
            inconsistentes.append(v)
        elif len(s) >= minimo:
            buenos.append(v)
        else:
            flojos.append(v)

    print(f"{n_vars} variables pedidas | mínimo para dar por bueno: {minimo:.0f}")
    print(f"  completos   : {len(buenos)} -> {sorted(buenos)}")
    print(f"  incompletos : {len(flojos)} -> {sorted(flojos)}")
    print(f"  inconsistentes: {len(inconsistentes)} -> {sorted(inconsistentes)}")

    antes = set()
    if os.path.exists(HECHOS):
        antes = {int(x) for x in open(HECHOS, encoding="utf-8").read().split()}
    print(f"\nmarcados como hechos antes: {len(antes)} | de verdad: {len(buenos)}")
    print(f"se liberan para rebajar: {len(antes) - len(buenos)}")

    descartar = set(flojos) | set(inconsistentes)
    if descartar:
        with open(SALIDA, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(cab))
            w.writeheader()
            for r in filas:
                if int(r["VUPACI"]) not in descartar:
                    w.writerow(r)
        print(f"CSV reescrito sin los VUPACI {sorted(descartar)}")

    with open(HECHOS, "w", encoding="utf-8") as f:
        for v in sorted(buenos):
            f.write(f"{v}\n")
    print(f"checkpoint rehecho: {len(buenos)} VUPACI")


if __name__ == "__main__":
    main()
