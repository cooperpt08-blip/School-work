"""Home venue location per team (ESPN abbreviation): lat, lon, elevation (m), UTC offset (standard
time), dome. Used for travel distance, time zones crossed, altitude and indoor/outdoor."""
import math

NBA = {
    "ATL": (33.757, -84.396, 300, -5), "BOS": (42.366, -71.062, 5, -5), "BKN": (40.683, -73.975, 10, -5),
    "CHA": (35.225, -80.839, 230, -5), "CHI": (41.881, -87.674, 180, -6), "CLE": (41.497, -81.688, 200, -5),
    "DAL": (32.790, -96.810, 140, -6), "DEN": (39.749, -105.008, 1609, -7), "DET": (42.341, -83.055, 190, -5),
    "GS": (37.768, -122.388, 5, -8), "HOU": (29.751, -95.362, 15, -6), "IND": (39.764, -86.156, 220, -5),
    "LAC": (33.945, -118.343, 30, -8), "LAL": (34.043, -118.267, 90, -8), "MEM": (35.138, -90.051, 80, -6),
    "MIA": (25.781, -80.188, 2, -5), "MIL": (43.045, -87.917, 190, -6), "MIN": (44.980, -93.276, 260, -6),
    "NO": (29.949, -90.082, 1, -6), "NY": (40.751, -73.993, 10, -5), "OKC": (35.463, -97.515, 370, -6),
    "ORL": (28.539, -81.384, 30, -5), "PHI": (39.901, -75.172, 10, -5), "PHX": (33.446, -112.071, 340, -7),
    "POR": (45.532, -122.667, 15, -8), "SAC": (38.580, -121.500, 10, -8), "SA": (29.427, -98.438, 200, -6),
    "TOR": (43.643, -79.379, 80, -5), "UTAH": (40.768, -111.901, 1300, -7), "WSH": (38.898, -77.021, 20, -5),
}
NFL = {  # last field: dome / retractable roof
    "ARI": (33.528, -112.263, 330, -7, True), "ATL": (33.755, -84.401, 300, -5, True), "BAL": (39.278, -76.623, 10, -5, False),
    "BUF": (42.774, -78.787, 200, -5, False), "CAR": (35.226, -80.853, 230, -5, False), "CHI": (41.862, -87.617, 180, -6, False),
    "CIN": (39.095, -84.516, 150, -5, False), "CLE": (41.506, -81.700, 180, -5, False), "DAL": (32.748, -97.093, 170, -6, True),
    "DEN": (39.744, -105.020, 1609, -7, False), "DET": (42.340, -83.046, 190, -5, True), "GB": (44.501, -88.062, 200, -6, False),
    "HOU": (29.685, -95.411, 15, -6, True), "IND": (39.760, -86.164, 220, -5, True), "JAX": (30.324, -81.637, 5, -5, False),
    "KC": (39.049, -94.484, 270, -6, False), "LAC": (33.953, -118.339, 30, -8, True), "LAR": (33.953, -118.339, 30, -8, True),
    "LV": (36.091, -115.184, 610, -8, True), "MIA": (25.958, -80.239, 2, -5, False), "MIN": (44.974, -93.258, 260, -6, True),
    "NE": (42.091, -71.264, 90, -5, False), "NO": (29.951, -90.081, 1, -6, True), "NYG": (40.814, -74.074, 5, -5, False),
    "NYJ": (40.814, -74.074, 5, -5, False), "PHI": (39.901, -75.168, 10, -5, False), "PIT": (40.447, -80.016, 220, -5, False),
    "SEA": (47.595, -122.332, 5, -8, False), "SF": (37.403, -121.970, 10, -8, False), "TB": (27.976, -82.503, 10, -5, False),
    "TEN": (36.166, -86.771, 130, -6, False), "WSH": (38.908, -76.864, 50, -5, False),
}
# ESPN abbreviation <-> Kalshi ticker code differences
KALSHI_ALIAS = {"nba": {"GSW": "GS", "NYK": "NY", "SAS": "SA", "NOP": "NO", "UTA": "UTAH", "WAS": "WSH", "BRK": "BKN"},
                "nfl": {"WAS": "WSH", "JAC": "JAX", "LA": "LAR"}}


def place(league, abbr):
    t = (NBA if league == "nba" else NFL).get(abbr)
    if not t:
        return None
    return {"lat": t[0], "lon": t[1], "elev": t[2], "tz": t[3], "dome": t[4] if len(t) > 4 else True}


def km(a, b):
    if not a or not b:
        return 0.0
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))
