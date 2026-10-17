# -*- coding: utf-8 -*-
"""
Auditoría completa del panel 2011 antes de publicarlo.

verificar_panel.py compara el Total de cada VUPACI contra la base de arraigo,
que salió del mismo asistente del INE: sirve para detectar respuestas cruzadas,
pero es un control interno. Esto va más lejos y mira cinco cosas distintas:

 1. estructura    duplicados, Totales que falten, valores no numéricos
 2. coherencia    el Total tiene que ser idéntico en las 78 variables
 3. agregación    las categorías de cada variable deben sumar su Total
 4. secreto       el 2011 va redondeado a múltiplos de 5; comprobarlo
 5. control       población por VUPACI según el fichero masivo de indicadores
                  por sección censal (t1_1), que es una fuente independiente
                  del asistente: se descarga aparte y no pasa por la sesión

    python3 auditar_panel.py
"""

import os
import sys

import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
PANEL = os.path.join(RAIZ, "datos", "censo2011", "panel_2011.csv")
SECCIONADO = os.path.join(RAIZ, "datos", "originales", "Seccionado VUPACI.xlsx")
INDICADORES = os.path.join(RAIZ, "datos", "ine", "csv",
                           "C2011_ccaa13_Indicadores.csv")
TOTAL_VUPACI = 489

# Variables cuyas categorías NO suman el Total porque son jerárquicas o
# admiten respuesta múltiple. Se detectan solas, pero se dejan dichas.
problemas = []


def avisar(grave, titulo, detalle=""):
    marca = "FALLA" if grave else "aviso"
    problemas.append((grave, titulo))
    print(f"  [{marca}] {titulo}")
    if detalle:
        print(detalle)


def main():
    df = pd.read_csv(PANEL)
    print(f"panel: {len(df):,} filas | {df.VUPACI.nunique()} VUPACI | "
          f"{df.variable.nunique()} variables | {df.rama.nunique()} ramas\n")

    # ---------------------------------------------------------------- 1
    print("1. ESTRUCTURA")
    dup = df.duplicated(subset=["VUPACI", "variable", "categoria"]).sum()
    if dup:
        avisar(True, f"{dup} filas duplicadas (VUPACI, variable, categoría)")
    else:
        print("  sin duplicados")

    nn = df["personas"].isna().sum()
    if nn:
        avisar(False, f"{nn} celdas sin valor numérico")
    else:
        print("  todas las celdas son numéricas")

    neg = (df["personas"] < 0).sum()
    if neg:
        avisar(True, f"{neg} valores negativos")
    else:
        print("  ningún valor negativo")

    tot = df[df.categoria == "Total"]
    sin_total = (df.groupby(["VUPACI", "variable"]).size().index
                 .difference(tot.set_index(["VUPACI", "variable"]).index))
    if len(sin_total):
        avisar(True, f"{len(sin_total)} pares (VUPACI, variable) sin fila Total",
               "        " + str(list(sin_total)[:5]))
    else:
        print("  toda variable de todo VUPACI tiene su Total")

    # ---------------------------------------------------------------- 2
    print("\n2. COHERENCIA INTERNA (el Total no depende de la variable)")
    por_v = tot.groupby("VUPACI")["personas"].nunique()
    malos = por_v[por_v > 1]
    if len(malos):
        avisar(True, f"{len(malos)} VUPACI con Totales distintos entre variables",
               "        " + str(malos.head().to_dict()))
    else:
        print(f"  {len(por_v)} VUPACI con un Total único en sus variables")

    # ---------------------------------------------------------------- 3
    print("\n3. AGREGACIÓN (las categorías suman el Total)")
    sumas = (df[df.categoria != "Total"].groupby(["VUPACI", "variable"])
             ["personas"].sum().rename("suma"))
    comp = pd.concat([sumas, tot.set_index(["VUPACI", "variable"])
                      ["personas"].rename("total")], axis=1).dropna()
    comp["dif"] = comp["suma"] - comp["total"]
    # el redondeo a 5 mete ruido: hasta 5 por categoría es esperable
    ncat = df[df.categoria != "Total"].groupby(["VUPACI", "variable"]).size()
    comp["holgura"] = 5 * ncat.reindex(comp.index).fillna(1)
    fuera = comp[comp["dif"].abs() > comp["holgura"]]
    por_var = (fuera.reset_index().groupby("variable").size()
               .sort_values(ascending=False))
    if len(fuera):
        avisar(False, f"{len(fuera):,} pares fuera de la holgura del redondeo, "
                      f"concentrados en {len(por_var)} variables")
        for v, n in por_var.head(8).items():
            med = fuera.reset_index().query("variable == @v")["dif"].median()
            print(f"        {n:5}  {v[:52]:52} mediana {med:+.0f}")
    else:
        print("  todo cuadra dentro de la holgura del redondeo")

    # ---------------------------------------------------------------- 4
    print("\n4. SECRETO ESTADÍSTICO (2011 va redondeado a múltiplos de 5)")
    vals = df["personas"].dropna()
    no5 = (vals % 5 != 0).sum()
    print(f"  {len(vals) - no5:,} de {len(vals):,} celdas son múltiplo de 5 "
          f"({100 * (len(vals) - no5) / len(vals):.1f} %)")
    if no5 / len(vals) > 0.02:
        avisar(False, f"{no5:,} celdas no son múltiplo de 5")
    marcadas = (df["marcada"] == "sí").sum()
    print(f"  {marcadas:,} celdas marcadas con * (fiabilidad baja)")

    # ---------------------------------------------------------------- 5
    print("\n5. CONTROL INDEPENDIENTE (fichero masivo de indicadores, t1_1)")
    if not (os.path.exists(SECCIONADO) and os.path.exists(INDICADORES)):
        avisar(False, "falta el seccionado o el fichero de indicadores")
    else:
        sec = pd.read_excel(SECCIONADO, header=1).iloc[:, 1:3]
        sec.columns = ["VUPACI", "SECCION"]
        sec = sec.dropna(how="any")
        sec["VUPACI"] = sec["VUPACI"].astype(int)
        sec["SECCION"] = (sec["SECCION"].astype("int64").astype(str)
                          .str.zfill(10))
        ind = pd.read_csv(INDICADORES, dtype=str)
        ind["SECCION"] = (ind["cpro"].str.zfill(2) + ind["cmun"].str.zfill(3)
                          + ind["dist"].str.zfill(2) + ind["secc"].str.zfill(3))
        ind["t1_1"] = pd.to_numeric(ind["t1_1"], errors="coerce")
        pob = (sec.merge(ind[["SECCION", "t1_1"]], on="SECCION", how="left")
                  .groupby("VUPACI")["t1_1"].sum())

        nuestro = tot.groupby("VUPACI")["personas"].max()
        comun = nuestro.index.intersection(pob.index)
        rel = ((nuestro[comun] - pob[comun]).abs() / pob[comun] * 100)
        print(f"  {len(comun)} VUPACI cruzados contra el control")
        print(f"  desviación: mediana {rel.median():.3f} %  |  "
              f"p95 {rel.quantile(.95):.2f} %  |  máx {rel.max():.2f} %")
        graves = rel[rel > 2.0]
        if len(graves):
            avisar(True, f"{len(graves)} VUPACI con más de 2 % de desviación")
            for v, r in graves.sort_values(ascending=False).head(10).items():
                print(f"        VUPACI {v}: {int(nuestro[v])} vs "
                      f"{int(pob[v])} ({r:+.2f} %)")
        else:
            print("  ningún VUPACI por encima del 2 % de desviación")

    # ---------------------------------------------------------------- resumen
    print("\n" + "=" * 62)
    hechos = df.VUPACI.nunique()
    print(f"COBERTURA: {hechos}/{TOTAL_VUPACI} VUPACI "
          f"({100 * hechos / TOTAL_VUPACI:.1f} %) | "
          f"{int(tot.groupby('VUPACI')['personas'].max().sum()):,} personas")
    fallas = [t for g, t in problemas if g]
    avisos = [t for g, t in problemas if not g]
    if fallas:
        print(f"FALLAS ({len(fallas)}): " + "; ".join(fallas))
    else:
        print("FALLAS: ninguna")
    if avisos:
        print(f"avisos ({len(avisos)}): " + "; ".join(avisos))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
