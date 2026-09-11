"""Dashboard web en vivo del gemelo digital.

Muestra las aulas y, dentro de cada una, cada sensor con su valor actual y un
color de estado (verde/ámbar/rojo) según umbrales. Se refresca solo cada pocos
segundos. Resuelve el hecho de que Gaphor no se auto-actualiza.

* Usa SOLO la librería estándar de Python (http.server) -> cero dependencias
  extra, fácil de levantar en cualquier laptop.
* Lee de la misma base SQLite que escribe el bridge (proceso aparte).
* Sirve una página HTML autocontenida + un endpoint JSON ``/api/latest``.

Uso:  python -m gemelo -c config.yaml dashboard   (luego abre http://localhost:8080)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import Config
from .models import SENSORS
from .storage import Storage
from .thresholds import from_config

log = logging.getLogger("gemelo.dashboard")

# Si un sensor no reporta hace más de estos segundos, se considera "sin señal".
STALE_AFTER_S = 30

# Cuántos puntos recientes se envían para dibujar el sparkline (tendencia).
SPARK_POINTS = 40

# Cuántos puntos se envían para la gráfica histórica en grande (hover).
HISTORY_POINTS = 500


def metric_status(key: str, value: float, thresholds=None) -> str:
    """Devuelve 'ok' | 'warn' | 'alert' | 'info' para una métrica.

    ``thresholds`` es un dict {metric_key: MetricThreshold}; si se omite se usan
    los defaults. Una métrica sin umbral definido es 'info'.
    """
    th = (thresholds or from_config(None)).get(key)
    return th.status(value) if th else "info"


def build_state(config: Config, storage: Storage) -> dict:
    """Construye el JSON con el estado de todo el gemelo, listo para pintar."""
    now = datetime.now(timezone.utc)
    latest = storage.latest_all()
    thresholds = from_config(config.thresholds)

    aulas_out = []
    for aula in config.aulas:
        ages = []
        sensors_out = []
        for key, spec in SENSORS.items():
            entry = latest.get((aula.id, key))
            if entry is not None:
                metrics, ts = entry
                age = (now - ts).total_seconds()
                ages.append(age)
                stale = age > STALE_AFTER_S
                metrics_out = []
                for m in spec.metrics:
                    if m.key in metrics:
                        v = metrics[m.key]
                        th = thresholds.get(m.key)
                        if stale or th is None:
                            status, gauge = "info", None
                        else:
                            status, gauge = th.status(v), th.gauge(v)
                        # spark: pares [epoch_segundos, valor] para poder ubicar
                        # los puntos en el tiempo real y detectar huecos.
                        raw = storage.history_points(aula.id, key, m.key, SPARK_POINTS)
                        spark = [[round(datetime.fromisoformat(p["ts"]).timestamp(), 1),
                                  p["v"]] for p in raw]
                        metrics_out.append({
                            "key": m.key, "label": m.label, "unit": m.unit,
                            "value": v, "status": status, "gauge": gauge,
                            "spark": spark if len(spark) >= 2 else None,
                        })
                sensors_out.append({
                    "key": key, "model": spec.model, "category": spec.category,
                    "age_s": round(age, 1), "stale": stale,
                    "metrics": metrics_out,
                })
            else:
                # Aún sin datos: se muestra el componente igual (parte del gemelo).
                sensors_out.append({
                    "key": key, "model": spec.model, "category": spec.category,
                    "age_s": None, "stale": True, "nodata": True,
                    "metrics": [{"key": m.key, "label": m.label, "unit": m.unit,
                                 "value": None, "status": "nodata", "gauge": None,
                                 "spark": None}
                                for m in spec.metrics],
                })
        last_seen = round(min(ages), 1) if ages else None
        aulas_out.append({
            "id": aula.id, "name": aula.name,
            "online": last_seen is not None and last_seen <= STALE_AFTER_S,
            "last_seen_s": last_seen,
            "sensors": sensors_out,
        })

    return {"now": now.isoformat(), "stale_after_s": STALE_AFTER_S, "aulas": aulas_out}


def build_history(config: Config, storage: Storage, aula: str, sensor: str,
                  metric: str, limit: int = HISTORY_POINTS) -> dict:
    """Serie histórica de una métrica + su umbral, para la gráfica en grande."""
    thresholds = from_config(config.thresholds)
    th = thresholds.get(metric)
    spec = SENSORS.get(sensor)
    mspec = spec.metric(metric) if spec else None
    return {
        "aula": aula, "sensor": sensor, "metric": metric,
        "model": spec.model if spec else sensor,
        "label": mspec.label if mspec else metric,
        "unit": mspec.unit if mspec else "",
        "points": storage.history_points(aula, sensor, metric, limit),
        "threshold": th.to_dict() if th else None,
    }


# ---------------------------------------------------------------------------
# Servidor HTTP
# ---------------------------------------------------------------------------

def make_handler(config: Config, storage: Storage):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silencia el log ruidoso por request
            pass

        def _send(self, code, content_type, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/latest"):
                body = json.dumps(build_state(config, storage)).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", body)
            elif self.path.startswith("/api/history"):
                qs = parse_qs(urlparse(self.path).query)
                aula = qs.get("aula", [""])[0]
                sensor = qs.get("sensor", [""])[0]
                metric = qs.get("metric", [""])[0]
                if not (aula and sensor and metric):
                    self._send(400, "text/plain; charset=utf-8",
                               b"Faltan parametros aula/sensor/metric")
                    return
                data = build_history(config, storage, aula, sensor, metric)
                self._send(200, "application/json; charset=utf-8",
                           json.dumps(data).encode("utf-8"))
            elif self.path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
            else:
                self._send(404, "text/plain; charset=utf-8", b"No encontrado")

    return Handler


def run_dashboard(config: Config, host: str = "0.0.0.0", port: int = 8080) -> int:
    storage = Storage(config.db_path)
    handler = make_handler(config, storage)
    httpd = ThreadingHTTPServer((host, port), handler)
    shown = "localhost" if host in ("0.0.0.0", "") else host
    print(f"[dashboard] Gemelo digital en:  http://{shown}:{port}")
    print("[dashboard] Ctrl-C para detener.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] Detenido.")
    finally:
        httpd.server_close()
        storage.close()
    return 0


# ---------------------------------------------------------------------------
# Página web (HTML + CSS + JS autocontenidos)
# ---------------------------------------------------------------------------
PAGE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gemelo Digital de Aulas</title>
<style>
  :root {
    --bg:#0f1420; --panel:#182234; --panel2:#1f2c42; --text:#e8eef7;
    --muted:#93a1b8; --line:#2b3a55;
    --ok:#2ecc71; --warn:#f4c542; --alert:#ff5c5c; --info:#5aa9ff; --nodata:#556;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg:#eef2f7; --panel:#fff; --panel2:#f4f7fb; --text:#16202e;
            --muted:#5b6b82; --line:#dce4ee; }
  }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--text); }
  header { padding:18px 24px; border-bottom:1px solid var(--line);
           display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
  header h1 { font-size:20px; margin:0; }
  .pulse { width:10px; height:10px; border-radius:50%; background:var(--ok);
           box-shadow:0 0 0 0 rgba(46,204,113,.6); animation:p 2s infinite; }
  @keyframes p { 0%{box-shadow:0 0 0 0 rgba(46,204,113,.5)} 70%{box-shadow:0 0 0 10px rgba(46,204,113,0)} }
  .meta { color:var(--muted); font-size:13px; margin-left:auto; }
  main { padding:20px 24px; display:grid; gap:22px;
         grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); }
  .aula { background:var(--panel); border:1px solid var(--line);
          border-radius:14px; overflow:hidden; }
  .aula-head { padding:14px 18px; display:flex; align-items:center; gap:10px;
               border-bottom:1px solid var(--line); }
  .aula-head h2 { margin:0; font-size:17px; }
  .badge { font-size:11px; padding:3px 9px; border-radius:999px; font-weight:600; }
  .badge.on { background:rgba(46,204,113,.18); color:var(--ok); }
  .badge.off { background:rgba(255,92,92,.16); color:var(--alert); }
  .sensors { padding:12px; display:grid; gap:10px; }
  .sensor { background:var(--panel2); border:1px solid var(--line);
            border-radius:10px; padding:12px 14px; }
  .sensor.stale { opacity:.55; }
  .s-top { display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
  .s-name { font-weight:600; }
  .s-cat { color:var(--muted); font-size:12px; }
  .s-age { color:var(--muted); font-size:11px; white-space:nowrap; }
  .metrics { margin-top:10px; display:grid; gap:12px; }
  .metric { display:grid; gap:5px; }
  .m-head { display:flex; align-items:center; gap:8px; }
  .dot { width:10px; height:10px; border-radius:50%; flex:none; background:var(--info); }
  .dot.ok{background:var(--ok)} .dot.warn{background:var(--warn)}
  .dot.alert{background:var(--alert)} .dot.info{background:var(--info)}
  .dot.nodata{background:var(--nodata)}
  .m-label { color:var(--muted); font-size:13px; flex:1; }
  .m-val { font-variant-numeric:tabular-nums; font-weight:700; }
  .m-val.ok{color:var(--ok)} .m-val.warn{color:var(--warn)} .m-val.alert{color:var(--alert)}
  .m-unit { color:var(--muted); font-size:12px; font-weight:500; margin-left:2px; }
  /* Sparkline: mini-gráfica de tendencia reciente */
  .spark { width:74px; height:20px; flex:none; opacity:.9; }
  .spark polyline { fill:none; stroke:var(--info); stroke-width:1.4;
                    vector-effect:non-scaling-stroke; stroke-linejoin:round; }
  .spark circle { fill:var(--info); }
  .spark.ok polyline{stroke:var(--ok)} .spark.ok circle{fill:var(--ok)}
  .spark.warn polyline{stroke:var(--warn)} .spark.warn circle{fill:var(--warn)}
  .spark.alert polyline{stroke:var(--alert)} .spark.alert circle{fill:var(--alert)}
  .metric.hoverable { cursor:pointer; border-radius:8px; padding:3px 5px; margin:-3px -5px; }
  .metric.hoverable:hover { background:rgba(127,127,127,.12); }
  /* Popover con la gráfica histórica en grande */
  #pop { position:fixed; z-index:50; display:none; width:412px; background:var(--panel);
         border:1px solid var(--line); border-radius:12px; padding:12px 14px;
         box-shadow:0 14px 44px rgba(0,0,0,.4); }
  #pop h4 { margin:0 0 2px; font-size:14px; }
  #pop .sub { color:var(--muted); font-size:12px; margin-bottom:6px; }
  #pop .stats { display:flex; gap:16px; margin-top:6px; color:var(--muted); font-size:12px; }
  #pop .stats b { color:var(--text); font-variant-numeric:tabular-nums; }
  .axis { fill:var(--muted); font-size:9px; }
  .grid { stroke:var(--line); stroke-width:1; }
  .hband.ok{fill:rgba(46,204,113,.16)} .hband.warn{fill:rgba(244,197,66,.18)}
  .hband.alert{fill:rgba(255,92,92,.18)}
  .hline { fill:none; stroke:var(--info); stroke-width:1.8; vector-effect:non-scaling-stroke;
           stroke-linejoin:round; }
  .hline.ok{stroke:var(--ok)} .hline.warn{stroke:var(--warn)} .hline.alert{stroke:var(--alert)}
  /* Medidor: barra con zonas de color y un marcador en el valor actual */
  .gauge { position:relative; height:11px; border-radius:6px; overflow:hidden;
           background:var(--bg); border:1px solid var(--line); }
  .zone { position:absolute; top:0; bottom:0; }
  .zone.ok{background:rgba(46,204,113,.45)}
  .zone.warn{background:rgba(244,197,66,.55)}
  .zone.alert{background:rgba(255,92,92,.55)}
  .marker { position:absolute; top:-2px; bottom:-2px; width:3px; border-radius:2px;
            background:var(--text); box-shadow:0 0 0 1.5px var(--panel2);
            transform:translateX(-50%); }
  footer { padding:14px 24px; color:var(--muted); font-size:12px;
           border-top:1px solid var(--line); }
</style>
</head>
<body>
<header>
  <div class="pulse" id="pulse"></div>
  <h1>Gemelo Digital de Aulas</h1>
  <div class="meta" id="meta">Conectando…</div>
</header>
<main id="main"></main>
<div id="pop"></div>
<footer>
  Se actualiza automáticamente cada 2 s. Los colores indican el estado según
  umbrales configurables; la mini-gráfica muestra la tendencia reciente.
  Fuente: base de datos del bridge (SQLite).
</footer>
<script>
const STAT = { ok:"ok", warn:"advertencia", alert:"alerta", info:"info", nodata:"sin datos" };

function fmt(v){ return (v===null||v===undefined) ? "—" : (Math.round(v*100)/100); }

// Parte una serie [[t, v], ...] en segmentos, cortando donde hay un HUECO de
// tiempo (p. ej. el sistema estuvo apagado). Devuelve los segmentos y el rango
// de tiempo, para ubicar los puntos según el tiempo real (no por índice).
function timeSegments(pairs){
  if(!pairs || pairs.length < 1) return {segments:[], tmin:0, tmax:1};
  const deltas=[];
  for(let i=1;i<pairs.length;i++) deltas.push(pairs[i][0]-pairs[i-1][0]);
  const sorted=[...deltas].sort((a,b)=>a-b);
  const med = sorted.length ? sorted[Math.floor(sorted.length/2)] : 1;
  const gap = Math.max(med*4, 1e-6);   // umbral: 4x el intervalo típico
  const segs=[]; let cur=[pairs[0]];
  for(let i=1;i<pairs.length;i++){
    if(pairs[i][0]-pairs[i-1][0] > gap){ segs.push(cur); cur=[pairs[i]]; }
    else cur.push(pairs[i]);
  }
  segs.push(cur);
  return {segments:segs, tmin:pairs[0][0], tmax:pairs[pairs.length-1][0]};
}

function sparkline(arr, status){
  if(!arr || arr.length < 2) return "";
  const W=74, H=20, pad=2;
  const vals=arr.map(p=>p[1]);
  const min=Math.min(...vals), max=Math.max(...vals);
  const span=(max-min) || 1;
  const {segments, tmin, tmax} = timeSegments(arr);
  const tspan=(tmax-tmin) || 1;
  const X=t => pad + (t-tmin)/tspan*(W-2*pad);
  const Y=v => (H-pad) - (v-min)/span*(H-2*pad);
  const cls=["ok","warn","alert"].includes(status)?status:"info";
  // Una polilínea por segmento: los huecos NO se cruzan con una línea.
  const lines = segments.filter(s=>s.length>=2).map(s =>
    `<polyline points="${s.map(p=>X(p[0]).toFixed(1)+","+Y(p[1]).toFixed(1)).join(" ")}"/>`
  ).join("");
  const last=arr[arr.length-1];
  return `<svg class="spark ${cls}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
     ${lines}<circle cx="${X(last[0]).toFixed(1)}" cy="${Y(last[1]).toFixed(1)}" r="1.7"/></svg>`;
}

// Gráfica histórica en grande (SVG). Devuelve el HTML del contenido del popover.
function bigChart(d){
  const pts = d.points || [];
  if (pts.length < 2)
    return `<div class="sub">Sin suficiente historial todavía (se acumula mientras corre).</div>`;
  const W=384, H=172, mL=46, mR=14, mT=12, mB=26;
  const vals = pts.map(p => p.v);
  let ymin = Math.min(...vals), ymax = Math.max(...vals);
  const th = d.threshold;
  if (th){ ymin = Math.min(ymin, th.bar_min); ymax = Math.max(ymax, th.bar_max); }
  if (ymin === ymax){ ymin -= 1; ymax += 1; }
  const padv = (ymax - ymin) * 0.08; ymin -= padv; ymax += padv;

  // Eje X por tiempo REAL: pares [ms, valor]; se cortan los huecos (apagones).
  const pairs = pts.map(p => [Date.parse(p.ts), p.v]);
  const {segments, tmin, tmax} = timeSegments(pairs);
  const tspan = (tmax - tmin) || 1;
  const X = t => mL + (t-tmin)/tspan*(W-mL-mR);
  const Y = v => mT + (ymax-v)/(ymax-ymin)*(H-mT-mB);

  let bands = "";
  let last = "info";
  if (th){
    for (const b of th.bands){
      const y1 = Y(b.to), y2 = Y(b.from);
      bands += `<rect class="hband ${b.status}" x="${mL}" y="${y1.toFixed(1)}" width="${W-mL-mR}" height="${(y2-y1).toFixed(1)}"/>`;
    }
    const lv = vals[vals.length-1];
    for (const b of th.bands){ if (lv >= b.from && lv <= b.to) last = b.status; }
  }
  // Una línea por segmento; punto aislado tras un hueco -> circulito.
  let lines = "";
  for (const s of segments){
    if (s.length >= 2)
      lines += `<polyline class="hline ${last}" points="${s.map(p=>X(p[0]).toFixed(1)+","+Y(p[1]).toFixed(1)).join(" ")}"/>`;
    else
      lines += `<circle cx="${X(s[0][0]).toFixed(1)}" cy="${Y(s[0][1]).toFixed(1)}" r="2" fill="var(--muted)"/>`;
  }
  const gaps = segments.length - 1;
  const t0 = new Date(tmin).toLocaleString();
  const t1 = new Date(tmax).toLocaleString();
  const avg = vals.reduce((a,b)=>a+b,0)/vals.length;
  const svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block">
     ${bands}
     <line class="grid" x1="${mL}" y1="${mT}" x2="${mL}" y2="${H-mB}"/>
     <line class="grid" x1="${mL}" y1="${H-mB}" x2="${W-mR}" y2="${H-mB}"/>
     ${lines}
     <text class="axis" x="${mL-4}" y="${mT+4}" text-anchor="end">${(Math.round(ymax*10)/10)}</text>
     <text class="axis" x="${mL-4}" y="${H-mB}" text-anchor="end">${(Math.round(ymin*10)/10)}</text>
     <text class="axis" x="${mL}" y="${H-mB+13}">${t0}</text>
     <text class="axis" x="${W-mR}" y="${H-mB+13}" text-anchor="end">${t1}</text>
   </svg>`;
  const gapNote = gaps > 0
    ? `<span title="tramos separados por periodos sin datos">huecos <b>${gaps}</b></span>` : "";
  const stats = `<div class="stats">
     <span>puntos <b>${pts.length}</b></span>
     <span>mín <b>${fmt(Math.min(...vals))}</b></span>
     <span>máx <b>${fmt(Math.max(...vals))}</b></span>
     <span>prom <b>${fmt(avg)}</b></span>${gapNote}</div>`;
  return svg + stats;
}
function age(s){
  if (s===null||s===undefined) return "sin datos";
  if (s<60) return "hace "+Math.round(s)+" s";
  return "hace "+Math.round(s/60)+" min";
}

function render(state){
  document.getElementById("meta").textContent =
    "Actualizado " + new Date(state.now).toLocaleTimeString();
  const main = document.getElementById("main");
  main.innerHTML = "";
  for (const aula of state.aulas){
    const card = document.createElement("section");
    card.className = "aula";
    const badge = aula.online
      ? '<span class="badge on">● en línea</span>'
      : '<span class="badge off">● sin señal</span>';
    let html = `<div class="aula-head"><h2>${aula.name}</h2>${badge}
       <span class="s-age" style="margin-left:auto">${age(aula.last_seen_s)}</span></div>
       <div class="sensors">`;
    for (const s of aula.sensors){
      const rows = s.metrics.map(m => {
        const g = m.gauge;
        const gaugeHtml = g
          ? `<div class="gauge">${
              g.zones.map(z => `<div class="zone ${z.status}" style="left:${z.from}%;width:${(z.to-z.from)}%"></div>`).join("")
            }<div class="marker" style="left:${g.pct}%" title="${fmt(m.value)} ${m.unit}"></div></div>`
          : "";
        const valClass = ["ok","warn","alert"].includes(m.status) ? m.status : "";
        const hover = (m.value!==null)
          ? `hoverable" data-aula="${aula.id}" data-sensor="${s.key}" data-metric="${m.key}`
          : "";
        return `<div class="metric ${hover}">
            <div class="m-head">
              <span class="dot ${m.status}" title="${STAT[m.status]||''}"></span>
              <span class="m-label">${m.label}</span>
              ${sparkline(m.spark, m.status)}
              <span class="m-val ${valClass}">${fmt(m.value)}<span class="m-unit">${m.value===null?'':m.unit}</span></span>
            </div>${gaugeHtml}
          </div>`;
      }).join("");
      html += `<div class="sensor ${s.stale?'stale':''}">
          <div class="s-top">
            <span><span class="s-name">${s.model}</span>
                  <span class="s-cat"> · ${s.category}</span></span>
            <span class="s-age">${s.nodata?'sin datos':age(s.age_s)}</span>
          </div>
          <div class="metrics">${rows}</div>
        </div>`;
    }
    html += `</div>`;
    card.innerHTML = html;
    main.appendChild(card);
  }
}

// --- Detalle histórico al pasar el mouse -------------------------------
const main = document.getElementById("main");
const pop = document.getElementById("pop");
let paused = false, curKey = null, hideTimer = null;

function positionPop(el){
  const r = el.getBoundingClientRect();
  const w = pop.offsetWidth, h = pop.offsetHeight;
  let left = r.right + 12;
  if (left + w > window.innerWidth - 8) left = r.left - w - 12;
  if (left < 8) left = 8;
  let top = r.top;
  if (top + h > window.innerHeight - 8) top = window.innerHeight - h - 8;
  if (top < 8) top = 8;
  pop.style.left = left + "px";
  pop.style.top = top + "px";
}

async function showDetail(el){
  const key = el.dataset.aula + "|" + el.dataset.sensor + "|" + el.dataset.metric;
  if (key === curKey && pop.style.display === "block") return;
  curKey = key; paused = true;
  try {
    const q = `aula=${encodeURIComponent(el.dataset.aula)}&sensor=${encodeURIComponent(el.dataset.sensor)}&metric=${encodeURIComponent(el.dataset.metric)}`;
    const d = await (await fetch("/api/history?" + q, {cache:"no-store"})).json();
    if (curKey !== key) return;      // el mouse ya se movió a otra métrica
    pop.innerHTML = `<h4>${d.model} · ${d.label}</h4>
      <div class="sub">${d.aula} — historial ${d.unit ? "("+d.unit+")" : ""}</div>` + bigChart(d);
    pop.style.display = "block";
    positionPop(el);
  } catch(e){ /* si falla, no mostramos nada */ }
}

function hideDetail(){ pop.style.display = "none"; curKey = null; paused = false; }

main.addEventListener("mouseover", e => {
  const m = e.target.closest(".metric.hoverable");
  if (m){ clearTimeout(hideTimer); showDetail(m); }
});
main.addEventListener("mouseout", e => {
  const m = e.target.closest(".metric.hoverable");
  if (m && !m.contains(e.relatedTarget) && !pop.contains(e.relatedTarget))
    hideTimer = setTimeout(hideDetail, 180);
});
pop.addEventListener("mouseenter", () => clearTimeout(hideTimer));
pop.addEventListener("mouseleave", () => { hideTimer = setTimeout(hideDetail, 180); });

// --- Refresco en vivo ---------------------------------------------------
async function tick(){
  if (paused) return;              // no re-render mientras se inspecciona el historial
  try {
    const r = await fetch("/api/latest", {cache:"no-store"});
    render(await r.json());
    document.getElementById("pulse").style.background = "var(--ok)";
  } catch(e){
    document.getElementById("meta").textContent = "Sin conexión con el servidor…";
    document.getElementById("pulse").style.background = "var(--alert)";
  }
}
tick();
setInterval(tick, 2000);
</script>
</body>
</html>"""
