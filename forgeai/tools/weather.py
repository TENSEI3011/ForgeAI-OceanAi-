"""Current weather + short forecast from Open-Meteo (keyless public API)."""
from __future__ import annotations

from typing import Any

import requests


def _geocode(name: str) -> tuple[float, float, str]:
    r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": name, "count": 1}, timeout=15)
    r.raise_for_status()
    res = (r.json().get("results") or [])
    if not res:
        raise ValueError(f"location not found: {name}")
    top = res[0]
    return top["latitude"], top["longitude"], f"{top['name']}, {top.get('country', '')}"


def run(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    if args.get("latitude") is not None and args.get("longitude") is not None:
        lat, lon, label = float(args["latitude"]), float(args["longitude"]), f"({args['latitude']}, {args['longitude']})"
    else:
        lat, lon, label = _geocode(str(args.get("location") or args.get("place") or ""))
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=15, params={
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,wind_speed_10m,wind_direction_10m,weather_code,precipitation",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "forecast_days": 3, "timezone": "auto"})
    r.raise_for_status()
    d = r.json()
    cur = d.get("current", {})
    daily = d.get("daily", {})
    lines = [f"Weather for {label} (source: open-meteo.com)",
             f"Now: {cur.get('temperature_2m')} C, wind {cur.get('wind_speed_10m')} km/h from {cur.get('wind_direction_10m')} deg, "
             f"precipitation {cur.get('precipitation')} mm"]
    for i, day in enumerate(daily.get("time", [])):
        lines.append(f"{day}: {daily['temperature_2m_min'][i]}-{daily['temperature_2m_max'][i]} C, "
                     f"max wind {daily['wind_speed_10m_max'][i]} km/h, rain {daily['precipitation_sum'][i]} mm")
    return "\n".join(lines)
