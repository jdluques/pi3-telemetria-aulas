"""Umbrales por métrica: qué se considera normal, advertencia o alerta.

Cada métrica puede tener un rango "cómodo" (``ok_min``/``ok_max``) y límites de
alerta (``alert_min``/``alert_max``). Fuera del rango cómodo pero dentro de los
de alerta = advertencia; más allá de los de alerta = alerta.

``bar_min``/``bar_max`` definen la escala visual del medidor (la barra) en el
dashboard.

Los valores por defecto (``DEFAULTS``) están pensados para un aula y viven en
el código, así el sistema tiene sentido aunque no se configure nada. Se pueden
sobrescribir, total o parcialmente, desde ``config.yaml`` (sección
``thresholds``). Ver :func:`from_config`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass
class MetricThreshold:
    ok_min: float | None = None
    ok_max: float | None = None
    alert_min: float | None = None
    alert_max: float | None = None
    bar_min: float | None = None
    bar_max: float | None = None

    def status(self, v: float) -> str:
        """'ok' | 'warn' | 'alert' para un valor."""
        if (self.alert_min is not None and v < self.alert_min) or \
           (self.alert_max is not None and v > self.alert_max):
            return "alert"
        if (self.ok_min is not None and v < self.ok_min) or \
           (self.ok_max is not None and v > self.ok_max):
            return "warn"
        return "ok"

    def _scale(self) -> tuple[float, float] | None:
        """Rango visual de la barra; si no se dio, se deriva de los límites."""
        lo, hi = self.bar_min, self.bar_max
        candidates = [c for c in (self.alert_min, self.ok_min, self.ok_max,
                                  self.alert_max) if c is not None]
        if lo is None and candidates:
            lo = min(candidates)
        if hi is None and candidates:
            hi = max(candidates)
        if lo is None or hi is None or hi <= lo:
            return None
        return lo, hi

    def gauge(self, v: float) -> dict | None:
        """Datos para pintar el medidor: posición del valor y zonas de color.

        Devuelve ``{"pct": <0-100>, "zones": [{"from","to","status"}]}`` o
        ``None`` si no hay escala suficiente para dibujar.
        """
        scale = self._scale()
        if scale is None:
            return None
        lo, hi = scale
        span = hi - lo

        def pct(x: float) -> float:
            return round(max(0.0, min(100.0, (x - lo) / span * 100)), 2)

        # Puntos de corte ordenados dentro del rango visible.
        cuts = sorted({lo, hi} | {
            b for b in (self.alert_min, self.ok_min, self.ok_max, self.alert_max)
            if b is not None and lo < b < hi
        })
        zones = []
        for a, b in zip(cuts, cuts[1:]):
            mid = (a + b) / 2
            zones.append({"from": pct(a), "to": pct(b), "status": self.status(mid)})
        return {"pct": pct(v), "zones": zones}

    def bands(self) -> list[dict]:
        """Zonas de color en unidades del valor (para la gráfica histórica).

        ``[{"from": <valor>, "to": <valor>, "status": ...}, ...]``.
        """
        scale = self._scale()
        if scale is None:
            return []
        lo, hi = scale
        cuts = sorted({lo, hi} | {
            b for b in (self.alert_min, self.ok_min, self.ok_max, self.alert_max)
            if b is not None and lo < b < hi
        })
        return [{"from": a, "to": b, "status": self.status((a + b) / 2)}
                for a, b in zip(cuts, cuts[1:])]

    def to_dict(self) -> dict | None:
        """Escala y zonas en unidades del valor, o ``None`` si no hay escala."""
        scale = self._scale()
        if scale is None:
            return None
        lo, hi = scale
        return {"bar_min": lo, "bar_max": hi, "bands": self.bands()}


# ---------------------------------------------------------------------------
# Valores por defecto (contexto: aula). Fuente de referencia para ajustar:
#   CO2: <800 ppm bien ventilado; >1200 ppm ventilación insuficiente.
#   Confort térmico típico de aula: ~19-26 °C.
#   Humedad relativa saludable: ~30-60 %.
#   Ruido de aula: hasta ~65 dB aceptable; >80 dB molesto.
#   Iluminancia recomendada para aulas: ~300-1000 lux.
# ---------------------------------------------------------------------------
DEFAULTS: dict[str, MetricThreshold] = {
    "temp_c":  MetricThreshold(ok_min=19, ok_max=26, alert_min=16, alert_max=30,
                               bar_min=10, bar_max=40),
    "mean_c":  MetricThreshold(ok_min=19, ok_max=26, alert_min=16, alert_max=30,
                               bar_min=10, bar_max=40),
    "hum_pct": MetricThreshold(ok_min=30, ok_max=60, alert_min=20, alert_max=75,
                               bar_min=0, bar_max=100),
    "co2_ppm": MetricThreshold(ok_max=800, alert_max=1200,
                               bar_min=400, bar_max=2000),
    "spl_db":  MetricThreshold(ok_max=65, alert_max=80,
                               bar_min=30, bar_max=100),
    "lux":     MetricThreshold(ok_min=300, ok_max=1000, alert_min=100,
                               bar_min=0, bar_max=1600),
    # Cámara térmica MLX90640: min_c/max_c son temperaturas de SUPERFICIE, no de
    # confort ambiental (para eso está el BME280). Rangos más anchos a propósito.
    #   min_c: punto más frío (ventana/pared fría, corriente de aire).
    #   max_c: punto más caliente (presencia de personas ~30-34 °C, o fuente de
    #          calor / sobrecalentamiento si es muy alto).
    "min_c":   MetricThreshold(ok_min=15, ok_max=30, alert_min=8, alert_max=35,
                               bar_min=0, bar_max=40),
    "max_c":   MetricThreshold(ok_min=18, ok_max=36, alert_max=50,
                               bar_min=10, bar_max=55),
}

# Campos válidos al sobrescribir desde config.yaml.
_FIELDS = ("ok_min", "ok_max", "alert_min", "alert_max", "bar_min", "bar_max")


def from_config(raw: dict | None) -> dict[str, MetricThreshold]:
    """Combina los defaults con las sobreescrituras del ``config.yaml``.

    ``raw`` es ``config.thresholds``: ``{metric_key: {campo: valor, ...}}``.
    Solo se reemplazan los campos indicados; el resto conserva el default.
    Métricas nuevas (no presentes en DEFAULTS) también se aceptan.
    """
    result = {k: replace(v) for k, v in DEFAULTS.items()}
    for key, overrides in (raw or {}).items():
        if not isinstance(overrides, dict):
            continue
        base = result.get(key, MetricThreshold())
        changes = {f: overrides[f] for f in _FIELDS if f in overrides}
        result[key] = replace(base, **changes)
    return result
