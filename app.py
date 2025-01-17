############################
# app.py
############################

########## CONFIGURATION-BLOCK ##########
MAX_DAYS = 30           # Maximum number of days user can pick
USE_CITY_SEARCH = True  # Whether city name -> lat/lon via LocationIQ is enabled
DEBUG = True            # Toggle debug messages in the console
######## END CONFIG BLOCK ###############

import streamlit as st
from datetime import date, datetime, timedelta
import requests
import pytz
from timezonefinder import TimezoneFinder
import folium
from streamlit_folium import st_folium
from skyfield.api import load, Topos
from time import sleep
import pandas as pd

########################################
# PAGE CONFIG + Custom CSS
########################################
st.set_page_config(
    page_title="Astronomical Darkness Calculator (Night-Labeled)",
    page_icon="🌑",
    layout="centered"
)

# Minimal custom CSS
st.markdown("""
<style>
textarea {
    font-family: "Courier New", monospace;
}
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
</style>
""", unsafe_allow_html=True)

########################################
# UTILS
########################################
def debug_print(msg: str):
    """Append a debug message to the session-based console."""
    if DEBUG:
        st.session_state["progress_console"] += msg + "\n"

def moon_phase_icon(phase_deg):
    """
    Return an emoji for the moon phase based on the angle difference 
    between the Sun and Moon in ecliptic longitude.
    """
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

def geocode_city(city_name, token):
    """
    City -> (lat, lon) using LocationIQ /v1/search.
    Returns None if no result or error.
    """
    if not USE_CITY_SEARCH or not city_name.strip():
        return None
    url = f"https://us1.locationiq.com/v1/search?key={token}&q={city_name}&format=json"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                return (lat, lon)
            else:
                debug_print(f"No results for city: {city_name}")
        else:
            debug_print(f"City lookup code {resp.status_code}, text={resp.text}")
    except Exception as e:
        debug_print(f"City lookup error: {e}")
    return None

def reverse_geocode(lat, lon, token):
    """
    (lat, lon) -> city using LocationIQ /v1/reverse.
    Returns None if no result or error.
    """
    if not USE_CITY_SEARCH:
        return None
    url = f"https://us1.locationiq.com/v1/reverse?key={token}&lat={lat}&lon={lon}&format=json"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            address = data.get("address", {})
            city = address.get("city") or address.get("town") or address.get("village")
            return city if city else data.get("display_name")
        else:
            debug_print(f"Reverse code {resp.status_code}, text={resp.text}")
    except Exception as e:
        debug_print(f"Reverse error: {e}")
    return None


########################################
# NIGHT-LABELED NOON→NOON CALC
########################################
def compute_night_details(
    lat, lon,
    start_date, end_date,
    moon_affect,  # "Include Moonlight" or "Ignore Moonlight"
    step_minutes,
    progress_bar,
    token
):
    """
    For each local day in [start_date, end_date], define day D as local noon D -> local noon D+1.
    Label that entire block "Night of D". 

    ***IMPORTANT:***
    - "Include Moonlight" => we do *not* subtract times with the Moon above horizon.
      So astro_minutes counts all minutes sun<-18, and moonless_minutes is the *subset* with moon<0.
      The total 'Astro Darkness' is bigger because we do not exclude moonlit times.
    - "Ignore Moonlight" => we *only* count minutes when the Moon is *also* below horizon 
      => results in a smaller total for astro darkness.
    """
    debug_print("Starting Night-labeled calculations...")
    ts = load.timescale()
    eph = load('de421.bsp')
    observer = eph['Earth'] + Topos(latitude_degrees=lat, longitude_degrees=lon)

    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
    try:
        local_tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        local_tz = pytz.utc
        debug_print(f"Unknown tz for {lat},{lon}. Using UTC.")
    debug_print(f"Local timezone: {tz_name}")

    night_data = []
    total_days = (end_date - start_date).days + 1
    if total_days < 1:
        debug_print("No days in range => returning empty.")
        return []

    for i in range(total_days):
        fraction = (i+1) / total_days
        progress_bar.progress(min(fraction, 1.0))

        # Label date
        label_date = start_date + timedelta(days=i)
        debug_print(f"Processing Night of {label_date}")

        # local noon => next local noon
        local_noon_dt = datetime(label_date.year, label_date.month, label_date.day, 12, 0, 0)
        try:
            local_noon_aware = local_tz.localize(local_noon_dt, is_dst=None)
        except:
            local_noon_aware = pytz.utc.localize(local_noon_dt)
        local_next = local_noon_aware + timedelta(days=1)

        start_utc = local_noon_aware.astimezone(pytz.utc)
        end_utc   = local_next.astimezone(pytz.utc)
        total_minutes = int((end_utc - start_utc).total_seconds() // 60)
        steps = total_minutes // step_minutes

        times_list = []
        for s in range(steps+1):
            dt_utc = start_utc + timedelta(minutes=s*step_minutes)
            times_list.append(ts.from_datetime(dt_utc))

        # We'll accumulate minutes in 2 ways:
        # 1) astro_minutes => minutes sun < -18
        # 2) moonless_minutes => minutes sun < -18 AND moon < 0 (only relevant if user picks "Ignore Moonlight"?)
        # But we'll compute both anyway and interpret them accordingly.
        astro_minutes = 0
        moonless_minutes = 0

        for idx in range(len(times_list)-1):
            t_ = times_list[idx]
            sun_alt_deg = observer.at(t_).observe(eph['Sun']).apparent().altaz()[0].degrees
            moon_alt_deg = observer.at(t_).observe(eph['Moon']).apparent().altaz()[0].degrees

            if sun_alt_deg < -18.0:
                astro_minutes += step_minutes

                # Also count if the moon is below horizon
                if moon_alt_deg < 0.0:
                    moonless_minutes += step_minutes

        # Now interpret them depending on user choice:
        # "Include Moonlight" => show astro_minutes as the big total, 
        #   the user sees that as "Astro Darkness." 
        #   We won't subtract times the moon is up. 
        # "Ignore Moonlight" => the "true" astro darkness is the subset with moon below horizon => moonless_minutes.

        if moon_affect == "Include Moonlight":
            # The "big" total is astro_minutes. We'll store that as "astro_dark_hours"
            # The smaller subset is moonless_minutes, but we won't actually use that as the final total 
            # (the user won't see a second column).
            final_astro = astro_minutes
        else:
            # "Ignore Moonlight" => we only want the smaller subset
            final_astro = moonless_minutes

        a_h = final_astro // 60
        a_m = final_astro % 60

        # We'll store a second field "moonless_hours" for reference 
        # so we can show or hide in the final display. 
        # If ignoring moonlight, astro==moonless. If including, astro is bigger, moonless is smaller.
        mo_h = moonless_minutes // 60
        mo_m = moonless_minutes % 60

        # Moon phase at local noon
        local_noon_utc = local_noon_aware.astimezone(pytz.utc)
        t_noon = ts.from_datetime(local_noon_utc)
        obs_noon = observer.at(t_noon)
        sun_ecl  = obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360

        night_data.append({
            "night_label": label_date.strftime("%Y-%m-%d"),
            "astro_dark_hours": f"{a_h} Hours {a_m} Minutes",
            "moonless_hours":   f"{mo_h} Hours {mo_m} Minutes",
            "moon_phase": moon_phase_icon(phase_angle)
        })

    return night_data

########################################
# MAIN
########################################
def main():
    st.markdown("<h2>Astronomical Darkness Calculator (Night-Labeled)</h2>", unsafe_allow_html=True)
    st.markdown("""
    <h4>
    This tool calculates how many hours of 'astro dark' (Sun below -18°) you get, 
    labeling each night by the local noon date it starts. 
    Perfect for planning extended nights without splitting at midnight!
    </h4>
    """, unsafe_allow_html=True)

    st.write(f"**Running Streamlit version:** {st.__version__}")

    # Initialize session
    if "progress_console" not in st.session_state:
        st.session_state["progress_console"] = ""
    if "city" not in st.session_state:
        st.session_state["city"] = "Marrakech"
    if "lat" not in st.session_state:
        st.session_state["lat"] = 31.6258
    if "lon" not in st.session_state:
        st.session_state["lon"] = -7.9892
    if "dates_range" not in st.session_state:
        # By default, pick today + tomorrow
        st.session_state["dates_range"] = (date.today(), date.today() + timedelta(days=1))
    if "last_map_click" not in st.session_state:
        st.session_state["last_map_click"] = None

    # Retrieve token
    LOCATIONIQ_TOKEN = st.secrets["locationiq"]["token"]

    # Row 1: city, date range, time step
    st.markdown("#### Inputs")
    row1 = st.columns(3)

    with row1[0]:
        city_val = st.text_input(
            "City (optional)",
            value=st.session_state["city"],
            help="Enter a city name (e.g., 'London'). We attempt lat/lon if recognized."
        )
        if city_val != st.session_state["city"]:
            coords = geocode_city(city_val, LOCATIONIQ_TOKEN)
            if coords:
                st.session_state["lat"], st.session_state["lon"] = coords
                st.session_state["city"] = city_val
                st.success(f"Updated lat/lon for '{city_val}' => {coords}")
            else:
                st.warning("City not found or usage limit reached. Keeping previous coords.")

    with row1[1]:
        # Let date_input store final result in st.session_state itself
        dates_range = st.date_input(
            "Pick up to 30 days (Night-labeled)",
            value=st.session_state["dates_range"],
            help=("Select two dates in a single pop-up. We'll treat each local day as noon→noon, "
                  "so all nighttime belongs to the day it started. Up to 30 days allowed."),
            key="dates_range"
        )

    with row1[2]:
        step_choices = ["1", "2", "5", "10", "15", "30"]
        step_mins_str = st.selectbox(
            "Time Step (Mins)",
            options=step_choices,
            index=0,
            help="Lower = more accurate but slower. E.g., '1' => 1440 steps/day; '30' => 48 steps/day."
        )
        step_minutes = int(step_mins_str)

    # Row 2: lat, lon, moon influence
    row2 = st.columns(3)
    with row2[0]:
        lat_in = st.number_input(
            "Latitude",
            value=st.session_state["lat"],
            format="%.6f",
            min_value=-90.0,
            max_value=90.0,
            help="Decimal degrees latitude (e.g., 51.5074 for London)."
        )
        if abs(lat_in - st.session_state["lat"]) > 1e-7:
            st.session_state["lat"] = lat_in

    with row2[1]:
        lon_in = st.number_input(
            "Longitude",
            value=st.session_state["lon"],
            format="%.6f",
            min_value=-180.0,
            max_value=180.0,
            help="Decimal degrees longitude (e.g., -0.1278 for London)."
        )
        if abs(lon_in - st.session_state["lon"]) > 1e-7:
            st.session_state["lon"] = lon_in

    with row2[2]:
        # Default is "Include Moonlight" => bigger total
        moon_mode = st.selectbox(
            "Moon Influence",
            options=["Include Moonlight", "Ignore Moonlight"],
            index=0,
            help=("Include Moonlight => we do NOT subtract times the moon is up (bigger total). "
                  "Ignore Moonlight => we ONLY count times the moon is below horizon (smaller total).")
        )

    # Map
    st.markdown("#### Select Location on Map")
    with st.expander("View / Click Map"):
        folium_map = folium.Map(location=[st.session_state["lat"], st.session_state["lon"]], zoom_start=6)
        folium.Marker(
            [st.session_state["lat"], st.session_state["lon"]],
            popup="Current Location"
        ).add_to(folium_map)
        map_res = st_folium(folium_map, width=700, height=450)

        if map_res and "last_clicked" in map_res and map_res["last_clicked"]:
            clat = map_res["last_clicked"]["lat"]
            clon = map_res["last_clicked"]["lng"]
            if -90 <= clat <= 90 and -180 <= clon <= 180:
                if st.session_state["last_map_click"] != (clat, clon):
                    st.session_state["lat"] = clat
                    st.session_state["lon"] = clon
                    ccity = reverse_geocode(clat, clon, LOCATIONIQ_TOKEN)
                    if ccity:
                        st.session_state["city"] = ccity
                        st.success(f"Map click -> {ccit
