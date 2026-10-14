#!/usr/bin/env bash
# Vigila la descarga del panel 2011 y la relanza si se cayó.
#
# Hace falta porque el asistente del INE falla de forma intermitente y el
# proceso puede morir sin que nadie se entere: el 2026-10-13 estuvo doce horas
# parado. Se instala en el cron del usuario y corre cada 15 minutos.
#
# No hace nada si la descarga está corriendo o si ya terminó.

set -uo pipefail

RAIZ="/mnt/Mec/Proyectos/academico/Miri/secciones-censales-es"
SCRIPTS="$RAIZ/scripts"
DATOS="$RAIZ/datos/censo2011"
LOG="$DATOS/log_panel_laptop.txt"
BITACORA="$DATOS/vigilante.log"
LOCK="$DATOS/.vigilante.lock"
TOTAL=489

anotar () { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$BITACORA"; }

# un solo vigilante a la vez
exec 9>"$LOCK"
flock -n 9 || exit 0

if pgrep -f "descargar_panel_2011[.]py" > /dev/null; then
  exit 0                      # va bien, nada que hacer
fi

HECHOS=$(wc -l < "$DATOS/panel_2011.hechos.txt" 2>/dev/null || echo 0)
if [ "$HECHOS" -ge "$TOTAL" ]; then
  anotar "terminado: $HECHOS/$TOTAL VUPACI, el vigilante ya no hace falta"
  exit 0
fi

anotar "caída detectada con $HECHOS/$TOTAL hechos, relanzando"
tail -3 "$LOG" 2>/dev/null | sed 's/^/    /' >> "$BITACORA"

cd "$SCRIPTS" || exit 1
nohup python3 -u descargar_panel_2011.py --pausa 0.2 >> "$LOG" 2>&1 &
sleep 10

if pgrep -f "descargar_panel_2011[.]py" > /dev/null; then
  anotar "relanzada correctamente"
else
  anotar "ATENCIÓN: el relanzamiento falló"
fi
