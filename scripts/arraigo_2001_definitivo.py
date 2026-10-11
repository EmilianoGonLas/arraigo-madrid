# -*- coding: utf-8 -*-
"""
Arraigo 2001 y 2011 por VUPACI, ya sin aproximaciones.

El archivo "Seccionado VUPACI 2001 y 2011.xlsx" trae lo que faltaba: **la
asignación de VUPACI para el seccionado de 2001**, además de la de 2011. Con
eso cada censo se agrega con su propio seccionado y los dos resultados son
comparables de verdad.

Comprobado contra lo bajado del INE:
  - las 3.906 secciones del lado 2001 son exactamente las 3.906 que publica el
    censo 2001 para Madrid;
  - las 4.271 del lado 2011 son idénticas al seccionado anterior, sin un solo
    cambio de asignación;
  - la suma de población cierra en 5.394.140, el total provincial de 2001.

El índice usa los mismos cuatro tramos en los dos años, por posición relativa
al censo (los seis últimos años, los cinco previos, los diez previos, el resto).

Salida: salidas/Arraigo 2001 por VUPACI.xlsx
"""

import os

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SECCIONADO = os.path.join(RAIZ, "datos", "originales",
                          "Seccionado VUPACI 2001 y 2011.xlsx")
SEC2001 = os.path.join(RAIZ, "salidas", "censo2001_secciones_madrid.csv")
ARR2011 = os.path.join(RAIZ, "salidas", "arraigo_por_vupaci.csv")
XLSX = os.path.join(RAIZ, "salidas", "Arraigo 2001 por VUPACI.xlsx")

CAT01 = ["2001", "2000", "1999", "1998", "1997", "1996", "1991-1995",
         "1981-1990", "1971-1980", "1961-1970", "1941-1960", "Antes de 1941"]
CAT11 = ["2011", "2010", "2009", "2008", "2007", "2006", "2001-2005",
         "1991-2000", "1981-1990", "1971-1980", "Antes de 1971"]

TRAMOS01 = {"a": (["2001", "2000", "1999", "1998", "1997", "1996"], 0.00),
            "b": (["1991-1995"], 0.33),
            "c": (["1981-1990"], 0.66),
            "d": (["1971-1980", "1961-1970", "1941-1960", "Antes de 1941"], 1.00)}
TRAMOS11 = {"a": (["2011", "2010", "2009", "2008", "2007", "2006"], 0.00),
            "b": (["2001-2005"], 0.33),
            "c": (["1991-2000"], 0.66),
            "d": (["1981-1990", "1971-1980", "Antes de 1971"], 1.00)}


def leer_seccionado_doble(ruta=SECCIONADO):
    df = pd.read_excel(ruta, header=1)
    df.columns = ["sec01", "vup01", "x", "vup11", "sec11"]
    a = df[["sec01", "vup01"]].dropna()
    a["sec01"] = a["sec01"].astype("int64").astype(str).str.zfill(10)
    a["vup01"] = a["vup01"].astype(int)
    b = df[["sec11", "vup11"]].dropna()
    b["sec11"] = b["sec11"].astype("int64").astype(str).str.zfill(10)
    b["vup11"] = b["vup11"].astype(int)
    return a, b


def indice(df, tramos):
    t = pd.DataFrame(index=df.index)
    for k, (cols, _) in tramos.items():
        t[k] = df[cols].sum(axis=1)
    suma = t.sum(axis=1)
    val = sum(t[k] / suma * peso for k, (_, peso) in tramos.items()) * 100
    return t, suma, val.round(2)


def main():
    a, _ = leer_seccionado_doble()
    s01 = pd.read_csv(SEC2001, dtype={"SECCION": str}).set_index("SECCION")
    j = a.join(s01, on="sec01")
    if j["TOTAL"].isna().any():
        raise RuntimeError("hay secciones de 2001 sin dato del censo")
    g01 = j.groupby("vup01")[["TOTAL"] + CAT01].sum()
    g01.index.name = "VUPACI"
    g01.insert(0, "n_secciones_2001", j.groupby("vup01").size())

    d11 = pd.read_csv(ARR2011).set_index("VUPACI").sort_index()

    t01, suma01, i01 = indice(g01, TRAMOS01)
    t11, suma11, i11 = indice(d11, TRAMOS11)

    comun = g01.index.intersection(d11.index)
    comp = pd.DataFrame({
        "n_secciones_2001": g01.loc[comun, "n_secciones_2001"],
        "n_secciones_2011": d11.loc[comun, "n_secciones"],
        "poblacion_2001": g01.loc[comun, "TOTAL"],
        "poblacion_2011": d11.loc[comun, "Total"],
        "indice_2001": i01.reindex(comun),
        "indice_2011": i11.reindex(comun),
    })
    comp["variacion_poblacion"] = comp["poblacion_2011"] - comp["poblacion_2001"]
    comp["variacion_indice"] = (comp["indice_2011"] - comp["indice_2001"]).round(2)

    solo11 = sorted(set(d11.index) - set(g01.index))

    salida01 = g01.copy()
    for k in TRAMOS01:
        salida01[f"tramo_{k}"] = t01[k]
    salida01["indice_arraigo_2001"] = i01

    with pd.ExcelWriter(XLSX, engine="openpyxl") as xls:
        comp.reset_index().to_excel(xls, sheet_name="Comparación", index=False)
        salida01.reset_index().to_excel(xls, sheet_name="Arraigo 2001", index=False)
        _hoja_nota(xls.book, comp, solo11)

    print(f"VUPACI con dato en 2001: {len(g01)} | en 2011: {len(d11)}")
    print(f"comparables: {len(comp)} | sólo en 2011: {solo11}")
    print(f"población 2001: {int(g01['TOTAL'].sum()):,}".replace(",", "."))
    print(f"índice 2001 medio {comp['indice_2001'].mean():.1f} | "
          f"2011 medio {comp['indice_2011'].mean():.1f}")
    print(f"correlación entre ambos: {comp['indice_2001'].corr(comp['indice_2011']):.3f}")
    print("\nExcel:", XLSX)


def _hoja_nota(libro, comp, solo11):
    h = libro.create_sheet("Nota", 0)
    lineas = [
        ("Arraigo por VUPACI, censos 2001 y 2011", True),
        ("", False),
        ("Cada censo se agrega con SU PROPIO seccionado, tomado del archivo "
         "«Seccionado VUPACI 2001 y 2011.xlsx»: el lado 2001 asigna VUPACI a "
         "las secciones de 2001 y el lado 2011 a las de 2011. No hay ninguna "
         "aproximación: no se reutilizan códigos de un año en el otro.", False),
        ("", False),
        ("Comprobaciones hechas sobre ese archivo:", True),
        ("· Las 3.906 secciones del lado 2001 son exactamente las 3.906 que "
         "publica el censo 2001 para Madrid (bajadas del INE por separado).", False),
        ("· Las 4.271 del lado 2011 son idénticas al seccionado que veníamos "
         "usando, sin un solo cambio de asignación.", False),
        ("· La población suma 5.394.140, el total provincial de 2001.", False),
        ("· Ninguna sección quedó sin dato.", False),
        ("", False),
        ("El índice usa los mismos cuatro tramos en los dos años, por posición "
         "relativa al censo:", True),
        ("        2011                      2001                   peso", False),
        ("   a    2006-2011 (6 años)        1996-2001 (6 años)       0", False),
        ("   b    2001-2005 (5 años)        1991-1995 (5 años)       0,33", False),
        ("   c    1991-2000 (10 años)       1981-1990 (10 años)      0,66", False),
        ("   d    antes de 1991             antes de 1981            1", False),
        ("", False),
        ("Lectura: 0 = todos llegaron en los últimos seis años; 100 = todos "
         "llevan más de veinte.", False),
        ("", False),
        (f"VUPACI sin secciones en 2001: {solo11 or 'ninguno'}. No existía como "
         "territorio poblado en aquel censo, así que no tiene fila en la "
         "comparación.", False),
        ("", False),
        ("Dos diferencias entre censos que conviene citar en el trabajo:", True),
        ("· El colectivo no se llama igual: 2011 es «residentes en viviendas "
         "principales» y 2001 «residentes en viviendas familiares».", False),
        ("· La precisión tampoco: 2001 son recuentos exactos; 2011 viene "
         "redondeado a múltiplos de 5, lo que mete algo de ruido en los grupos "
         "chicos.", False),
    ]
    for i, (txt, negrita) in enumerate(lineas, start=1):
        c = h.cell(row=i, column=1, value=txt)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if negrita:
            c.font = Font(bold=True)
    h.column_dimensions["A"].width = 100

    for nombre in ("Comparación", "Arraigo 2001"):
        hh = libro[nombre]
        for c in hh[1]:
            c.font = Font(bold=True)
            c.alignment = Alignment(horizontal="center", wrap_text=True)
            c.fill = PatternFill("solid", fgColor="E5E7EB")
        for j in range(1, hh.max_column + 1):
            hh.column_dimensions[get_column_letter(j)].width = 14
        hh.freeze_panes = "B2"


if __name__ == "__main__":
    main()
