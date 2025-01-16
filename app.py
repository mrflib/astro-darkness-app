############################
# app.py - Using LocationIQ for City Geocoding
############################

########## CONFIGURATION BLOCK ##########
MAX_DAYS = 30         # how many days to allow
STEP_MINUTES = 1      # how many minutes between each step
USE_CITY_SEARCH = True 
DEBUG = True
SHOW_BULLETS = False   # hide bullets, per your request
LOCATIONIQ_TOKEN = "pk.adea9a047c0d5d483f99ee4ae1b4b08d"  # your public token
######## END CONFIG BLOCK ###############

import streamlit as st
from datetime import date, datetime, timedelta
import pytz
from timezonefinder import TimezoneFinder
import pandas as pd
import requests

from skyfield.api import load, Topos

# For the map
import folium
from streamlit_folium import st_folium

########################################
# PAGE CONFIG + Custom CSS for No Moon
########################################
st.set_page_config(
    page_title="Astronomical Darkness Calculator (LocationIQ)",
    page_icon="🌑",
    layout="centered"
)

# Inline CSS to enlarge the No Moon checkbox
st.markdown("""
<style>
    .stCheckbox > div:first-child {
        transform: scale(1.3); 
        margin-top: 8px;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

########################################
# UTILS
########################################
def debug_print(msg: str):
    """Helper to conditionally print debug statements."""
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
# LocationIQ GEOCODING
########################################
def geocode_city(city_name):
    """
    Use LocationIQ's /v1/search endpoint to convert city -> (lat,lon).
    Returns (lat,lon) float or None if not found.
    """
    if not USE_CITY_SEARCH or not city_name.strip():
        return None
    token = LOCATIONIQ_TOKEN
    url = f"https://us1.locationiq.com/v1/search?key={token}&q={city_name}&format=json"
    headers = {"accept": "application/json"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data)>0:
                # Take the first result
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                return (lat, lon)
        else:
            debug_print(f"DEBUG: City lookup failed with code {resp.status_code}")
    except Exception as e:
        debug_print(f"DEBUG: City lookup error: {e}")
    return None

def reverse_geocode(lat, lon):
    """
    Use LocationIQ's /v1/reverse endpoint to convert (lat,lon)-> city.
    Returns city name or None if not found.
    """
    token = LOCATIONIQ_TOKEN
    url = f"https://us1.locationiq.com/v1/reverse?key={token}&lat={lat}&lon={lon}&format=json"
    headers = {"accept": "application/json"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # We can parse city or display_name
            address = data.get("address", {})
            # Try city, town, village, etc
            city = address.get("city") or address.get("town") or address.get("village")
            if city:
                return city
            # fallback
            return data.get("display_name")
        else:
            debug_print(f"DEBUG: Reverse geocode failed code {resp.status_code}")
    except Exception as e:
        debug_print(f"DEBUG: Reverse geocode error: {e}")
    return None

########################################
# Astronomy Calculation (unchanged)
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
        alt_moon, _, _ = app_moon.altaz()
        return alt_moon.degrees

    max_days = MAX_DAYS
    day_results = []
    day_count = 0
    current = start_date

    while current <= end_date and day_count < max_days:
        debug_print(f"DEBUG: Day {day_count}, date={current}")
        local_mid = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)

        start_aware = local_tz.localize(local_mid)
        end_aware = local_tz.localize(local_next)
        start_utc = start_aware.astimezone(pytz.utc)
        end_utc = end_aware.astimezone(pytz.utc)

        # Build times
        steps_per_day = (24*60)//STEP_MINUTES
        debug_print(f"DEBUG: steps_per_day={steps_per_day} for date={current}")
        times_list = []
        for i in range(steps_per_day+1):
            dt_utc = start_utc + timedelta(minutes=i*STEP_MINUTES)
            times_list.append(ts.from_datetime(dt_utc))

        sun_alts = []
        moon_alts = []
        for i in range(len(times_list)):
            alt_sun = sun_alt_deg(times_list[i])
            alt_moon = moon_alt_deg(times_list[i])
            sun_alts.append(alt_sun)
            moon_alts.append(alt_moon)

        debug_print(f"DEBUG: built alt arrays, length={len(sun_alts)}")

        # Summation
        astro_minutes = 0
        moonless_minutes = 0
        for i in range(len(times_list)-1):
            s_mid = (sun_alts[i] + sun_alts[i+1]) / 2.0
            m_mid = (moon_alts[i] + moon_alts[i+1]) / 2.0
            if s_mid < -18.0:
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
        start_dark_str = "-"
        end_dark_str = "-"
        found_dark = False
        for i in range(len(sun_alts)-1):
            if sun_alts[i] < -18 and not found_dark:
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                start_dark_str = dt_loc.strftime("%H:%M")
                found_dark = True
            if found_dark and sun_alts[i]>=-18:
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                end_dark_str = dt_loc.strftime("%H:%M")
                break
        if found_dark and end_dark_str=="-":
            dt_loc = times_list[-1].utc_datetime().astimezone(local_tz)
            end_dark_str = dt_loc.strftime("%H:%M")

        # Moon rise/set
        m_rise_str = "-"
        m_set_str = "-"
        prev_alt = moon_alts[0]
        for i in range(1, len(moon_alts)):
            if prev_alt<0 and moon_alts[i]>=0 and m_rise_str=="-":
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                m_rise_str = dt_loc.strftime("%H:%M")
            if prev_alt>=0 and moon_alts[i]<0 and m_set_str=="-":
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
            "astro_dark_hours": round(astro_hrs,2),
            "moonless_hours": round(moonless_hrs,2),
            "dark_start": start_dark_str,
            "dark_end": end_dark_str,
            "moon_rise": m_rise_str,
            "moon_set": m_set_str,
            "moon_phase": moon_phase_icon(phase_angle)
        })

        current += timedelta(days=1)
        day_count+=1

    debug_print("DEBUG: Exiting compute_day_details, returning results.")
    return day_results

def main():
    st.subheader("Input Lat/Lon (Optional City if USE_CITY_SEARCH=True)")

    lat_default = 31.6258
    lon_default = -7.9892

    if USE_CITY_SEARCH:
        city_input = st.text_input(
            "City Name (optional)", 
            value="Marrakech"  # default
        )
        if city_input:
            coords = geocode_city(city_input)  # Use LocationIQ-based function
            if coords:
                lat_default, lon_default = coords
            else:
                st.warning("City not found or blocked. Please use lat/lon below.")

    # Two columns for lat/lon
    col_lat, col_lon = st.columns(2)
    with col_lat:
        lat_in = st.number_input("Latitude", value=lat_default, format="%.6f")
    with col_lon:
        lon_in = st.number_input("Longitude", value=lon_default, format="%.6f")

    # Two columns for date range & no moon
    col_date, col_checkbox = st.columns([2,1])
    with col_date:
        d_range = st.date_input(f"Pick up to {MAX_DAYS} days", [date(2025,10,15), date(2025,10,16)])
        if len(d_range)==1:
            start_d = d_range[0]
            end_d = d_range[0]
        else:
            start_d, end_d = d_range[0], d_range[-1]

    with col_checkbox:
        # Larger checkbox is done via the CSS above
        no_moon = st.checkbox("No Moon", value=False)

    # Map in an expander
    with st.expander("Pick on Map (optional)"):
        st.write("Click on the map to choose lat/lon, city will be looked up via LocationIQ reverse if city search is ON.")
        map_loc = [lat_in, lon_in]
        m = folium.Map(location=map_loc, zoom_start=4)
        folium.TileLayer("OpenStreetMap").add_to(m)
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, width=600, height=400)
        if map_data and map_data.get("last_clicked"):
            clat = map_data["last_clicked"]["lat"]
            clng = map_data["last_clicked"]["lng"]
            st.info(f"Clicked lat={clat:.4f}, lon={clng:.4f}")
            lat_in, lon_in = clat, clng
            # If city search on, try reverse geocode
            if USE_CITY_SEARCH:
                rev_city = reverse_geocode(clat, clng)
                if rev_city:
                    st.success(f"Reverse geocoded city: {rev_city}")
                else:
                    st.warning("City not found or blocked via reverse geocode. Check lat/lon or usage limits.")

    delta_days = (end_d - start_d).days + 1
    if delta_days>MAX_DAYS:
        st.error(f"Please pick {MAX_DAYS} days or fewer.")
        return

    if st.button("Calculate"):
        if start_d> end_d:
            st.error("Start date must be <= end date.")
            return

        st.write(f"DEBUG: Starting calc with {STEP_MINUTES}-min steps, up to {MAX_DAYS} days.")
        daily_data = compute_day_details(lat_in, lon_in, start_d, end_d, no_moon)
        if not daily_data:
            st.warning("No data?? Possibly 0-day range.")
            return

        total_astro = sum(d["astro_dark_hours"] for d in daily_data)
        total_moonless = sum(d["moonless_hours"] for d in daily_data)

        st.subheader("Results")
        cA, cB = st.columns(2)
        with cA:
            st.success(f"Total Astronomical Darkness: {total_astro:.2f} hrs")
        with cB:
            st.success(f"Moonless Darkness: {total_moonless:.2f} hrs")

        st.subheader("Day-by-Day Breakdown")
        df = pd.DataFrame(daily_data)
        df = df.rename(columns={
            "date":"Date",
            "astro_dark_hours":"Astro (hrs)",
            "moonless_hours":"Moonless (hrs)",
            "dark_start":"Dark Start",
            "dark_end":"Dark End",
            "moon_rise":"Moonrise",
            "moon_set":"Moonset",
            "moon_phase":"Phase"
        })
        st.table(df)

########################################
# REPLACE Nominatim calls with LocationIQ
########################################
def geocode_city(city_name):
    """
    Use LocationIQ /v1/search to convert city->(lat,lon).
    """
    if not USE_CITY_SEARCH or not city_name.strip():
        return None
    token = "pk.adea9a047c0d5d483f99ee4ae1b4b08d"
    url = f"https://us1.locationiq.com/v1/search?key={token}&q={city_name}&format=json"
    headers = {"accept": "application/json"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data)>0:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                return (lat, lon)
        else:
            debug_print(f"DEBUG: City lookup code {resp.status_code}, text={resp.text}")
    except Exception as e:
        debug_print(f"DEBUG: City lookup error: {e}")
    return None

def reverse_geocode(lat, lon):
    """
    Use LocationIQ /v1/reverse to convert (lat,lon)-> city name.
    """
    if not USE_CITY_SEARCH:
        return None
    token = "pk.adea9a047c0d5d483f99ee4ae1b4b08d"
    url = f"https://us1.locationiq.com/v1/reverse?key={token}&lat={lat}&lon={lon}&format=json"
    headers = {"accept": "application/json"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            address = data.get("address", {})
            city = address.get("city") or address.get("town") or address.get("village")
            return city if city else data.get("display_name")
        else:
            debug_print(f"DEBUG: Reverse geocode code {resp.status_code}, text={resp.text}")
    except Exception as e:
        debug_print(f"DEBUG: Reverse geocode error: {e}")
    return None

# we run main
if __name__ == "__main__":
    main()
