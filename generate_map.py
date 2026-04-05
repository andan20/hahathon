#!/usr/bin/env python3
"""Встраивает output.csv в интерактивную карту stores_map.html."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "output.csv"
OUT_HTML = ROOT / "stores_map.html"

CENTER_LAT = 55.754264
CENTER_LON = 37.648633


def main() -> None:
    rows: list[dict] = []
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        lat_key = "Широта (WGS84)"
        lon_key = "Долгота (WGS84)"
        for row in reader:
            try:
                lat_s = (row.get(lat_key) or "").strip()
                lon_s = (row.get(lon_key) or "").strip()
                if not lat_s or not lon_s:
                    continue
                lat = float(lat_s.replace(",", "."))
                lon = float(lon_s.replace(",", "."))
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "id": row.get("ID", ""),
                    "lat": lat,
                    "lon": lon,
                    "address": (row.get("Адрес") or "").strip(),
                    "metro": (row.get("Метро") or "").strip(),
                }
            )

    data_json = json.dumps(rows, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Магазины в радиусе</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; margin: 0; font-family: system-ui, sans-serif; }}
    #map {{ height: 100%; width: 100%; }}
    .panel {{
      position: absolute; z-index: 1000; top: 12px; left: 12px;
      background: rgba(255,255,255,.95); padding: 12px 16px; border-radius: 10px;
      box-shadow: 0 2px 12px rgba(0,0,0,.15); max-width: min(360px, 92vw);
    }}
    .panel h1 {{ margin: 0 0 8px; font-size: 1rem; font-weight: 600; }}
    .panel label {{ display: block; font-size: .85rem; color: #444; margin-bottom: 6px; }}
    .panel input[type="range"] {{ width: 100%; }}
    .stats {{ margin-top: 10px; font-size: .9rem; color: #222; }}
    .stats strong {{ color: #0a5; }}
    .hint {{ font-size: .75rem; color: #666; margin-top: 8px; line-height: 1.35; }}
  </style>
</head>
<body>
  <div class="panel">
    <h1>Радиус от центра</h1>
    <label for="radius">Радиус: <span id="radiusVal">2000</span> м</label>
    <input type="range" id="radius" min="100" max="50000" step="100" value="2000" />
    <div class="stats">В зоне: <strong id="count">0</strong> из <span id="total">0</span></div>
    <p class="hint">Центр: {CENTER_LAT}, {CENTER_LON}. Увеличьте радиус — появятся точки в пределах круга.</p>
  </div>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const STORES = {data_json};
    const CENTER = [{CENTER_LAT}, {CENTER_LON}];

    function haversineM(aLat, aLon, bLat, bLon) {{
      const R = 6371000;
      const toRad = (d) => d * Math.PI / 180;
      const dLat = toRad(bLat - aLat);
      const dLon = toRad(bLon - aLon);
      const x =
        Math.sin(dLat / 2) ** 2 +
        Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLon / 2) ** 2;
      return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
    }}

    const map = L.map("map").setView(CENTER, 12);
    L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
      attribution: "&copy; OpenStreetMap",
      maxZoom: 19,
    }}).addTo(map);

    L.marker(CENTER).addTo(map).bindPopup("Центр");
    let circle = L.circle(CENTER, {{ radius: 2000, color: "#3388ff", fillOpacity: 0.12 }}).addTo(map);

    const layerGroup = L.layerGroup().addTo(map);
    const centroidGroup = L.layerGroup().addTo(map);
    document.getElementById("total").textContent = STORES.length;

    function popupHtml(s) {{
      const esc = (t) => String(t || "").replace(/&/g,"&amp;").replace(/</g,"&lt;");
      let h = "<b>ID " + esc(s.id) + "</b><br/>" + esc(s.address);
      if (s.metro) h += "<br/><small>" + esc(s.metro) + "</small>";
      return h;
    }}

    function refresh() {{
      const r = parseInt(document.getElementById("radius").value, 10);
      document.getElementById("radiusVal").textContent = r;
      map.removeLayer(circle);
      circle = L.circle(CENTER, {{ radius: r, color: "#3388ff", weight: 2, fillOpacity: 0.1 }}).addTo(map);

      layerGroup.clearLayers();
      centroidGroup.clearLayers();
      let n = 0;
      let sumLat = 0;
      let sumLon = 0;
      for (const s of STORES) {{
        const d = haversineM(CENTER[0], CENTER[1], s.lat, s.lon);
        if (d <= r) {{
          n++;
          sumLat += s.lat;
          sumLon += s.lon;
          L.circleMarker([s.lat, s.lon], {{
            radius: 6,
            fillColor: "#e63946",
            color: "#fff",
            weight: 1,
            fillOpacity: 0.9,
          }}).bindPopup(popupHtml(s)).addTo(layerGroup);
        }}
      }}
      if (n > 0) {{
        const cLat = sumLat / n;
        const cLon = sumLon / n;
        L.circleMarker([cLat, cLon], {{
          radius: 10,
          fillColor: "#2a9d8f",
          color: "#fff",
          weight: 2,
          fillOpacity: 1,
        }})
          .bindPopup(
            "Центр выбранных магазинов<br/><small>" +
              cLat.toFixed(6) +
              ", " +
              cLon.toFixed(6) +
              "</small>"
          )
          .addTo(centroidGroup);
      }}
      document.getElementById("count").textContent = n;
    }}

    document.getElementById("radius").addEventListener("input", refresh);
    refresh();
  </script>
</body>
</html>
"""

    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Written {len(rows)} stores -> {OUT_HTML}")


if __name__ == "__main__":
    main()
