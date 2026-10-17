# -*- coding: utf-8 -*-
"""
Baja el censo 2011 completo por VUPACI: todas las variables de la lista de
configuración, en formato largo.

Truco que hace esto viable: la selección geográfica se puede **reusar**. Se fija
el VUPACI una vez (unos 10 s de los tres pasos del asistente) y después se piden
las variables una tras otra contra Informe.do, a unos 5 s cada una. Sin eso
habría que rehacer el asistente entero por variable y costaría el triple.

REGLA IMPORTANTE: una sola sesión contra el INE a la vez **en toda la red**. Con
dos procesos simultáneos el servidor devuelve la tabla de otra consulta en
curso, sin avisar y con pinta de dato bueno.

Salida (una fila por VUPACI, variable y categoría):
    datos/censo2011/panel_2011.csv

Se puede cortar y retomar: anota en un archivo aparte los VUPACI terminados.

    python3 descargar_panel_2011.py [--limite N] [--desde V]
"""

import argparse
import csv
import json
import os
import sys
import time

import requests

import ine_censo2011 as ine
from descargar_arraigo import leer_seccionado

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
CONFIG = os.path.join(RAIZ, "datos", "config", "variables_2011.json")
DESTINO = os.path.join(RAIZ, "datos", "censo2011")
SALIDA = os.path.join(DESTINO, "panel_2011.csv")
HECHOS = os.path.join(DESTINO, "panel_2011.hechos.txt")
PROGRESO = os.path.join(DESTINO, "progreso.csv")
RESPALDO = os.path.join(DESTINO, "panel_2011.respaldo.csv")
# registro de las variables que el INE no devolvió, para pedirlas después
FALTANTES = os.path.join(DESTINO, "faltantes.csv")
QUEMADOS = os.path.join(DESTINO, "quemados.csv")
CADA = 5          # cada cuántos VUPACI se deja registro y respaldo

# Se puede correr una segunda instancia en OTRA MÁQUINA empezando por el final
# (--inverso --sufijo loquesea), para que las dos se encuentren en el medio.
# OJO: con dos sesiones en la MISMA máquina el INE cruza respuestas. Desde IPs
# distintas se comprobó que no pasa, pero hay que validar con
# verificar_panel.py, que compara contra los totales ya conocidos.

# un VUPACI sólo se da por bueno si volvió al menos esta fracción de las
# variables pedidas. Sin esto, una caída de red marca como "hecho" un VUPACI
# del que no se bajó nada: pasó el 2026-10-09 y se perdieron 220 grupos.
FRACCION_MINIMA = 0.80
AVISO_CAIDA = "no funciona con normalidad"


def esperar_red(intentos=None):
    """Bloquea hasta que el INE vuelva a responder. Devuelve los minutos esperados."""
    # El asistente de 2011 devuelve 500 y 404 de forma intermitente: el
    # mismo pedido falla y al segundo siguiente responde 200. Comprobado
    # el 2026-10-13 con dos curl seguidos (500 y luego 200), mientras el
    # resto de ine.es y el sistema de 2001 respondían bien.
    #
    # Por eso conviene reintentar rápido y muchas veces antes de dormir en
    # serio. Con el backoff anterior (duplicando hasta 600 s) un fallo de
    # dos segundos costaba veinte minutos de reloj.
    # Dos averías distintas, comprobadas en los logs:
    #  - HTTP 500/404 intermitentes (122 el 14/10, de 03 a 07 h): el servidor
    #    está en pie y falla un pedido suelto. Se arregla reintentando rápido.
    #  - ConnectTimeout sostenido (250 el 14/10, de 10:34 a 20:45, diez horas
    #    clavadas): no entra ni el SYN, mientras el resto de internet anda.
    #    Ahí reintentar cada dos minutos no sirve de nada y, si lo que hay
    #    del otro lado es un bloqueo por IP, lo único que hace es alimentarlo.
    # El escalón largo que probé el 14/10 (300 s y 600 s tras un rato) resultó
    # contraproducente: el 17/10 un proceso quedó cuatro horas sondeando cada
    # diez minutos, siempre 500, mientras otro proceso contra la misma URL y la
    # misma IP sacaba 200 el 70 % de las veces. Un proceso así no se arregla
    # esperando más, se arregla reemplazándolo, y de eso se ocupa vigilante.sh
    # cuando ve que el panel dejó de crecer. Acá la espera no pasa de 120 s.
    esperas = [2, 2, 5, 5, 10, 15, 30, 60, 120]
    i_espera, total = 0, 0
    while intentos is None or intentos > 0:
        espera = esperas[min(i_espera, len(esperas) - 1)]
        try:
            r = requests.get(ine.BASE + "Inicio.do", timeout=30)
            # El INE avisa de sus incidencias en el cuerpo de la respuesta:
            # "Debido a cuestiones técnicas, la web del INE no funciona con
            # normalidad. Por favor, inténtelo más tarde". Eso no es un 500
            # suelto que convenga reintentar a los dos segundos, es una caída
            # declarada que dura horas (la del 16/10/2026 se llevó dos días).
            # Distinguirla sirve para dos cosas: no machacarles el servidor
            # mientras lo arreglan, y dejarlo dicho en el log en lugar de
            # acumular mil líneas de "no responde" sin explicación.
            if AVISO_CAIDA in r.text:
                print(f"    [{time.strftime('%H:%M:%S')}] el INE avisa de una "
                      f"incidencia en su web; espero 15 min", file=sys.stderr,
                      flush=True)
                time.sleep(900)
                total += 900
                if intentos is not None:
                    intentos -= 1
                continue
            r.raise_for_status()
            if total:
                print(f"    [{time.strftime('%H:%M:%S')}] el INE volvió tras "
                      f"{total}s", flush=True)
            return total
        except Exception as e:
            # anotar la CAUSA: no es lo mismo que se caiga la red local a que
            # el INE devuelva 503 o corte la conexión. Las esperas largas
            # observadas (166 y 206 min, las dos de madrugada) apuntan a una
            # ventana de mantenimiento del INE, no a la conexión de casa.
            causa = type(e).__name__
            resp = getattr(e, "response", None)
            if resp is not None:
                causa = f"HTTP {resp.status_code}"
            print(f"    [{time.strftime('%H:%M:%S')}] el INE no responde "
                  f"({causa}), reintento en {espera}s",
                  file=sys.stderr, flush=True)
            time.sleep(espera)
            total += espera
            i_espera += 1
            if intentos is not None:
                intentos -= 1
    return total


def fijar_geografia(sesion, secciones, muni):
    cods = sorted({s[:5] for s in secciones})
    nombres = {c: muni[c].split(".")[-1].strip("[]")[6:] for c in cods}
    ine._post(sesion, ine.BASE + "Wizard.do", {
        "reqCode": "paso4", "WIZARD": "6",
        "areaOrigen": "municipios-seccionescensales",
        "idComunidad": "", "idProvincia": "", "municipios": "",
        "idMunicipio": [muni[c] for c in cods], "subtipoInfra": "S"})
    r = ine._post(sesion, ine.BASE + "Wizard.do", {
        "reqCode": "paso5", "WIZARD": "6", "areaOrigen": "seccionescensales",
        "idDistrito": "", "idSeccion": "",
        "elementosGeograficosOrigenSeleccionados":
            [ine.clave_seccion(s, nombres[s[:5]]) for s in secciones],
        "desglose": "NO"})
    ine._verificar_ambito(r.text, secciones)
    ine._get(sesion, ine.BASE + "Wizard.do?WIZARD=1&reqCode=paso2")


def pedir(sesion, clave):
    """Una variable en columnas. Devuelve (categorías, valores crudos)."""
    r = ine._post(sesion, ine.BASE + "Informe.do", {
        "reqCode": "iniciar", "jerarquiasSeleccionada": "", "WIZARD": "2",
        "pagina4": "6", "tipoInforme": "LIBRE",
        "idColumna": clave, "medidas": ine.MEDIDA_PERSONAS})
    cols, filas = ine._parsear_tabla(r.text)
    return cols, filas[0][1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=None)
    ap.add_argument("--pausa", type=float, default=0.2)
    ap.add_argument("--inverso", action="store_true",
                    help="recorrer los VUPACI del último al primero")
    ap.add_argument("--sufijo", default="",
                    help="sufijo para los archivos de salida, para no pisar "
                         "los de la otra máquina")
    ap.add_argument("--cada", type=int, default=CADA,
                    help="cada cuántos VUPACI dejar registro y respaldo")
    ap.add_argument("--excluir", default=None,
                    help="archivo con VUPACI ya hechos por la otra máquina")
    args = ap.parse_args()

    global SALIDA, HECHOS
    if args.sufijo:
        SALIDA = os.path.join(DESTINO, f"panel_2011_{args.sufijo}.csv")
        HECHOS = os.path.join(DESTINO, f"panel_2011_{args.sufijo}.hechos.txt")

    variables = json.load(open(CONFIG, encoding="utf-8"))["incluidas"]
    grupos = leer_seccionado()
    os.makedirs(DESTINO, exist_ok=True)

    hechos = set()
    if os.path.exists(HECHOS):
        hechos = {int(x) for x in open(HECHOS, encoding="utf-8").read().split()}
    if args.excluir and os.path.exists(args.excluir):
        ajenos = {int(x) for x in open(args.excluir, encoding="utf-8").read().split()}
        hechos |= ajenos
        print(f"excluidos por la otra máquina: {len(ajenos)}", flush=True)
    pendientes = sorted((v for v in grupos if v not in hechos),
                        reverse=args.inverso)
    if args.limite:
        pendientes = pendientes[:args.limite]

    print(f"{len(variables)} variables x {len(grupos)} VUPACI | "
          f"{len(hechos)} VUPACI hechos | {len(pendientes)} pendientes",
          flush=True)
    estimado = len(pendientes) * (10 + len(variables) * 4.8) / 3600
    print(f"estimación: {estimado:.1f} horas", flush=True)

    nuevo = not os.path.exists(SALIDA)
    f = open(SALIDA, "a", newline="", encoding="utf-8")
    w = csv.writer(f)
    if nuevo:
        w.writerow(["VUPACI", "rama", "variable", "categoria", "personas",
                    "marcada"])
        f.flush()
    marcas = open(HECHOS, "a", encoding="utf-8")

    nuevo_falt = not os.path.exists(FALTANTES)
    falt = open(FALTANTES, "a", newline="", encoding="utf-8")
    wfalt = csv.writer(falt)
    if nuevo_falt:
        wfalt.writerow(["momento", "VUPACI", "rama", "variable"])
        falt.flush()

    nuevo_prog = not os.path.exists(PROGRESO)
    prog = open(PROGRESO, "a", newline="", encoding="utf-8")
    wprog = csv.writer(prog)
    if nuevo_prog:
        wprog.writerow(["momento", "vupaci_hechos", "pendientes", "ultimo",
                        "filas", "seg_por_grupo", "horas_restantes",
                        "totales_ok"])
        prog.flush()

    def dejar_registro(hechos_ahora, pendientes_ahora, ultimo, seg):
        """Respalda el CSV y anota una línea de progreso verificada."""
        # control rápido: dentro de cada VUPACI el total debe ser único
        tot = {}
        with open(SALIDA, newline="", encoding="utf-8") as g:
            for r in csv.DictReader(g):
                if r["categoria"] == "Total" and r["personas"]:
                    tot.setdefault(int(r["VUPACI"]), set()).add(int(r["personas"]))
        malos = [v for v, s_ in tot.items() if len(s_) > 1]
        with open(SALIDA, "rb") as a, open(RESPALDO, "wb") as b:
            b.write(a.read())
        n_filas = sum(1 for _ in open(SALIDA, encoding="utf-8")) - 1
        wprog.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), hechos_ahora,
                        pendientes_ahora, ultimo, n_filas, round(seg, 1),
                        round(pendientes_ahora * seg / 3600, 1),
                        "sí" if not malos else f"NO: {malos[:5]}"])
        prog.flush()
        print(f"    · registro: {hechos_ahora} hechos, {n_filas} filas, "
              f"respaldo guardado, totales {'ok' if not malos else 'CON PROBLEMAS'}",
              flush=True)

    def nueva_sesion_firme():
        """
        Abre sesión insistiendo indefinidamente.

        NO se rinde a propósito. La versión con 20 intentos agotaba sus diez
        minutos y mataba el proceso: el 2026-10-13 eso costó doce horas de
        descarga parada, con el INE respondiendo bien mucho antes. Esto corre
        desatendido, así que ante un servidor intermitente lo correcto es
        esperar, no abandonar.
        """
        intento = 0
        while True:
            intento += 1
            try:
                esperar_red()
                s_ = ine.nueva_sesion()
                return s_, ine.cargar_municipios(s_, "28")
            except Exception as e:
                espera = min(5 * intento, 45)
                print(f"    [{time.strftime('%H:%M:%S')}] no se pudo abrir "
                      f"sesión ({type(e).__name__}), intento {intento}, "
                      f"reintento en {espera}s", file=sys.stderr, flush=True)
                time.sleep(espera)

    sesion, muni = nueva_sesion_firme()
    t_inicio = time.time()

    quemados = []
    bajados = 0
    # Esperas entre tandas cuando el grupo devuelve CERO variables.
    ESPERAS_TANDA = [300, 600, 1200, 1800, 1800]

    for i, v in enumerate(pendientes, 1):
        t0 = time.time()
        filas_v, fallos, hechas = [], [], 0
        logrado = False

        # Un grupo que devuelve CERO variables no tiene un problema propio:
        # el que está roto es el INE. Comprobado el 16/10/2026: con Inicio.do
        # contestando 200 (o sea, esperar_red() daba vía libre y no anotó un
        # solo fallo), el asistente devolvía 500 a cada consulta, y la corrida
        # se comió diecinueve grupos seguidos -del 249 al 267- a cinco vueltas
        # cada uno, sin bajar una sola fila. Por eso el cero ya no hace avanzar
        # la lista: espera y reintenta EL MISMO grupo. Que baje algunas
        # variables sí es cosa del grupo, y entonces se lo deja atrás.
        for tanda in range(len(ESPERAS_TANDA) + 1):
            if tanda:
                espera = ESPERAS_TANDA[tanda - 1]
                print(f"    VUPACI {v}: cero variables en cinco vueltas, el INE "
                      f"debe estar roto; espero {espera // 60} min y repito "
                      f"el mismo grupo", file=sys.stderr, flush=True)
                time.sleep(espera)
                try:
                    sesion, muni = nueva_sesion_firme()
                except Exception:
                    pass

            for vuelta in range(1, 6):      # el VUPACI se reintenta entero
                filas_v, fallos, totales = [], [], set()
                esperar_red()
                try:
                    fijar_geografia(sesion, grupos[v], muni)
                except Exception as e:
                    print(f"    VUPACI {v}: geografía falló ({e}), vuelta {vuelta}",
                          file=sys.stderr, flush=True)
                    esperar_red()
                    try:
                        sesion, muni = nueva_sesion_firme()
                    except Exception:
                        pass
                    continue

                for d in variables:
                    try:
                        cols, crudos = pedir(sesion, d["clave"])
                        nums = [ine.a_numero(x) for x in crudos]
                        # El INE puede devolver la tabla TRUNCADA: el Total
                        # correcto pero sólo parte de las categorías. Pasaba
                        # inadvertido porque el Total cuadraba con el control
                        # de población. Comprobado el 17/10/2026 en 2 de 24.991
                        # pares: al VUPACI 142 le faltaban 3 de 9 categorías de
                        # "Tipo de estudios completados", o sea 6.945 personas,
                        # y al 237 dos tramos de "Año de construcción".
                        # Las categorías tienen que sumar el Total; el redondeo
                        # a múltiplos de 5 deja un margen de 5 por categoría
                        # (el 99,99 % de los pares buenos cae dentro de ±20).
                        suma = sum(n for c, n in zip(cols, nums)
                                   if c != "Total" and n is not None)
                        total_d = next((n for c, n in zip(cols, nums)
                                        if c == "Total"), None)
                        ncat = max(1, sum(1 for c in cols if c != "Total"))
                        if (total_d is not None
                                and abs(suma - total_d) > 5 * ncat):
                            raise ValueError(
                                f"tabla truncada: las categorías suman {suma} "
                                f"y el Total dice {total_d}")
                        for cat, n, val in zip(cols, nums, crudos):
                            if cat == "Total":
                                totales.add(n)
                            filas_v.append([v, d["rama"], d["nombre"], cat, n,
                                            "sí" if "*" in (val or "") else ""])
                    except Exception:
                        fallos.append((d["rama"], d["nombre"]))
                        time.sleep(1)

                hechas = len(variables) - len(fallos)
                # el total de personas tiene que ser el mismo en todas las
                # variables; si no, el INE cruzó respuestas y el grupo no sirve
                if len(totales) > 1:
                    print(f"    VUPACI {v}: totales inconsistentes {sorted(totales)}, "
                          f"se descarta y se repite", file=sys.stderr, flush=True)
                    hechas = 0          # cruce = problema del servidor, reintentar
                    sesion, muni = nueva_sesion_firme()
                    continue
                if hechas >= FRACCION_MINIMA * len(variables):
                    break
                print(f"    VUPACI {v}: sólo {hechas}/{len(variables)} variables, "
                      f"vuelta {vuelta}", file=sys.stderr, flush=True)
                esperar_red()
                try:
                    sesion = ine.nueva_sesion()
                    muni = ine.cargar_municipios(sesion, "28")
                except Exception:
                    pass

            if hechas >= FRACCION_MINIMA * len(variables):
                logrado = True
                break
            if hechas:
                break           # bajó algo: es el grupo, no el servidor

        if not logrado:
            print(f"    VUPACI {v}: NO se pudo bajar, queda pendiente",
                  file=sys.stderr, flush=True)
            quemados.append(v)
            with open(QUEMADOS, "a", encoding="utf-8") as q:
                q.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},{v},{hechas}\n")
            continue
        bajados += 1

        for fila in filas_v:
            w.writerow(fila)
        f.flush()
        for rama, nombre in fallos:
            wfalt.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), v, rama, nombre])
        if fallos:
            falt.flush()
        marcas.write(f"{v}\n")
        marcas.flush()
        restante = (len(pendientes) - i) * (time.time() - t_inicio) / i / 3600
        print(f"[{i}/{len(pendientes)}] VUPACI {v}: {hechas}/{len(variables)} "
              f"variables en {time.time()-t0:.0f}s | faltan {restante:.1f} h"
              + (f" | faltaron {len(fallos)}: "
                 f"{[n for _, n in fallos][:3]}" if fallos else ""), flush=True)
        if args.cada and i % args.cada == 0:
            dejar_registro(len(hechos) + bajados, len(pendientes) - i, v,
                           (time.time() - t_inicio) / i)
        time.sleep(args.pausa)

    if pendientes:
        dejar_registro(len(hechos) + bajados, len(quemados), pendientes[-1],
                       (time.time() - t_inicio) / max(1, len(pendientes)))
    if quemados:
        print(f"\nquedaron {len(quemados)} VUPACI sin bajar: {quemados}\n"
              f"están anotados en {QUEMADOS} y vuelven solos a la cola "
              f"en el próximo arranque", flush=True)
    f.close()
    marcas.close()
    prog.close()
    falt.close()
    print("\nCSV:", SALIDA)


if __name__ == "__main__":
    main()
