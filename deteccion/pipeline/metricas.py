"""Construye las filas de permanencia por persona y el reporte final de la
corrida, a partir de los datos que ya quedaron en la BD."""
from deteccion.utils import to_timestamp

_BUCKETS_ORDEN = ["< 1 min", "1-5 min", "5-15 min", "15-60 min", "> 1 hora"]


def _dist_bucket(sec: float) -> str:
    if sec < 60:   return "< 1 min"
    if sec < 300:  return "1-5 min"
    if sec < 900:  return "5-15 min"
    if sec < 3600: return "15-60 min"
    return "> 1 hora"


def construir_rows(resumen_personas: list, fps: float) -> list:
    """Agrega entrada/salida/duracion a los datos crudos por persona que
    devuelve PersonTracker.resumen_por_persona()."""
    rows = []
    for p in resumen_personas:
        first_frame, last_frame = p["first_frame"], p["last_frame"]
        dur_sec = (last_frame - first_frame + 1) / fps
        rows.append({
            "id":           p["sid"],
            "_first_frame": first_frame,
            "_last_frame":  last_frame,
            "entrada":      to_timestamp(first_frame, fps),
            "salida":       to_timestamp(last_frame, fps),
            "duracion_seg": round(dur_sec, 1),
            "duracion_min": round(dur_sec / 60, 2),
            "metodo_reid":      p["metodo_reid"],
            "descripcion":      p["descripcion"],
            "cliente_id_hint":  p.get("cliente_id_hint"),
        })
    return rows


def imprimir_resumen(
    rows: list, camara_id, sesion_id, max_personas: int,
    conteo_metodo_reid: dict, total_detecciones: int, frames_procesados: int,
    num_trayectorias: int,
) -> None:
    duraciones = [r["duracion_seg"] for r in rows]
    promedio   = sum(duraciones) / len(duraciones) if duraciones else 0

    buckets = {}
    for d in duraciones:
        b = _dist_bucket(d)
        buckets[b] = buckets.get(b, 0) + 1

    print("\n" + "=" * 52)
    print("           RESUMEN DE ANALISIS")
    print("=" * 52)
    print(f"  Camara                      : {camara_id or 'desconocida'}")
    print(f"  Sesion BD                   : {sesion_id or 'no guardada'}")
    print(f"  Personas unicas detectadas  : {len(rows)}")
    print(f"  Maximas personas simultaneas: {max_personas}")
    print(f"  Permanencia promedio        : {promedio/60:.1f} min")
    if duraciones:
        idx_max = duraciones.index(max(duraciones))
        idx_min = duraciones.index(min(duraciones))
        print(f"  Permanencia maxima          : {max(duraciones)/60:.1f} min  (ID {rows[idx_max]['id']})")
        print(f"  Permanencia minima          : {min(duraciones)/60:.1f} min  (ID {rows[idx_min]['id']})")
    print(f"  Total detecciones heatmap   : {total_detecciones:,}")
    print(f"  Frames procesados           : {frames_procesados:,}")
    print()
    print("  Auditoria de Re-ID (metodo de resolucion por bytetrack id):")
    total_resoluciones = sum(conteo_metodo_reid.values())
    # "nuevo/posicion/apariencia" son fijos; cualquier otra clave presente en el
    # conteo es un proveedor de Re-ID en la nube (gemini, groq, o el que se
    # agregue despues) -- se muestra dinamicamente, sin hardcodear cual esta activo.
    metodos_locales = ["nuevo", "posicion", "apariencia"]
    metodos_nube    = sorted(set(conteo_metodo_reid) - set(metodos_locales))
    for metodo in metodos_locales + metodos_nube:
        cnt = conteo_metodo_reid.get(metodo, 0)
        pct = (cnt / total_resoluciones * 100) if total_resoluciones else 0
        print(f"    {metodo:<12}: {cnt:>4}  ({pct:.1f}%)")
    total_reid = total_resoluciones - conteo_metodo_reid.get("nuevo", 0)
    if total_reid > 0:
        cnt_nube  = sum(conteo_metodo_reid.get(m, 0) for m in metodos_nube)
        pct_nube  = cnt_nube / total_reid * 100
        pct_local = 100 - pct_nube
        etiqueta_nube = "/".join(m.capitalize() for m in metodos_nube) if metodos_nube else "nube"
        print(f"    -> de las reidentificaciones (excluyendo altas nuevas): "
              f"{pct_local:.1f}% local, {pct_nube:.1f}% {etiqueta_nube}")
    print()
    print("  Distribucion:")
    for bucket in _BUCKETS_ORDEN:
        count = buckets.get(bucket, 0)
        print(f"    {bucket:<12}: {count:>4}  {'|' * count}")
    print()
    if sesion_id:
        print(f"  BD              : sesion={sesion_id}, {len(rows)} personas, {num_trayectorias} trayectorias")
    print("=" * 52)
