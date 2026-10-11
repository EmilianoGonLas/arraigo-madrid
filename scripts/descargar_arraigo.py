# -*- coding: utf-8 -*-
"""
Descarga, para cada VUPACI del seccionado, la distribución de personas
residentes en viviendas principales por "Año de llegada a la vivienda"
(Censo de Población y Viviendas 2011, INE).

Es exactamente la misma consulta que se hace a mano en el asistente web
—mismos municipios, mismas secciones, "desglosado = NO"— pero automatizada.
Por eso los números salen idénticos a los de la consulta manual: el INE
redondea cada consulta a múltiplos de 5, así que agregar por VUPACI *dentro*
del INE no es lo mismo que sumar secciones redondeadas.

Guarda el resultado incrementalmente en un CSV, así que se puede cortar y
retomar sin perder lo descargado.

    python3 descargar_arraigo.py [--limite N] [--pausa 0.4] [--hilos 3]

NO paralelizar. Se probó con 3 sesiones simultáneas y el INE devuelve, cada
tantas consultas, la tabla de *otra* consulta en curso: la selección geográfica
que el informe declara es la correcta, pero los números son los de otro VUPACI.
Se detectó porque 7 de 101 grupos se desviaban muchísimo del control de
población (ver verificar_arraigo.py). En secuencial no pasa.
"""

import argparse
import csv
import os
import queue
import sys
import threading
import time

import pandas as pd

import ine_censo2011 as ine

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SECCIONADO = os.path.join(RAIZ, "datos", "originales", "Seccionado VUPACI.xlsx")
SALIDA = os.path.join(RAIZ, "salidas", "arraigo_por_vupaci.csv")

COLUMNAS = ["Total", "2011", "2010", "2009", "2008", "2007", "2006",
            "2001-2005", "1991-2000", "1981-1990", "1971-1980", "Antes de 1971"]


def leer_seccionado(ruta=SECCIONADO):
    """{vupaci: [codigos de sección de 10 dígitos]} en el orden del Excel."""
    df = pd.read_excel(ruta, header=1).iloc[:, 1:3]
    df.columns = ["VUPACI", "SECCION"]
    df = df.dropna(how="any")
    df["VUPACI"] = df["VUPACI"].astype(int)
    df["SECCION"] = df["SECCION"].astype("int64").astype(str).str.zfill(10)
    grupos = {}
    for v, sub in df.groupby("VUPACI", sort=True):
        grupos[int(v)] = sub["SECCION"].tolist()
    return grupos


def _alinear(cols, crudos):
    """
    Pone los valores en el orden canónico de COLUMNAS.

    El INE **no dibuja la columna** de una categoría que no tiene ningún dato
    en el grupo consultado: la tabla vuelve con 11 columnas en vez de 12. Esas
    ausencias son ceros reales —comprobado: el total sigue cuadrando con la
    suma de las categorías presentes—, así que se rellenan con 0 y se anotan.
    """
    por_nombre = dict(zip(cols, crudos))
    desconocidas = [c for c in cols if c not in COLUMNAS]
    if desconocidas:
        raise RuntimeError(f"columnas inesperadas: {desconocidas}")
    ausentes = [c for c in COLUMNAS if c not in por_nombre]
    ordenados = [por_nombre.get(c, "0") for c in COLUMNAS]
    return [ine.a_numero(x) for x in ordenados], ordenados, ausentes


def ya_descargados(ruta=SALIDA):
    if not os.path.exists(ruta):
        return set()
    hechos = set()
    with open(ruta, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            hechos.add(int(fila["VUPACI"]))
    return hechos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=None,
                    help="procesar solo los N primeros VUPACI pendientes")
    ap.add_argument("--pausa", type=float, default=0.4,
                    help="segundos de espera entre consultas")
    ap.add_argument("--hilos", type=int, default=1,
                    help="sesiones simultáneas. OJO: con más de 1 el INE cruza "
                         "respuestas entre sesiones y devuelve la tabla de otra "
                         "consulta sin avisar. Dejar en 1.")
    args = ap.parse_args()

    grupos = leer_seccionado()
    hechos = ya_descargados()
    pendientes = [v for v in grupos if v not in hechos]
    if args.limite:
        pendientes = pendientes[:args.limite]

    print(f"{len(grupos)} VUPACI en el seccionado | "
          f"{len(hechos)} ya descargados | {len(pendientes)} por descargar")
    if not pendientes:
        return

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    nuevo = not os.path.exists(SALIDA)
    salida = open(SALIDA, "a", newline="", encoding="utf-8")
    escritor = csv.writer(salida)
    if nuevo:
        escritor.writerow(["VUPACI", "n_secciones"] + COLUMNAS
                          + ["marcadas", "ausentes"])
        salida.flush()

    cola = queue.Queue()
    for v in pendientes:
        cola.put(v)
    candado = threading.Lock()
    errores = []
    hechos_ahora = [0]

    def trabajador(n):
        sesion = ine.nueva_sesion()
        muni = ine.cargar_municipios(sesion, "28")
        while True:
            try:
                v = cola.get_nowait()
            except queue.Empty:
                return
            secciones = grupos[v]
            for intento in (1, 2, 3):
                try:
                    cols, filas = ine.consultar(sesion, secciones, muni)
                    valores, crudos, ausentes = _alinear(cols, filas[0][1])
                    aviso = "|".join(ine.marcadas(crudos, COLUMNAS))
                    with candado:
                        escritor.writerow([v, len(secciones)] + valores
                                          + [aviso, "|".join(ausentes)])
                        salida.flush()
                        hechos_ahora[0] += 1
                        print(f"[{hechos_ahora[0]}/{len(pendientes)}] "
                              f"VUPACI {v} ({len(secciones)} secc.) "
                              f"-> total {valores[0]}", flush=True)
                    break
                except Exception as e:
                    print(f"    hilo {n}, VUPACI {v}: fallo {intento}/3 -> {e}",
                          file=sys.stderr, flush=True)
                    time.sleep(2 * intento)
                    sesion = ine.nueva_sesion()      # la sesión del INE caduca
                    muni = ine.cargar_municipios(sesion, "28")
            else:
                with candado:
                    errores.append(v)
            time.sleep(args.pausa)

    hilos = [threading.Thread(target=trabajador, args=(n,), daemon=True)
             for n in range(args.hilos)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    salida.close()
    if errores:
        print(f"\nVUPACI sin descargar tras 3 intentos: {errores}")
    print(f"\nCSV: {SALIDA}")


if __name__ == "__main__":
    main()
