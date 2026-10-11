#!/usr/bin/env bash
# Descarga las tres cartografías de secciones censales del INE y recorta Madrid.
# No se versionan porque pesan 170 MB; este script las reconstruye.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p datos/cartografia/{origen,ext2001,ext2011,ext2021,madrid}
cd datos/cartografia

descargar () { [ -f "origen/$2" ] || curl -sSL --max-time 900 -o "origen/$2" "$1"; }
descargar https://www.ine.es/censos2011_datos/cartografia_censo2011_nacional.zip cartografia_censo2011_nacional.zip
descargar https://www.ine.es/prodyser/cartografia/seccionado_2021.zip seccionado_2021.zip
descargar https://www.ine.es/prodyser/cartografia/seccionado_2001.zip seccionado_2001.zip

unzip -q -o origen/cartografia_censo2011_nacional.zip -d ext2011/
unzip -q -o origen/seccionado_2021.zip -d ext2021/
unzip -q -o origen/seccionado_2001.zip -d ext2001/

ogr2ogr -f GPKG madrid/secc_2011.gpkg ext2011/SECC_CPV_E_20111101_01_R_INE.shp \
  -where "CPRO='28'" -nln secc -t_srs EPSG:4326 -select CUSEC,CUMUN,CPRO,NPRO
ogr2ogr -f GPKG madrid/secc_2021.gpkg ext2021/Seccionado_2021/SECC_CE_20210101.shp \
  -where "CPRO='28'" -nln secc -t_srs EPSG:4326 -select CUSEC,CUMUN,CPRO,NPRO
ogr2ogr -f GPKG madrid/secc_2001.gpkg "ext2001/España_Seeccionado2001/PeninsulayBaleares01.shp" \
  -where "Prov='28'" -nln secc -t_srs EPSG:4326

echo "listo: $(ls madrid/)"
