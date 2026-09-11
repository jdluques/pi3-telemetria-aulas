"""Tests del almacenamiento SQLite."""

from datetime import datetime, timedelta, timezone

from gemelo.models import Reading
from gemelo.storage import Storage


def _reading(aula, sensor, metrics, ts):
    return Reading(aula=aula, sensor=sensor, ts=ts, metrics=metrics)


def test_insert_y_latest():
    with Storage(":memory:") as st:
        t0 = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
        st.insert(_reading("aula-A", "bme280", {"temp_c": 20.0, "hum_pct": 50.0}, t0))
        st.insert(_reading("aula-A", "bme280", {"temp_c": 22.5, "hum_pct": 48.0},
                           t0 + timedelta(minutes=5)))
        metrics, ts = st.latest("aula-A", "bme280")
        # Debe devolver el más reciente.
        assert metrics["temp_c"] == 22.5
        assert ts == t0 + timedelta(minutes=5)


def test_latest_sin_datos_devuelve_none():
    with Storage(":memory:") as st:
        assert st.latest("aula-A", "bme280") is None


def test_latest_all():
    with Storage(":memory:") as st:
        t0 = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
        st.insert(_reading("aula-A", "bme280", {"temp_c": 21.0}, t0))
        st.insert(_reading("aula-B", "bh1750", {"lux": 300.0}, t0))
        alld = st.latest_all()
        assert set(alld) == {("aula-A", "bme280"), ("aula-B", "bh1750")}
        assert alld[("aula-B", "bh1750")][0]["lux"] == 300.0


def test_count():
    with Storage(":memory:") as st:
        t0 = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
        st.insert(_reading("aula-A", "bme280", {"temp_c": 21.0, "hum_pct": 40.0}, t0))
        assert st.count() == 2  # una fila por métrica
