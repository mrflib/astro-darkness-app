############################
# app.py
############################

########## CONFIGURATION-BLOCK ##########
MAX_DAYS = 30
USE_CITY_SEARCH = True
DEBUG = True
######## END CONFIG BLOCK ###############

import streamlit as st
from datetime import date, datetime, timedelta
import requests
import pytz
from timezonefinder import TimezoneFinder
import folium
from streamlit_folium import st_folium
from skyfield.api import load, Topos
import pandas as pd

########################################
# PAGE CONFIG + Custom CSS
########################################
st.set_page_config(
    page_title="Astronomical Darkness Calculator (Night-Labeled)",
    page_icon="🌑",
    layout="centered"
)

# Custom CSS: slightly darker green #218838 for result boxes, 
# plus a “box” style for the city/lat/lon + map container
st.markdown("""
<style>
textarea {
    font-family: "Courier New", monospace;
}
.result-box {
    background-color: #218838; /* darker green */
    color: white;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
    margin: 10px;
}
.result-title {
    font-size: 1.2em;
    margin-bottom: 10px;
}
.result-value {
    font-size: 1.5em;
    font-weight: bold;
}
/* A custom "box" with rounded corners, matching padding */
.city-map-box {
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 12px;
    padding: 15px;
    margin-bottom: 20px;
}
</style>
""", unsafe_allow_html=True)

########################################
# UTILS
########################################
def debug_print(msg: str):
    """Append debug info to session-based console if DEBUG=True."""
    if DEBUG:
        st.session_state["progress_console"] += msg + "\n"

########################################
# MAIN CALC LOGIC
########################################
def compute_night_details(
    lat, lon,
    start_date, end_date,
    step_minutes
):
    """
    For each local day from local noon->noon, label it "Night of D".
    We compute:
      - astro_minutes: sun < -18
      - moonless_minutes: sun < -18 and moon < 0
    Then we find crossing times:
      - Dark Start, Dark End (sun crosses -18)
      - Moon Rise, Moon Set (moon crosses 0)
    Return a list of dicts with columns:
      Night, Dark Start, Dark End, Moon Rise, Moon Set, 
      Dark Hours, Moonless Hours
    """
    from skyfield.api import load, Topos
    ts = load.timescale()
    eph = load('de421.bsp')
    observer = eph['Earth'] + Topos(latitude_degrees=lat, longitude_degrees=lon)

    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
    try:
        local_tz = pytz.timezone(tz_name)
    except:
        local_tz = pytz.utc
        debug_print(f"Unknown tz for {lat},{lon}, using UTC.")
    debug_print(f"Local timezone: {tz_name}")

    nights_data = []
    total_days = (end_date - start_date).days + 1
    for d_i in range(total_days):
        day_label = start_date + timedelta(days=d_i)
        debug_print(f"Processing 'Night of {day_label}' (noon->noon).")

        local_noon = datetime(day_label.year, day_label.month, day_label.day, 12, 0, 0)
        try:
            local_noon_aware = local_tz.localize(local_noon, is_dst=None)
        except:
            local_noon_aware = pytz.utc.localize(local_noon)

        local_next = local_noon_aware + timedelta(days=1)
        start_utc = local_noon_aware.astimezone(pytz.utc)
        end_utc   = local_next.astimezone(pytz.utc)

        total_minutes = int((end_utc - start_utc).total_seconds() // 60)
        steps = total_minutes // step_minutes

        # Build arrays
        times_list = []
        sun_alts = []
        moon_alts = []

        for s in range(steps+1):
            dt_utc = start_utc + timedelta(minutes=s*step_minutes)
            tsky = ts.from_datetime(dt_utc)
            times_list.append(tsky)
            sun_alt = observer.at(tsky).observe(eph['Sun']).apparent().altaz()[0].degrees
            moon_alt = observer.at(tsky).observe(eph['Moon']).apparent().altaz()[0].degrees
            sun_alts.append(sun_alt)
            moon_alts.append(moon_alt)

        # Summations
        astro_minutes = 0
        moonless_minutes = 0
        for idx in range(len(times_list)-1):
            if sun_alts[idx] < -18.0:
                astro_minutes += step_minutes
                if moon_alts[idx] < 0.0:
                    moonless_minutes += step_minutes

        # Crossing times
        dark_start_str = "-"
        dark_end_str   = "-"
        moon_rise_str  = "-"
        moon_set_str   = "-"

        for idx in range(len(sun_alts)-1):
            if sun_alts[idx] >= -18.0 and sun_alts[idx+1] < -18.0 and dark_start_str == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                dark_start_str = dt_loc.strftime("%H:%M")
            if sun_alts[idx] < -18.0 and sun_alts[idx+1] >= -18.0 and dark_end_str == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                dark_end_str = dt_loc.strftime("%H:%M")

        for idx in range(len(moon_alts)-1):
            if moon_alts[idx] < 0.0 and moon_alts[idx+1] >= 0.0 and moon_rise_str == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                moon_rise_str = dt_loc.strftime("%H:%M")
            if moon_alts[idx] >= 0.0 and moon_alts[idx+1] < 0.0 and moon_set_str == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                moon_set_str = dt_loc.strftime("%H:%M")

        # Convert minutes -> "X Hours Y Minutes"
        d_h  = astro_minutes // 60
        d_m  = astro_minutes % 60
        ml_h = moonless_minutes // 60
        ml_m = moonless_minutes % 60

        nights_data.append({
            "Night":        day_label.strftime("%Y-%m-%d"),
            "Dark Start":   dark_start_str,
            "Dark End":     dark_end_str,
            "Moon Rise":    moon_rise_str,
            "Moon Set":     moon_set_str,
            "Dark Hours":   f"{d_h} Hours {d_m} Minutes",
            "Moonless Hours": f"{ml_h} Hours {ml_m} Minutes"
        })

    return nights_data

########################################
# MAIN
########################################
def main():
    st.title("Astronomical Darkness Calculator (Night-Labeled)")
    st.write("Either enter a city, or lat/long, or select a location on the map, then pick your date range and press Calculate.")

    if "progress_console" not in st.session_state:
        st.session_state["progress_console"] = ""
    if "city" not in st.session_state:
        st.session_state["city"] = "Marrakech"
    if "lat" not in st.session_state:
        st.session_state["lat"] = 31.6258
    if "lon" not in st.session_state:
        st.session_state["lon"] = -7.9892
    if "dates_range" not in st.session_state:
        st.session_state["dates_range"] = (date.today(), date.today() + timedelta(days=1))
    if "last_map_click" not in st.session_state:
        st.session_state["last_map_click"] = None

    LOCATIONIQ_TOKEN = st.secrets["locationiq"]["token"]

    # A box for city/lat/lon + map
    with st.container():
        st.markdown('<div class="city-map-box">', unsafe_allow_html=True)
        # Top row: city, lat, lon
        row1 = st.columns(3)
        with row1[0]:
            city_val = st.text_input(
                "City (optional)",
                value=st.session_state["city"],
                help="Type a city name. If recognized, lat/lon updates immediately."
            )
            if city_val != st.session_state["city"]:
                from time import sleep
                coords = geocode_city(city_val, LOCATIONIQ_TOKEN)
                if coords:
                    st.session_state["lat"], st.session_state["lon"] = coords
                    st.session_state["city"] = city_val
                    st.success(f"Updated location => {coords}")
                else:
                    st.warning("City not found or usage limit reached. Keeping old coords.")

        with row1[1]:
            lat_in = st.number_input(
                "Latitude",
                value=st.session_state["lat"],
                format="%.6f",
                min_value=-90.0,
                max_value=90.0
            )
            if abs(lat_in - st.session_state["lat"]) > 1e-7:
                st.session_state["lat"] = lat_in

        with row1[2]:
            lon_in = st.number_input(
                "Longitude",
                value=st.session_state["lon"],
                format="%.6f",
                min_value=-180.0,
                max_value=180.0
            )
            if abs(lon_in - st.session_state["lon"]) > 1e-7:
                st.session_state["lon"] = lon_in

        st.markdown("#### Map (Click to update Lat/Lon)")

        fol_map = folium.Map(location=[st.session_state["lat"], st.session_state["lon"]], zoom_start=6)
        folium.Marker([st.session_state["lat"], st.session_state["lon"]], popup="Current Location").add_to(fol_map)
        map_out = st_folium(fol_map, width=700, height=450)

        if map_out and "last_clicked" in map_out and map_out["last_clicked"]:
            clat = map_out["last_clicked"]["lat"]
            clon = map_out["last_clicked"]["lng"]
            if -90 <= clat <= 90 and -180 <= clon <= 180:
                if st.session_state["last_map_click"] != (clat, clon):
                    st.session_state["lat"] = clat
                    st.session_state["lon"] = clon
                    # optional reverse
                    cfound = reverse_geocode(clat, clon, LOCATIONIQ_TOKEN)
                    if cfound:
                        st.session_state["city"] = cfound
                        st.success(f"Map => {cfound} ({clat:.4f}, {clon:.4f})")
                    else:
                        st.success(f"Map => lat/lon=({clat:.4f}, {clon:.4f})")
                    st.session_state["last_map_click"] = (clat, clon)

        st.markdown('</div>', unsafe_allow_html=True)

    # Next row: date range, moon influence, time step, calc
    st.markdown("### Calculate Darkness")
    with st.form("calc_form"):
        c_cols = st.columns(3)
        with c_cols[0]:
            # date range
            date_range_val = st.date_input(
                "Pick up to 30 days",
                value=st.session_state["dates_range"],
                help="Select 2 dates (noon-labeled)."
