# -*- coding: utf-8 -*-
"""
Reconstruye el registro de variables faltantes comparando el panel con la lista
de variables que se pidieron.

Se usa para rellenar lo ya descargado: el log sólo mostraba las tres primeras
que fallaban en cada grupo, así que no sirve como registro. Esto lo saca del
dato mismo, que es la fuente fiable.

    python3 reconstruir_faltantes.py
"""

import csv
import json
import os
import collections

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
PANEL = os.path.join(RAIZ, "datos", "censo2011", "panel_2011.csv")
CONFIG = os.path.join(RAIZ, "datos", "config", "variables_2011.json")
FALTANTES = os.path.join(RAIZ, "datos", "censo2011", "faltantes.csv")


def main():
    variables = json.load(open(CONFIG, encoding="utf-8"))["incluidas"]
    rama_de = {d["nombre"]: d["rama"] for d in variables}
    pedidas = set(rama_de)

    tiene = collections.defaultdict(set)
    with open(PANEL, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            tiene[int(r["VUPACI"])].add(r["variable"])

    # las que nunca volvieron para NINGÚN grupo son rechazos sistemáticos del
    # INE (p. ej. por secreto estadístico), no fallos sueltos: no se reintentan
    nunca = pedidas - set().union(*tiene.values()) if tiene else set()
    recuperables = pedidas - nunca

    filas = []
    for v in sorted(tiene):
        for nombre in sorted(recuperables - tiene[v]):
            filas.append(["(reconstruido)", v, rama_de[nombre], nombre])

    previas = set()
    if os.path.exists(FALTANTES):
        with open(FALTANTES, newline="", encoding="utf-8") as f:
            previas = {(r["VUPACI"], r["variable"]) for r in csv.DictReader(f)}

    nuevo = not os.path.exists(FALTANTES)
    with open(FALTANTES, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["momento", "VUPACI", "rama", "variable"])
        n = 0
        for fila in filas:
            if (str(fila[1]), fila[3]) not in previas:
                w.writerow(fila); n += 1

    print(f"variables pedidas            : {len(pedidas)}")
    print(f"nunca devueltas por el INE   : {len(nunca)}")
    for x in sorted(nunca):
        print(f"    · {x}")
    print(f"VUPACI revisados             : {len(tiene)}")
    print(f"huecos recuperables anotados : {n}")
    for fila in filas[:10]:
        print(f"    VUPACI {fila[1]}: {fila[3]}")


if __name__ == "__main__":
    main()
