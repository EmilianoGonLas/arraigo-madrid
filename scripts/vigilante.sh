#!/usr/bin/env bash
# Vigila la descarga del panel 2011: la relanza si se cayó Y si se atascó.
#
# Hace falta porque el asistente del INE falla de forma intermitente y el
# proceso puede quedar inservible sin morirse. Dos averías comprobadas:
#
#  - 2026-10-13: el proceso murió y estuvo doce horas parado sin que nadie
#    se enterara. Para eso bastaba comprobar que existiera.
#  - 2026-10-17: el proceso seguía vivo pero llevaba CUATRO HORAS con el
#    100 % de las sondas en HTTP 500, mientras curl y requests desde otro
#    proceso contra la misma URL y la misma IP daban 200 el 70 % de las
#    veces. Nunca se recuperó solo; un proceso nuevo pasó la sonda al
#    primer intento. El panel estuvo 39 horas sin crecer y el vigilante
#    no vio nada, porque sólo miraba el pgrep.
#
# De ahí la regla de atasco: si el CSV no crece en ATASCO_MIN minutos con el
# proceso vivo, el proceso no sirve y se reemplaza. Un grupo tarda entre 6 y
# 20 minutos, así que 90 es holgado hasta para una tanda de esperas largas.
#
# Se instala en el cron del usuario y corre cada 15 minutos.
# No hace nada si la descarga avanza o si ya terminó.

set -uo pipefail

RAIZ="/mnt/Mec/Proyectos/academico/Miri/secciones-censales-es"
SCRIPTS="$RAIZ/scripts"
DATOS="$RAIZ/datos/censo2011"
LOG="$DATOS/log_panel_laptop.txt"
BITACORA="$DATOS/vigilante.log"
LOCK="$DATOS/.vigilante.lock"
CSV="$DATOS/panel_2011.csv"
TOTAL=489
ATASCO_MIN=90

anotar () { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$BITACORA"; }

# un solo vigilante a la vez
exec 9>"$LOCK"
flock -n 9 || exit 0

HECHOS=$(wc -l < "$DATOS/panel_2011.hechos.txt" 2>/dev/null || echo 0)
if [ "$HECHOS" -ge "$TOTAL" ]; then
  anotar "terminado: $HECHOS/$TOTAL VUPACI, el vigilante ya no hace falta"
  exit 0
fi

# pgrep puede devolver varios: dos procesos escribiendo el mismo CSV lo
# corrompen, así que sobra el más viejo y se queda el último.
mapfile -t VIVOS < <(pgrep -f "descargar_panel_2011[.]py" | sort -n)

if [ "${#VIVOS[@]}" -gt 1 ]; then
  anotar "ATENCIÓN: ${#VIVOS[@]} procesos a la vez (${VIVOS[*]}), dejo sólo el último"
  for p in "${VIVOS[@]:0:${#VIVOS[@]}-1}"; do kill -9 "$p" 2>/dev/null; done
  exit 0
fi

MOTIVO=""
if [ "${#VIVOS[@]}" -eq 0 ]; then
  MOTIVO="caída"
else
  # Un proceso que está esperando una incidencia declarada del INE no está
  # atascado: está haciendo lo correcto. Reemplazarlo no arregla nada y
  # reinicia la espera, así que en ese caso no se toca.
  if tail -5 "$LOG" 2>/dev/null | grep -q "avisa de una incidencia"; then
    exit 0
  fi

  # vivo: ¿avanza? el CSV se reescribe al cerrar cada VUPACI
  if [ -f "$CSV" ] && [ -n "$(find "$CSV" -mmin +$ATASCO_MIN 2>/dev/null)" ]; then
    QUIETO=$(( ( $(date +%s) - $(stat -c %Y "$CSV") ) / 60 ))
    MOTIVO="atasco: el panel no crece desde hace $QUIETO min"
    anotar "$MOTIVO, mato ${VIVOS[0]} y relanzo"
    kill -9 "${VIVOS[0]}" 2>/dev/null
    sleep 3
  else
    exit 0                    # avanza, nada que hacer
  fi
fi

anotar "$MOTIVO con $HECHOS/$TOTAL hechos, relanzando"
tail -3 "$LOG" 2>/dev/null | sed 's/^/    /' >> "$BITACORA"

cd "$SCRIPTS" || exit 1
echo "[$(date '+%F %T')] vigilante: relanzado por $MOTIVO" >> "$LOG"
nohup python3 -u descargar_panel_2011.py --pausa 0.2 >> "$LOG" 2>&1 &
sleep 10

if pgrep -f "descargar_panel_2011[.]py" > /dev/null; then
  anotar "relanzada correctamente"
else
  anotar "ATENCIÓN: el relanzamiento falló"
fi
