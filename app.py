############################
# app.py
############################

########## CONFIGURATION BLOCK ##########
MAX_DAYS = 30
STEP_MINUTES = 1
USE_CITY_SEARCH = True
DEBUG = True
LOCATIONIQ_TOKEN = "pk.adea9a047c0d5d483f99ee4ae1b4b08d"
######## END CONFIG BLOCK ###############

import streamlit as st
from datetime import date, datetime, timedelta
import pytz
from timezonefinder import TimezoneFinder
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from skyfield.api import load, Topos

########################################
# PAGE CONFIG + Custom CSS
########################################
st.set_page_config(
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="centered"
)

st.markdown("""
<style>
    .stCheckbox > div:first-child {
        transform: scale(1.2); 
        margin-top: 5px;
        margin-bottom: 5px;
    }
</style>
""", unsafe_allow_html=True)

########################################
# UTILS
########################################
def debug_print(msg: str):
    if DEBUG:
        st.write(msg)

def moon_phase_icon(phase_deg):
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

########################################
# LocationIQ Geocoding Functions
########################################
def geocode_city(city_name):
    if not USE_CITY_SEARCH or not city_name.strip():
        return None
    url = f"https://us1.locationiq.com/v1/search?key={LOCATIONIQ_TOKEN}&q={city_name}&format=json"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                return (lat, lon)
    except Exception as e:
        debug_print(f"City lookup error: {e}")
    return None

def reverse_geocode(lat, lon):
    if not USE_CITY_SEARCH:
        return None
    url = f"https://us1.locationiq.com/v1/reverse?key={LOCATIONIQ_TOKEN}&lat={lat}&lon={lon}&format=json"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            address = data.get("address", {})
            city = address.get("city") or address.get("town") or address.get("village")
            return city if city else data.get("display_name")
    except Exception as e:
        debug_print(f"Reverse geocode error: {e}")
    return None

########################################
# Astro Calculation
########################################
@st.cache_data
def compute_day_details(lat, lon, start_date, end_date, no_moon):
    debug_print("DEBUG: Entering compute_day_details")

    ts = load.timescale()
    eph = load('de421.bsp')
    debug_print("DEBUG: Loaded timescale & ephemeris")

    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
    local_tz = pytz.timezone(tz_name)
    debug_print(f"DEBUG: local_tz={tz_name}")

    topos = Topos(latitude_degrees=lat, longitude_degrees=lon)
    observer = eph['Earth'] + topos

    def sun_alt_deg(t):
        app_sun = observer.at(t).observe(eph['Sun']).apparent()
        alt, _, _ = app_sun.altaz()
        return alt.degrees

    def moon_alt_deg(t):
        app_moon = observer.at(t).observe(eph['Moon']).apparent()
        alt_m, _, _ = app_moon.altaz()
        return alt_m.degrees

    day_results = []
    day_count = 0
    current = start_date

    while current <= end_date and day_count < MAX_DAYS:
        debug_print(f"DEBUG: Day {day_count}, date={current}")

        local_mid = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)
        start_aware = local_tz.localize(local_mid)
        end_aware = local_tz.localize(local_next)
        start_utc = start_aware.astimezone(pytz.utc)
        end_utc = end_aware.astimezone(pytz.utc)

        step_count = (24*60)//STEP_MINUTES
        times_list = []
        for i in range(step_count+1):
            dt_utc = start_utc + timedelta(minutes=i*STEP_MINUTES)
            times_list.append(ts.from_datetime(dt_utc))

        sun_alts = []
        moon_alts = []
        for t_ in times_list:
            s_alt = sun_alt_deg(t_)
            m_alt = moon_alt_deg(t_)
            sun_alts.append(s_alt)
            moon_alts.append(m_alt)

        # Summation
        astro_minutes = 0
        moonless_minutes = 0
        for i in range(len(times_list)-1):
            s_mid = (sun_alts[i] + sun_alts[i+1])/2
            m_mid = (moon_alts[i] + moon_alts[i+1])/2
            if s_mid < -18.0:  # astro dark
                astro_minutes += STEP_MINUTES
                if no_moon:
                    if m_mid < 0.0:
                        moonless_minutes += STEP_MINUTES
                else:
                    moonless_minutes += STEP_MINUTES

        astro_hrs = astro_minutes/60.0
        moonless_hrs = moonless_minutes/60.0
        debug_print(f"DEBUG: date={current}, astro_hrs={astro_hrs:.2f}, moonless_hrs={moonless_hrs:.2f}")

        # Dark start/end
        start_str = "-"
        end_str = "-"
        for i in range(len(sun_alts)-1):
            if sun_alts[i] >= -18 and sun_alts[i+1] < -18 and start_str == "-":
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                start_str = dt_loc.strftime("%H:%M")
            if sun_alts[i] < -18 and sun_alts[i+1] >= -18 and end_str == "-":
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                end_str = dt_loc.strftime("%H:%M")

        # Set end_str to the last time if no crossing found
        if end_str == "-":
            dt_loc = times_list[-1].utc_datetime().astimezone(local_tz)
            end_str = dt_loc.strftime("%H:%M")

        # Moon rise/set
        m_rise_str = "-"
        m_set_str = "-"
        prev_alt = moon_alts[0]
        for i in range(1, len(moon_alts)):
            if prev_alt < 0 and moon_alts[i] >= 0 and m_rise_str == "-":
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                m_rise_str = dt_loc.strftime("%H:%M")
            if prev_alt >= 0 and moon_alts[i] < 0 and m_set_str == "-":
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                m_set_str = dt_loc.strftime("%H:%M")
            prev_alt = moon_alts[i]

        # Moon phase at local noon
        local_noon = datetime(current.year, current.month, current.day, 12, 0, 0)
        local_noon_aware = local_tz.localize(local_noon)
        noon_utc = local_noon_aware.astimezone(pytz.utc)
        t_noon = ts.from_datetime(noon_utc)
        obs_noon = observer.at(t_noon)
        sun_ecl = obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360

        day_results.append({
            "date": current.strftime("%Y-%m-%d"),
            "astro_dark_hours": round(astro_hrs, 2),
            "moonless_hours": round(moonless_hrs, 2),
            "dark_start": start_str,
            "dark_end": end_str,
            "moon_rise": m_rise_str,
            "moon_set": m_set_str,
            "moon_phase": moon_phase_icon(phase_angle)
        })

        current += timedelta(days=1)
        day_count += 1

    return day_results

########################################
# MAIN
########################################
def main():
    st.title("Astronomical Darkness Calculator")
    st.subheader("Plan your astronomy holidays by finding areas with maximum darkness and minimal moonlight.")

    if "city" not in st.session_state:
        st.session_state["city"] = "Marrakech"
    if "lat" not in st.session_state:
        st.session_state["lat"] = 31.6258
    if "lon" not in st.session_state:
        st.session_state["lon"] = -7.9892
    if "start_date" not in st.session_state:
        st.session_state["start_date"] = date(2025, 10, 15)
    if "end_date" not in st.session_state:
        st.session_state["end_date"] = date(2025, 10, 16)

    row1_col1, row1_col2 = st.columns([2, 1])
    with row1_col1:
        city = st.text_input(
            "City (optional)",
            value=st.session_state["city"],
            help="Enter a city name (e.g., 'London').",
        )
        if city:
            coords = geocode_city(city)
            if coords:
                st.session_state["lat"], st.session_state["lon"] = coords
                st.session_state["city"] = city
    with row1_col2:
        date_range = st.date_input(
            f"Pick up to {MAX_DAYS} days",
            [st.session_state["start_date"], st.session_state["end_date"]],
            min_value=date(2000, 1, 1),
            max_value=date.today() + timedelta(days=MAX_DAYS - 1),
            help=f"Select a date range of up to {MAX_DAYS} days."
        )
        if len(date_range) == 2:
            st.session_state["start_date"], st.session_state["end_date"] = date_range

    lat = st.number_input("Latitude", value=st.session_state["lat"], format="%.6f")
    lon = st.number_input("Longitude", value=st.session_state["lon"], format="%.6f")

    no_moon = st.checkbox("No Moon", value=False, help="Exclude times when the Moon is above the horizon.")

    # Map
    with st.expander("Pick on Map"):
        map_center = [st.session_state["lat"], st.session_state["lon"]]
        map_widget = folium.Map(location=map_center, zoom_start=5)
        folium.Marker(location=map_center, tooltip="Current Location").add_to(map_widget)
        clicked = st_folium(map_widget, width=700, height=500)

        if clicked and "last_clicked" in clicked:
            lat_clicked, lon_clicked = clicked["last_clicked"]["lat"], clicked["last_clicked"]["lng"]
            reverse_city = reverse_geocode(lat_clicked, lon_clicked)
            st.session_state["lat"], st.session_state["lon"] = lat_clicked, lon_clicked
            if reverse_city:
                st.session_state["city"] = reverse_city

    if st.button("Calculate"):
        results = compute_day_details(lat, lon, st.session_state["start_date"], st.session_state["end_date"], no_moon)
        if results:
            total_astro = sum(d["astro_dark_hours"] for d in results)
            total_moonless = sum(d["moonless_hours"] for d in results)

            st.subheader("Results")
            st.success(f"Total Astronomical Darkness: {total_astro:.2f} hrs")
            st.success(f"Moonless Darkness: {total_moonless:.2f} hrs")

            st.subheader("Day-by-Day Breakdown")
            df = pd.DataFrame(results)
            st.table(df.rename(columns={
                "date": "Date",
                "astro_dark_hours": "Astro (hrs)",
                "moonless_hours": "Moonless (hrs)",
                "dark_start": "Dark Start",
                "dark_end": "Dark End",
                "moon_rise": "Moonrise",
                "moon_set": "Moonset",
                "moon_phase": "Phase"
            }))

if __name__ == "__main__":
    main()
