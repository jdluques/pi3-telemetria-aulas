"""Tests del dashboard: cálculo de estado por umbrales y armado del JSON."""

from datetime import datetime, timedelta, timezone

from gemelo.config import Config
from gemelo.dashboard import build_state, metric_status, STALE_AFTER_S
from gemelo.models import Reading, SENSORS
from gemelo.storage import Storage


def test_metric_status_umbrales():
    assert metric_status("co2_ppm", 500) == "ok"
    assert metric_status("co2_ppm", 900) == "warn"
    assert metric_status("co2_ppm", 1500) == "alert"
    assert metric_status("temp_c", 22) == "ok"
    assert metric_status("temp_c", 31) == "alert"
    # Métrica sin umbral definido: siempre 'info'.
    assert metric_status("pres_hpa", 1013) == "info"
    assert metric_status("occupancy_est", 5) == "info"


def test_gauge_incluye_zonas_y_posicion():
    from gemelo.thresholds import from_config
    th = from_config(None)["temp_c"]        # bar 10..40, ok 19-26, alert 16/30
    g = th.gauge(22.5)
    # El valor 22.5 en [10,40] cae a ~41.7%.
    assert 40 < g["pct"] < 44
    estados = [z["status"] for z in g["zones"]]
    # Debe haber zonas de alerta (extremos), advertencia y ok (centro).
    assert "ok" in estados and "warn" in estados and "alert" in estados
    # Las zonas cubren toda la barra (0 -> 100).
    assert g["zones"][0]["from"] == 0 and g["zones"][-1]["to"] == 100


def test_config_sobreescribe_umbral():
    from gemelo.thresholds import from_config
    th = from_config({"co2_ppm": {"alert_max": 1000}})["co2_ppm"]
    assert th.status(1100) == "alert"        # con default (1200) sería 'warn'
    assert th.ok_max == 800                   # lo no indicado conserva el default


def test_build_state_incluye_gauge():
    cfg = Config()
    with Storage(":memory:") as st:
        st.insert(Reading("aula-A", "bme280", datetime.now(timezone.utc),
                          {"temp_c": 24.0, "hum_pct": 45.0, "pres_hpa": 1012.0}))
        state = build_state(cfg, st)
    aula = next(a for a in state["aulas"] if a["id"] == "aula-A")
    bme = next(s for s in aula["sensors"] if s["key"] == "bme280")
    temp = next(m for m in bme["metrics"] if m["key"] == "temp_c")
    pres = next(m for m in bme["metrics"] if m["key"] == "pres_hpa")
    assert temp["gauge"] is not None and temp["gauge"]["zones"]
    assert pres["gauge"] is None            # presión no tiene umbral -> info
    assert pres["status"] == "info"


def test_history_devuelve_valores_en_orden_cronologico():
    from datetime import timedelta
    with Storage(":memory:") as st:
        t0 = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
        for i, v in enumerate([20.0, 21.0, 22.0]):
            st.insert(Reading("aula-A", "bme280", t0 + timedelta(minutes=i),
                              {"temp_c": v}))
        assert st.history("aula-A", "bme280", "temp_c") == [20.0, 21.0, 22.0]
        # 'limit' devuelve los más recientes, aún en orden cronológico.
        assert st.history("aula-A", "bme280", "temp_c", limit=2) == [21.0, 22.0]


def test_build_state_incluye_sparkline_con_historial():
    from datetime import timedelta
    cfg = Config()
    with Storage(":memory:") as st:
        now = datetime.now(timezone.utc)
        # Varias lecturas -> sparkline con serie; una sola -> sin sparkline.
        for i, v in enumerate([22.0, 23.0, 24.0, 25.0]):
            st.insert(Reading("aula-A", "bme280", now - timedelta(seconds=8 - i),
                              {"temp_c": v, "hum_pct": 50}))
        st.insert(Reading("aula-A", "mhz19b", now, {"co2_ppm": 700}))
        state = build_state(cfg, st)

    aula = next(a for a in state["aulas"] if a["id"] == "aula-A")
    temp = next(m for s in aula["sensors"] if s["key"] == "bme280"
                for m in s["metrics"] if m["key"] == "temp_c")
    # spark es una lista de pares [epoch_segundos, valor].
    assert [p[1] for p in temp["spark"]] == [22.0, 23.0, 24.0, 25.0]
    ts = [p[0] for p in temp["spark"]]
    assert ts == sorted(ts)          # timestamps en orden cronológico
    # Con una sola lectura no hay tendencia que dibujar.
    co2 = next(m for s in aula["sensors"] if s["key"] == "mhz19b"
               for m in s["metrics"] if m["key"] == "co2_ppm")
    assert co2["spark"] is None


def test_history_points_incluye_ts_y_valor():
    from datetime import timedelta
    with Storage(":memory:") as st:
        t0 = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
        for i, v in enumerate([10.0, 11.0]):
            st.insert(Reading("aula-A", "bh1750", t0 + timedelta(minutes=i),
                              {"lux": v}))
        pts = st.history_points("aula-A", "bh1750", "lux")
        assert [p["v"] for p in pts] == [10.0, 11.0]
        assert all("ts" in p for p in pts)


def test_build_history_incluye_umbral_y_bandas():
    from datetime import timedelta
    from gemelo.dashboard import build_history
    cfg = Config()
    with Storage(":memory:") as st:
        now = datetime.now(timezone.utc)
        for i, v in enumerate([600, 900, 1300]):
            st.insert(Reading("aula-A", "mhz19b", now - timedelta(seconds=6 - i),
                              {"co2_ppm": v}))
        d = build_history(cfg, st, "aula-A", "mhz19b", "co2_ppm")
    assert d["label"] == "CO2" and d["unit"] == "ppm"
    assert [p["v"] for p in d["points"]] == [600, 900, 1300]
    # El umbral trae escala y bandas de color (ok/warn/alert).
    assert d["threshold"]["bar_min"] == 400 and d["threshold"]["bar_max"] == 2000
    estados = {b["status"] for b in d["threshold"]["bands"]}
    assert estados == {"ok", "warn", "alert"}


def test_build_history_sin_umbral():
    from gemelo.dashboard import build_history
    cfg = Config()
    with Storage(":memory:") as st:
        st.insert(Reading("aula-A", "bme280", datetime.now(timezone.utc),
                          {"pres_hpa": 1012.0}))
        d = build_history(cfg, st, "aula-A", "bme280", "pres_hpa")
    assert d["threshold"] is None       # presión no tiene umbral -> sin bandas


def test_mlx_min_max_tienen_color_y_presion_no():
    cfg = Config()
    with Storage(":memory:") as st:
        now = datetime.now(timezone.utc)
        st.insert(Reading("aula-A", "mlx90640", now,
                          {"min_c": 12.0, "max_c": 33.0, "mean_c": 24.0,
                           "occupancy_est": 4}))
        st.insert(Reading("aula-A", "bme280", now, {"pres_hpa": 1012.0}))
        state = build_state(cfg, st)
    aula = next(a for a in state["aulas"] if a["id"] == "aula-A")
    mlx = next(s for s in aula["sensors"] if s["key"] == "mlx90640")
    by = {m["key"]: m for m in mlx["metrics"]}
    assert by["min_c"]["gauge"] is not None      # temperatura mínima con color
    assert by["max_c"]["gauge"] is not None      # temperatura máxima con color
    assert by["occupancy_est"]["gauge"] is None  # ocupación sin umbral -> info

    bme = next(s for s in aula["sensors"] if s["key"] == "bme280")
    pres = next(m for m in bme["metrics"] if m["key"] == "pres_hpa")
    assert pres["gauge"] is None                 # presión sin color (informativa)


def test_build_state_incluye_todos_los_sensores_aunque_no_haya_datos():
    cfg = Config()
    with Storage(":memory:") as st:
        state = build_state(cfg, st)
    assert len(state["aulas"]) == 2
    for aula in state["aulas"]:
        assert len(aula["sensors"]) == len(SENSORS)
        assert aula["online"] is False           # sin datos -> offline
        assert all(s.get("nodata") for s in aula["sensors"])


def test_build_state_refleja_medicion_reciente():
    cfg = Config()
    with Storage(":memory:") as st:
        now = datetime.now(timezone.utc)
        st.insert(Reading("aula-A", "mhz19b", now, {"co2_ppm": 1500}))
        state = build_state(cfg, st)

    aula_a = next(a for a in state["aulas"] if a["id"] == "aula-A")
    assert aula_a["online"] is True
    co2_sensor = next(s for s in aula_a["sensors"] if s["key"] == "mhz19b")
    assert co2_sensor["stale"] is False
    metric = co2_sensor["metrics"][0]
    assert metric["value"] == 1500
    assert metric["status"] == "alert"     # 1500 ppm supera el umbral


def test_build_state_marca_stale_datos_viejos():
    cfg = Config()
    with Storage(":memory:") as st:
        old = datetime.now(timezone.utc) - timedelta(seconds=STALE_AFTER_S + 60)
        st.insert(Reading("aula-B", "bme280", old, {"temp_c": 24.0}))
        state = build_state(cfg, st)

    aula_b = next(a for a in state["aulas"] if a["id"] == "aula-B")
    assert aula_b["online"] is False       # el dato es demasiado viejo
    bme = next(s for s in aula_b["sensors"] if s["key"] == "bme280")
    assert bme["stale"] is True
    # Un dato stale no dispara semáforo (se muestra como info).
    assert bme["metrics"][0]["status"] == "info"
