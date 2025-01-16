############################
# app.py - LocationIQ map + layout + "Prev. day" fix
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

from skyfield.api import load, Topos

# For the map
import folium
from streamlit_folium import st_folium

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
# LocationIQ Geocoding + Reverse
########################################
def geocode_city(city_name):
    """
    City->(lat,lon) using LocationIQ /v1/search.
    """
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
                debug_print(f"DEBUG: geocode no list data: {data}")
        else:
            debug_print(f"DEBUG: geocode code {resp.status_code}, text={resp.text}")
    except Exception as e:
        debug_print(f"DEBUG: geocode error: {e}")
    return None

def reverse_geocode(lat, lon):
    """
    (lat,lon)-> city using LocationIQ /v1/reverse.
    """
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
            debug_print(f"DEBUG: reverse code {resp.status_code}, text={resp.text}")
    except Exception as e:
        debug_print(f"DEBUG: reverse error: {e}")
    return None

########################################
# Astronomy Calculation
########################################
@st.cache_data
def compute_day_details(lat, lon, start_date, end_date, no_moon):
    debug_print("DEBUG: Entering compute_day_details")

    from skyfield.api import load, Topos
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

    max_days = MAX_DAYS
    day_results = []
    day_count = 0
    current = start_date

    while current <= end_date and day_count < max_days:
        debug_print(f"DEBUG: day {day_count}, date={current}")
        local_mid = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)

        start_aware = local_tz.localize(local_mid)
        end_aware = local_tz.localize(local_next)
        start_utc = start_aware.astimezone(pytz.utc)
        end_utc = end_aware.astimezone(pytz.utc)

        step_count = (24*60)//STEP_MINUTES
        debug_print(f"DEBUG: step_count={step_count} for date={current}")
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

        # Dark start/end fix: if at midnight sun < -18 => "Prev. day"
        start_dark_str = "-"
        end_dark_str = "-"
        found_dark = False

        for i in range(len(sun_alts)-1):
            if sun_alts[i] >= -18.0 and sun_alts[i+1] < -18.0:
                # crossing from above-18 to below-18 => dark start
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                start_dark_str = dt_loc.strftime("%H:%M")
            if sun_alts[i] < -18.0 and sun_alts[i+1] >= -18.0 and not found_dark:
                # crossing out of darkness => dark end
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                end_dark_str = dt_loc.strftime("%H:%M")
                found_dark = True

        # If the sun is below -18 at midnight => we set dark start to "Prev. day"
        if sun_alts[0] < -18.0:
            start_dark_str = "Prev. day"

        # If we remain in darkness at end of day => "Next day"
        if sun_alts[-1] < -18.0 and end_dark_str == "-":
            end_dark_str = "Next day"

        # Moon rise/set
        m_rise_str = "-"
        m_set_str = "-"
        prev_alt = moon_alts[0]
        for i in range(1, len(moon_alts)):
            if prev_alt < 0 and moon_alts[i]>=0 and m_rise_str=="-":
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
        t_noon = load.timescale().from_datetime(noon_utc)
        obs_noon = observer.at(t_noon)
        sun_ecl = obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360

        day_results.append({
            "date": current.strftime("%Y-%m-%d"),
            "astro_dark_hours": round(astro_hrs,2),
            "moonless_hours": round(moonless_hrs,2),
            "dark_start": start_dark_str,
            "dark_end": end_dark_str if end_dark_str != "-" else "00:00",
            "moon_rise": m_rise_str,
            "moon_set": m_set_str,
            "moon_phase": moon_phase_icon(phase_angle)
        })

        current += timedelta(days=1)
        day_count+=1

    debug_print("DEBUG: Exiting compute_day_details, returning results.")
    return day_results

def main():
    st.title("Astronomical Darkness Calculator")

    # Row: City + Date
    c1, c2 = st.columns([2,1])
    with c1:
        st.subheader("City Input")
        lat_default = 31.6258
        lon_default = -7.9892
        city_val = "Marrakech"
        if USE_CITY_SEARCH:
            city_val = st.text_input("City (optional)", city_val)
            if city_val:
                coords = geocode_city(city_val)
                if coords:
                    lat_default, lon_default = coords
                else:
                    st.warning("City not found/blocked. Use lat/lon or map.")
        else:
            st.write("City search OFF")

    with c2:
        st.subheader("Date Range")
        d_rng = st.date_input(f"Pick up to {MAX_DAYS} days",
                              [date(2025,10,15), date(2025,10,16)])
        if len(d_rng)==1:
            start_d = d_rng[0]
            end_d = d_rng[0]
        else:
            start_d, end_d = d_rng[0], d_rng[-1]

    # Row: Lat + Lon
    st.subheader("Lat/Lon")
    colL, colR = st.columns(2)
    with colL:
        lat_in = st.number_input("Latitude", value=lat_default, format="%.6f")
    with colR:
        lon_in = st.number_input("Longitude", value=lon_default, format="%.6f")

    # No Moon
    no_moon = st.checkbox(
        "No Moon", 
        value=False,
        help=(
            "Exclude times when Moon is above the horizon. This only counts hours "
            "where the Sun is < -18° AND Moon altitude < 0°, giving truly dark skies."
        )
    )

    # Map in expander
    with st.expander("Pick on Map (optional)"):
        st.write("Click map to select lat/lon. Reverse geocode attempts to update city as well.")
        m = folium.Map(location=[lat_in, lon_in], zoom_start=5)
        folium.TileLayer("OpenStreetMap").add_to(m)
        m.add_child(folium.LatLngPopup())
        map_res = st_folium(m, width=800, height=500)

        if map_res and map_res.get("last_clicked"):
            clat = map_res["last_clicked"]["lat"]
            clng = map_res["last_clicked"]["lng"]
            st.info(f"Clicked lat={clat:.4f}, lon={clng:.4f}")
            lat_in, lon_in = clat, clng
            # If city search on, do reverse geocode
            if USE_CITY_SEARCH:
                found_c = reverse_geocode(clat, clng)
                if found_c:
                    st.success(f"Reverse geocoded city: {found_c}")
                    city_val = found_c
                else:
                    st.warning("City not found from reverse geocode.")
            # Update input fields
            st.experimental_set_query_params(
                lat=str(lat_in),
                lon=str(lon_in),
                city=str(city_val)
            )

    # Check days
    day_span = (end_d - start_d).days + 1
    if day_span>MAX_DAYS:
        st.error(f"Please pick {MAX_DAYS} days or fewer.")
        return

    if st.button("Calculate"):
        if start_d > end_d:
            st.error("Start date must be <= end date.")
            return

        st.write(f"DEBUG: lat={lat_in:.4f}, lon={lon_in:.4f}, city={city_val}, start={start_d}, end={end_d}")
        data = compute_day_details(lat_in, lon_in, start_d, end_d, no_moon)
        if not data:
            st.warning("No data? Possibly 0-day range or something else.")
            return

        # Summaries
        total_astro = sum(d["astro_dark_hours"] for d in data)
        total_moonless = sum(d["moonless_hours"] for d in data)

        st.subheader("Results")
        boxA, boxB = st.columns(2)
        with boxA:
            st.success(f"Total Astronomical Darkness: {total_astro:.2f} hrs")
        with boxB:
            st.success(f"Moonless Darkness: {total_moonless:.2f} hrs")

        st.subheader("Day-by-Day Breakdown")
        df = pd.DataFrame(data)
        df = df.rename(columns={
            "date": "Date",
            "astro_dark_hours": "Astro (hrs)",
            "moonless_hours": "Moonless (hrs)",
            "dark_start": "Dark Start",
            "dark_end": "Dark End",
            "moon_rise": "Moonrise",
            "moon_set": "Moonset",
            "moon_phase": "Phase"
        })
        # remove the row index
        df.index = df.index.map(lambda x: "")
        st.dataframe(df)


if __name__=="__main__":
    main()
