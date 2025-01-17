############################
# app.py (Simplified)
############################

import streamlit as st
from datetime import date, datetime, timedelta
import pytz
from timezonefinder import TimezoneFinder
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from skyfield.api import load, Topos
from time import sleep

########################################
# CONFIG
########################################
st.set_page_config(
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="centered"
)

# Simple custom CSS
st.markdown("""
<style>
    .result-box {
        background-color: #28a745;
        color: white;
        border-radius: 15px;
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
    textarea {
        font-family: "Courier New", monospace;
    }
</style>
""", unsafe_allow_html=True)

########################################
# HELPER FUNCTIONS
########################################
def moon_phase_icon(phase_deg):
    """Simple emoji for moon phase."""
    x = phase_deg % 360
    if x < 22.5 or x >= 337.5:
        return "🌑"
    elif x < 67.5:
        return "🌒"
    elif x < 112.5:
        return "🌓"
    elif x < 157.5:
        return "🌔"
    elif x < 202.5:
        return "🌕"
    elif x < 247.5:
        return "🌖"
    elif x < 292.5:
        return "🌗"
    else:
        return "🌘"

def geocode_city(city, token):
    if not city.strip():
        return None
    url = f"https://us1.locationiq.com/v1/search?key={token}&q={city}&format=json"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list):
                return (float(data[0]["lat"]), float(data[0]["lon"]))
        return None
    except:
        return None

def reverse_geocode(lat, lon, token):
    url = f"https://us1.locationiq.com/v1/reverse?key={token}&lat={lat}&lon={lon}&format=json"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            address = data.get("address", {})
            return address.get("city") or address.get("town") or address.get("village") or data.get("display_name")
        return None
    except:
        return None

def compute_day_details(lat, lon, start_d, end_d, progress_bar, token):
    """Minimal day-by-day astro calc."""
    ts = load.timescale()
    eph = load('de421.bsp')

    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    try:
        local_tz = pytz.timezone(tz_name or "UTC")
    except:
        local_tz = pytz.utc

    topos = Topos(latitude_degrees=lat, longitude_degrees=lon)
    observer = eph['Earth'] + topos

    def sun_alt_deg(t):
        alt, _, _ = observer.at(t).observe(eph['Sun']).apparent().altaz()
        return alt.degrees

    def moon_alt_deg(t):
        alt_m, _, _ = observer.at(t).observe(eph['Moon']).apparent().altaz()
        return alt_m.degrees

    # Build list of days
    results = []
    total_days = (end_d - start_d).days + 1
    progress = 0

    for day_idx in range(total_days):
        # Update progress
        progress = (day_idx + 1) / total_days
        progress_bar.progress(min(progress, 1.0))

        current_date = start_d + timedelta(days=day_idx)
        # Build a times list for that day
        local_mid = datetime(current_date.year, current_date.month, current_date.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)
        try:
            start_aware = local_tz.localize(local_mid)
            end_aware   = local_tz.localize(local_next)
        except:
            start_aware = pytz.utc.localize(local_mid)
            end_aware   = pytz.utc.localize(local_next)

        start_utc = start_aware.astimezone(pytz.utc)
        end_utc   = end_aware.astimezone(pytz.utc)

        # Steps (simplified, always 1 min => 1440 steps)
        step_minutes = 1
        ts_list = []
        for m in range(1441):
            dt_utc = start_utc + timedelta(minutes=m)
            ts_list.append(ts.from_datetime(dt_utc))

        sun_alts = []
        moon_alts = []
        for t_ in ts_list:
            sun_alts.append(sun_alt_deg(t_))
            moon_alts.append(moon_alt_deg(t_))

        # Summaries
        astro_minutes = 0
        moonless_minutes = 0
        for i in range(len(ts_list)-1):
            s_mid = (sun_alts[i] + sun_alts[i+1]) / 2
            m_mid = (moon_alts[i] + moon_alts[i+1]) / 2
            if s_mid < -18.0:
                astro_minutes += 1
                if m_mid < 0.0:
                    moonless_minutes += 1

        astro_hrs = astro_minutes // 60
        astro_mins = astro_minutes % 60
        moonless_hrs = moonless_minutes // 60
        moonless_mins = moonless_minutes % 60

        # Calculate moon phase at local noon
        local_noon = datetime(current_date.year, current_date.month, current_date.day, 12, 0, 0)
        try:
            noon_aware = local_tz.localize(local_noon)
        except:
            noon_aware = pytz.utc.localize(local_noon)
        noon_utc = noon_aware.astimezone(pytz.utc)
        t_noon    = ts.from_datetime(noon_utc)
        obs_noon  = observer.at(t_noon)
        sun_ecl   = obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl  = obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360

        results.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "astro_dark_hours": f"{astro_hrs} Hours {astro_mins} Minutes",
            "moonless_hours":   f"{moonless_hrs} Hours {moonless_mins} Minutes",
            "moon_phase":       moon_phase_icon(phase_angle)
        })

    return results

########################################
# MAIN
########################################
def main():
    st.title("Astronomical Darkness Calculator (Simplified)")
    st.write(f"Running Streamlit version: {st.__version__}")

    # Session defaults
    if "city" not in st.session_state:
        st.session_state["city"] = "Marrakech"
    if "lat" not in st.session_state:
        st.session_state["lat"] = 31.6258
    if "lon" not in st.session_state:
        st.session_state["lon"] = -7.9892
    if "progress_console" not in st.session_state:
        st.session_state["progress_console"] = ""
    if "selected_range" not in st.session_state:
        # TWO-element date range => single pop-up
        st.session_state["selected_range"] = (date.today(), date.today() + timedelta(days=1))
    if "last_map_click" not in st.session_state:
        st.session_state["last_map_click"] = None

    LOCATIONIQ_TOKEN = st.secrets["locationiq"]["token"]

    # City & Date Range
    st.subheader("Inputs")
    input_cols = st.columns(2)
    with input_cols[0]:
        # City input
        city_val = st.text_input("City (optional)", value=st.session_state["city"])
        if city_val != st.session_state["city"]:
            coords = geocode_city(city_val, LOCATIONIQ_TOKEN)
            if coords:
                st.session_state["lat"], st.session_state["lon"] = coords
                st.session_state["city"] = city_val
                st.success(f"Lat/lon updated for {city_val} -> {coords}")
            else:
                st.warning("City not found or blocked.")
    with input_cols[1]:
        # Two-element date range
        st.session_state["selected_range"] = st.date_input(
            "Select date range",
            value=st.session_state["selected_range"],  # (start, end)
            format="YYYY/MM/DD"
        )

    # Coordinates & Map
    st.subheader("Coordinates & Map")
    coord_cols = st.columns(2)
    with coord_cols[0]:
        lat_in = st.number_input("Latitude", value=st.session_state["lat"], format="%.6f")
        if abs(lat_in - st.session_state["lat"]) > 1e-8:
            st.session_state["lat"] = lat_in

        lon_in = st.number_input("Longitude", value=st.session_state["lon"], format="%.6f")
        if abs(lon_in - st.session_state["lon"]) > 1e-8:
            st.session_state["lon"] = lon_in

    with coord_cols[1]:
        st.markdown("**Click map to set location**")
        folium_map = folium.Map(location=[st.session_state["lat"], st.session_state["lon"]], zoom_start=5)
        folium.Marker(
            [st.session_state["lat"], st.session_state["lon"]], 
            popup="Current Location"
        ).add_to(folium_map)
        map_click = st_folium(folium_map, width=500, height=350)

        if map_click and "last_clicked" in map_click and map_click["last_clicked"]:
            c_lat = map_click["last_clicked"]["lat"]
            c_lon = map_click["last_clicked"]["lng"]
            if -90 <= c_lat <= 90 and -180 <= c_lon <= 180:
                if st.session_state["last_map_click"] != (c_lat, c_lon):
                    st.session_state["lat"] = c_lat
                    st.session_state["lon"] = c_lon
                    ccity = reverse_geocode(c_lat, c_lon, LOCATIONIQ_TOKEN)
                    if ccity:
                        st.session_state["city"] = ccity
                        st.success(f"Updated to {ccity} ({c_lat}, {c_lon})")
                    else:
                        st.success(f"Updated lat/lon to ({c_lat:.4f}, {c_lon:.4f})")
                    st.session_state["last_map_click"] = (c_lat, c_lon)
            else:
                st.warning("Map click out of valid bounds?")

    # Calculate Button
    st.subheader("Calculate Darkness")
    calc_button = st.button("Calculate")

    # Progress & Console
    progress_holder = st.empty()
    progress_bar = progress_holder.progress(0)
    console_holder = st.empty()
    st.session_state["progress_console"] = ""  # Not used heavily in simplified code

    if calc_button:
        if isinstance(st.session_state["selected_range"], (list, tuple)) and len(st.session_state["selected_range"]) == 2:
            s_date, e_date = st.session_state["selected_range"]
            if s_date > e_date:
                st.error("Start date must be <= end date.")
                st.stop()

            # Perform calculations
            daily_data = compute_day_details(
                st.session_state["lat"],
                st.session_state["lon"],
                s_date,
                e_date,
                progress_bar,
                LOCATIONIQ_TOKEN
            )
            progress_bar.progress(1.0)

            if not daily_data:
                st.warning("No data, possibly invalid date range.")
                st.stop()

            # Summaries
            total_astro = 0
            total_moonless = 0
            for item in daily_data:
                # e.g. "4 Hours 25 Minutes"
                astro_parts = item["astro_dark_hours"].split()
                a_h, a_m = int(astro_parts[0]), int(astro_parts[2])
                moonless_parts = item["moonless_hours"].split()
                m_h, m_m = int(moonless_parts[0]), int(moonless_parts[2])
                total_astro += a_h*60 + a_m
                total_moonless += m_h*60 + m_m

            ta_hrs = total_astro // 60
            ta_mins = total_astro % 60
            tm_hrs = total_moonless // 60
            tm_mins = total_moonless % 60

            # Display results
            st.markdown("### Results")
            colA, colB = st.columns(2)
            with colA:
                st.markdown(f"""
                <div class="result-box">
                    <div class="result-title">Total Astro Darkness</div>
                    <div class="result-value">{ta_hrs} Hours {ta_mins} Minutes</div>
                </div>
                """, unsafe_allow_html=True)
            with colB:
                st.markdown(f"""
                <div class="result-box">
                    <div class="result-title">Moonless Darkness</div>
                    <div class="result-value">{tm_hrs} Hours {tm_mins} Minutes</div>
                </div>
                """, unsafe_allow_html=True)

            # Day-by-day table
            st.markdown("#### Day-by-Day Breakdown")
            df = pd.DataFrame(daily_data)
            df = df.rename(columns={
                "date": "Date",
                "astro_dark_hours": "Astro (hrs)",
                "moonless_hours": "Moonless (hrs)",
                "moon_phase": "Phase"
            })
            st.dataframe(df, use_container_width=True)
        else:
            st.error("Please pick a valid two-date range before calculating.")

    else:
        st.info("Pick a date range and click **Calculate** to see results.")
