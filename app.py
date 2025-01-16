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

# Enlarge the “No Moon” checkbox
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
    """Return an emoji for the moon phase."""
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
# LocationIQ city + reverse
########################################
def geocode_city(city_name):
    """City->(lat,lon) with LocationIQ /v1/search."""
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
            else:
                debug_print(f"No results for city: {city_name}")
        else:
            debug_print(f"City lookup code {resp.status_code}, text={resp.text}")
    except Exception as e:
        debug_print(f"City lookup error: {e}")
    return None

def reverse_geocode(lat, lon):
    """(lat,lon)-> city with LocationIQ /v1/reverse."""
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
        else:
            debug_print(f"Reverse code {resp.status_code}, text={resp.text}")
    except Exception as e:
        debug_print(f"Reverse error: {e}")
    return None

########################################
# Find Dark Crossings
########################################
def find_dark_crossings(sun_alts, times_list, local_tz):
    """
    Return (dark_start_str, dark_end_str) by scanning from >=-18 -> < -18 for start,
    then < -18 -> >= -18 for end. If not found, return ("-","-").
    """
    N = len(sun_alts)
    start_str = "-"
    end_str = "-"
    found_start = False

    for i in range(N-1):
        if sun_alts[i] >= -18 and sun_alts[i+1] < -18 and not found_start:
            dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
            start_str = dt_loc.strftime("%H:%M")
            found_start = True
        elif sun_alts[i] < -18 and sun_alts[i+1] >= -18 and found_start and end_str == "-":
            dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
            end_str = dt_loc.strftime("%H:%M")
            break

    return (start_str, end_str)

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
        debug_print(f"DEBUG: day {day_count}, date={current}")

        local_mid = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)
        start_aware = local_tz.localize(local_mid)
        end_aware = local_tz.localize(local_next)
        start_utc = start_aware.astimezone(pytz.utc)
        end_utc = end_aware.astimezone(pytz.utc)

        times_list = [ts.from_datetime(start_utc + timedelta(minutes=i * STEP_MINUTES))
                      for i in range((24 * 60) // STEP_MINUTES + 1)]

        sun_alts = [sun_alt_deg(t) for t in times_list]
        moon_alts = [moon_alt_deg(t) for t in times_list]

        astro_minutes = sum(STEP_MINUTES for i in range(len(sun_alts)-1) if (sun_alts[i]+sun_alts[i+1])/2 < -18)
        moonless_minutes = sum(STEP_MINUTES for i in range(len(sun_alts)-1)
                               if (sun_alts[i]+sun_alts[i+1])/2 < -18 and (moon_alts[i]+moon_alts[i+1])/2 < 0)

        astro_hrs = astro_minutes / 60
        moonless_hrs = moonless_minutes / 60

        dark_start_str, dark_end_str = find_dark_crossings(sun_alts, times_list, local_tz)

        m_rise_str, m_set_str = "-", "-"
        prev_alt = moon_alts[0]
        for i in range(1, len(moon_alts)):
            if prev_alt < 0 and moon_alts[i] >= 0 and m_rise_str == "-":
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                m_rise_str = dt_loc.strftime("%H:%M")
            if prev_alt >= 0 and moon_alts[i] < 0 and m_set_str == "-":
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                m_set_str = dt_loc.strftime("%H:%M")
            prev_alt = moon_alts[i]

        local_noon = local_tz.localize(datetime(current.year, current.month, current.day, 12, 0, 0))
        noon_utc = local_noon.astimezone(pytz.utc)
        t_noon = ts.from_datetime(noon_utc)
        obs_noon = observer.at(t_noon)
        phase_angle = (obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()[1].degrees -
                       obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()[1].degrees) % 360

        day_results.append({
            "date": current.strftime("%Y-%m-%d"),
            "astro_dark_hours": round(astro_hrs, 2),
            "moonless_hours": round(moonless_hrs, 2),
            "dark_start": dark_start_str,
            "dark_end": dark_end_str,
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
    # Subheader and logic...

if __name__ == "__main__":
    main()
