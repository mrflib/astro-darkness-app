############################
# app.py
############################

########## CONFIGURATION-BLOCK ##########
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
    This allows the 'dark end' to happen after midnight if crossing occurs in the next day.
    """
    N = len(sun_alts)
    start_str = "-"
    end_str = "-"
    found_start = False

    for i in range(N-1):
        # crossing from alt >= -18 -> < -18 => dark start
        if sun_alts[i] >= -18 and sun_alts[i+1] < -18 and not found_start:
            dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
            start_str = dt_loc.strftime("%H:%M")
            found_start = True
        # crossing from alt < -18 -> >= -18 => dark end
        elif sun_alts[i] < -18 and sun_alts[i+1] >= -18 and found_start and end_str=="-":
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

    max_days = MAX_DAYS
    day_results = []
    day_count = 0
    current = start_date

    while current <= end_date and day_count < max_days:
        debug_print(f"DEBUG: day {day_count}, date={current}")

        # local midnight -> next local midnight
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

        # crossing-based times
        dark_start_str, dark_end_str = find_dark_crossings(sun_alts, times_list, local_tz)

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
        t_noon = load.timescale().from_datetime(noon_utc)
        obs_noon = observer.at(t_noon)
        sun_ecl = obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360

        day_results.append({
            "date": current.strftime("%Y-%m-%d"),
            "astro_dark_hours": round(astro_hrs,2),
            "moonless_hours": round(moonless_hrs,2),
            "dark_start": dark_start_str if dark_start_str else "-",
            "dark_end": dark_end_str if dark_end_str else "-",
            "moon_rise": m_rise_str,
            "moon_set": m_set_str,
            "moon_phase": moon_phase_icon(phase_angle)
        })

        current += timedelta(days=1)
        day_count+=1

    return day_results

########################################
# MAIN
########################################
def main():
    st.title("Astronomical Darkness Calculator")
    st.subheader("Find how many hours of true night you get, anywhere in the world. Perfect for planning astronomy holidays to maximize dark sky time.")

    # Initialize session defaults if missing
    if "city" not in st.session_state:
        st.session_state["city"] = "Marrakech"
    if "lat" not in st.session_state:
        st.session_state["lat"] = 31.6258
    if "lon" not in st.session_state:
        st.session_state["lon"] = -7.9892
    if "start_date" not in st.session_state:
        st.session_state["start_date"] = date(2025,10,15)
    if "end_date" not in st.session_state:
        st.session_state["end_date"] = date(2025,10,16)

    # Row for city + date
    row1_col1, row1_col2 = st.columns([2,1])
    with row1_col1:
        st.subheader("City Input")
        if USE_CITY_SEARCH:
            cval = st.text_input(
                "City (optional)",
                value=st.session_state["city"],
                help="Enter a city name to look up lat/lon from LocationIQ (e.g. 'London')."
            )
            if cval != st.session_state["city"]:
                # user typed a new city
                coords = geocode_city(cval)
                if coords:
                    st.session_state["lat"], st.session_state["lon"] = coords
                    st.session_state["city"] = cval
                else:
                    st.warning("City not found or blocked. Check spelling or usage limits.")
            # else no changes
        else:
            st.write("City search is OFF")

    with row1_col2:
        st.subheader("Date Range")
        dvals = st.date_input(
            f"Pick up to {MAX_DAYS} days",
            [st.session_state["start_date"], st.session_state["end_date"]],
            help="Select 1 or 2 dates. e.g. 2025-10-14 to 2025-10-19"
        )
        if len(dvals)==1:
            st.session_state["start_date"] = dvals[0]
            st.session_state["end_date"] = dvals[0]
        else:
            st.session_state["start_date"], st.session_state["end_date"] = dvals[0], dvals[-1]

    # Row for lat/lon
    st.subheader("Lat/Lon")
    row2_col1, row2_col2 = st.columns(2)
    with row2_col1:
        lat_in = st.number_input(
            "Latitude",
            value=st.session_state["lat"],
            format="%.6f",
            help="Latitude in decimal degrees (e.g. 51.5074 for London)."
        )
        if abs(lat_in - st.session_state["lat"])>1e-8:
            st.session_state["lat"] = lat_in

    with row2_col2:
        lon_in = st.number_input(
            "Longitude",
            value=st.session_state["lon"],
            format="%.6f",
            help="Longitude in decimal degrees (e.g. -0.1278 for London)."
        )
        if abs(lon_in - st.session_state["lon"])>1e-8:
            st.session_state["lon"] = lon_in

    # No Moon
    no_moon = st.checkbox(
        "No Moon",
        value=False,
        help="Exclude times when the Moon is above the horizon, ensuring truly dark skies with no moonlight."
    )

    # Map in expander
    with st.expander("Pick on Map (optional)", expanded=False):
        st.write("Click on the map to select lat/lon. If city search is ON, we will also reverse geocode to update the City field.")
        default_loc = [st.session_state["lat"], st.session_state["lon"]]
        f_map = folium.Map(location=default_loc, zoom_start=5, width="100%")
        folium.TileLayer("OpenStreetMap").add_to(f_map)
        f_map.add_child(folium.LatLngPopup())

        map_result = st_folium(f_map, width=800, height=500)
        if map_result and map_result.get("last_clicked"):
            clat = map_result["last_clicked"]["lat"]
            clng = map_result["last_clicked"]["lng"]
            st.info(f"Clicked lat={clat:.4f}, lon={clng:.4f}")
            st.session_state["lat"] = clat
            st.session_state["lon"] = clng
            if USE_CITY_SEARCH:
                cfound = reverse_geocode(clat, clng)
                if cfound:
                    st.success(f"Reverse geocoded city: {cfound}")
                    st.session_state["city"] = cfound
                else:
                    st.warning("City not found from reverse geocode.")

    # Check day range
    delta_days = (st.session_state["end_date"] - st.session_state["start_date"]).days + 1
    if delta_days>MAX_DAYS:
        st.error(f"Please pick {MAX_DAYS} days or fewer.")
        return

    # Calculate
    if st.button("Calculate"):
        if st.session_state["start_date"]> st.session_state["end_date"]:
            st.error("Start date must be <= end date.")
            return

        debug_print(f"DEBUG: lat={st.session_state['lat']:.4f}, lon={st.session_state['lon']:.4f}, city={st.session_state['city']}, range={st.session_state['start_date']}..{st.session_state['end_date']}, no_moon={no_moon}")
        daily_data = compute_day_details(
            st.session_state["lat"],
            st.session_state["lon"],
            st.session_state["start_date"],
            st.session_state["end_date"],
            no_moon
        )
        if not daily_data:
            st.warning("No data?? Possibly 0-day range or an error.")
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
            "date": "Date",
            "astro_dark_hours": "Astro (hrs)",
            "moonless_hours": "Moonless (hrs)",
            "dark_start": "Dark Start",
            "dark_end": "Dark End",
            "moon_rise": "Moonrise",
            "moon_set": "Moonset",
            "moon_phase": "Phase"
        })
        # remove row index
        df.index = df.index.map(lambda x: "")
        st.dataframe(df)


if __name__=="__main__":
    main()
