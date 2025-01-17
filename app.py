############################
# app.py
############################

########## CONFIGURATION-BLOCK ##########
MAX_DAYS = 30
STEP_MINUTES = 1  # Default value; will be overridden by user selection
USE_CITY_SEARCH = True
DEBUG = True
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
from time import sleep

# NEW: import from your local “component”
from my_date_picker_component import my_date_range_picker

########################################
# PAGE CONFIG + Custom CSS
########################################
st.set_page_config(
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="centered"
)

# Custom CSS for styling your entire app, including the component if needed
st.markdown("""
<style>
    .stCheckbox > div:first-child {
        transform: scale(1.2); 
        margin-top: 5px;
        margin-bottom: 5px;
    }
    textarea {
        font-family: "Courier New", Courier, monospace;
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

    /* Example: if you want to style the date picker input or dropdown.
       That depends on how your “my_date_range_picker” front-end is structured.
       If it's using Ant Design, you can target .ant-* classes, etc. */
</style>
""", unsafe_allow_html=True)

########################################
# UTILS
########################################
def debug_print(msg: str):
    if DEBUG:
        st.session_state["progress_console"] += msg + "\n"

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
# LocationIQ city + reverse
########################################
def geocode_city(city_name, token):
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
# Find Dark Crossings
########################################
def find_dark_crossings(sun_alts, times_list, local_tz):
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

    if found_start and end_str == "-":
        for i in range(N-1):
            if sun_alts[i] < -18 and sun_alts[i+1] >= -18:
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                end_str = dt_loc.strftime("%H:%M")
                break

    return (start_str, end_str)

########################################
# Astro Calculation
########################################
def compute_day_details(lat, lon, start_date, end_date, moon_affect, step_minutes, progress_bar, token):
    ts = load.timescale()
    eph = load('de421.bsp')
    debug_print("Loaded timescale & ephemeris")

    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
    try:
        local_tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        local_tz = pytz.utc
        debug_print(f"Unknown timezone for coords. Defaulting to UTC.")
    debug_print(f"Local Timezone: {tz_name}")

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

    total_days = (end_date - start_date).days + 1
    for _ in range(total_days):
        if day_count >= MAX_DAYS:
            debug_print(f"Reached maximum day limit of {MAX_DAYS}.")
            break

        debug_print(f"Processing day {day_count + 1}: {current}")

        # Update progress bar
        progress_val = (day_count + 1) / MAX_DAYS
        progress_bar.progress(min(progress_val, 1.0))

        # Local midnight -> next local midnight
        local_mid = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)
        try:
            start_aware = local_tz.localize(local_mid, is_dst=None)
            end_aware   = local_tz.localize(local_next, is_dst=None)
        except Exception as e:
            debug_print(f"Timezone localization error: {e}")
            start_aware = pytz.utc.localize(local_mid)
            end_aware   = pytz.utc.localize(local_next)
        start_utc = start_aware.astimezone(pytz.utc)
        end_utc   = end_aware.astimezone(pytz.utc)

        step_count = (24*60)//step_minutes
        times_list = []
        for i in range(step_count+1):
            dt_utc = start_utc + timedelta(minutes=i*step_minutes)
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
            s_mid = (sun_alts[i] + sun_alts[i+1]) / 2
            m_mid = (moon_alts[i] + moon_alts[i+1]) / 2
            if s_mid < -18.0:  # astro dark
                astro_minutes += step_minutes
                if moon_affect == "Ignore Moonlight":
                    moonless_minutes += step_minutes
                else:
                    if m_mid < 0.0:
                        moonless_minutes += step_minutes

        astro_hrs = astro_minutes // 60
        astro_mins = astro_minutes % 60
        moonless_hrs = moonless_minutes // 60
        moonless_mins = moonless_minutes % 60
        debug_print(f"astro_hrs={astro_hrs}, astro_mins={astro_mins}, moonless_hrs={moonless_hrs}, moonless_mins={moonless_mins}")

        # Crossing-based times
        dark_start_str, dark_end_str = find_dark_crossings(sun_alts, times_list, local_tz)

        # Moon rise/set
        m_rise_str = "-"
        m_set_str  = "-"
        prev_alt   = moon_alts[0]
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
        try:
            noon_aware = local_tz.localize(local_noon, is_dst=None)
        except Exception as e:
            debug_print(f"Timezone localization error for noon: {e}")
            noon_aware = pytz.utc.localize(local_noon)
        noon_utc = noon_aware.astimezone(pytz.utc)
        t_noon   = ts.from_datetime(noon_utc)
        obs_noon = observer.at(t_noon)
        sun_ecl  = obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360

        day_results.append({
            "date": current.strftime("%Y-%m-%d"),
            "astro_dark_hours": f"{int(astro_hrs)} Hours {int(astro_mins)} Minutes",
            "moonless_hours":   f"{int(moonless_hrs)} Hours {int(moonless_mins)} Minutes",
            "dark_start": dark_start_str if dark_start_str else "-",
            "dark_end":   dark_end_str if dark_end_str else "-",
            "moon_rise":  m_rise_str,
            "moon_set":   m_set_str,
            "moon_phase": moon_phase_icon(phase_angle)
        })

        current += timedelta(days=1)
        day_count += 1

        sleep(0.1)

    progress_bar.progress(1.0)
    debug_print("All calculations completed.")
    return day_results

########################################
# MAIN
########################################
def main():
    st.markdown("<h2>Astronomical Darkness Calculator</h2>", unsafe_allow_html=True)
    st.markdown("<h4>Find how many hours of true night you get, anywhere in the world. Perfect for planning astronomy holidays to maximize dark sky time.</h4>", unsafe_allow_html=True)

    # Session defaults
    if "city" not in st.session_state:
        st.session_state["city"] = "Marrakech"
    if "lat" not in st.session_state:
        st.session_state["lat"] = 31.6258
    if "lon" not in st.session_state:
        st.session_state["lon"] = -7.9892
    if "progress_console" not in st.session_state:
        st.session_state["progress_console"] = ""
    if "selected_dates" not in st.session_state:
        st.session_state["selected_dates"] = [date.today(), date.today() + timedelta(days=1)]
    if "last_click" not in st.session_state:
        st.session_state["last_click"] = None

    LOCATIONIQ_TOKEN = st.secrets["locationiq"]["token"]

    # Inputs
    st.markdown("#### Inputs")
    input_cols = st.columns(3)
    with input_cols[0]:
        if USE_CITY_SEARCH:
            cval = st.text_input(
                "City (optional)",
                value=st.session_state["city"],
                help="Enter a city name to look up lat/lon from LocationIQ."
            )
            if cval != st.session_state["city"]:
                coords = geocode_city(cval, LOCATIONIQ_TOKEN)
                if coords:
                    st.session_state["lat"], st.session_state["lon"] = coords
                    st.session_state["city"] = cval
                else:
                    st.warning("City not found or blocked.")
        else:
            st.write("City search is OFF")

    with input_cols[1]:
        # REPLACE st.date_input(...) with our custom date range picker
        st.markdown("**Select Date Range**")
        # Convert the 2 date objects into Python datetimes for the custom component
        old_start = st.session_state["selected_dates"][0]
        old_end   = st.session_state["selected_dates"][1]
        default_start_dt = datetime(old_start.year, old_start.month, old_start.day)
        default_end_dt   = datetime(old_end.year,   old_end.month,   old_end.day)

        date_range_result = my_date_range_picker(
            label=f"Pick up to {MAX_DAYS} days",
            start_date=default_start_dt,
            end_date=default_end_dt,
            key="my_custom_date_range"
        )
        if date_range_result:
            # date_range_result is (start_str, end_str)
            start_str, end_str = date_range_result
            # parse them from ISO or your chosen format
            start_dt = datetime.fromisoformat(start_str)
            end_dt   = datetime.fromisoformat(end_str)

            # store them back as date objects
            st.session_state["selected_dates"] = [start_dt.date(), end_dt.date()]

    with input_cols[2]:
        step_options = {
            "1 Minute": 1,
            "2 Minutes": 2,
            "5 Minutes": 5,
            "15 Minutes": 15,
            "30 Minutes": 30
        }
        step_minutes = st.selectbox(
            "Time Accuracy (Mins)",
            options=list(step_options.keys()),
            index=0,
            help="""This determines how precise the astro darkness calculations are."""
        )

    # Coordinates & Moon Influence
    st.markdown("#### Coordinates & Moon Influence")
    coord_cols = st.columns(3)
    with coord_cols[0]:
        lat_in = st.number_input("Latitude",
                                 value=st.session_state["lat"],
                                 format="%.6f",
                                 min_value=-90.0,
                                 max_value=90.0)
        if abs(lat_in - st.session_state["lat"]) > 1e-8:
            st.session_state["lat"] = lat_in

    with coord_cols[1]:
        lon_in = st.number_input("Longitude",
                                 value=st.session_state["lon"],
                                 format="%.6f",
                                 min_value=-180.0,
                                 max_value=180.0)
        if abs(lon_in - st.session_state["lon"]) > 1e-8:
            st.session_state["lon"] = lon_in

    with coord_cols[2]:
        moon_options = ["Include Moonlight", "Ignore Moonlight"]
        moon_affect = st.selectbox("Moon Influence on Darkness", options=moon_options, index=0)

    # Map
    st.markdown("#### Select Location on Map")
    st.markdown("<h5>You may need to click the map twice...</h5>", unsafe_allow_html=True)
    with st.expander("View Map"):
        folium_map = folium.Map(location=[st.session_state["lat"], st.session_state["lon"]], zoom_start=10)
        folium.Marker([st.session_state["lat"], st.session_state["lon"]], popup="Location").add_to(folium_map)
        map_click = st_folium(folium_map, width=700, height=500)

        if map_click and 'last_clicked' in map_click and map_click['last_clicked']:
            clicked_lat = map_click['last_clicked']['lat']
            clicked_lon = map_click['last_clicked']['lng']
            if not (-90.0 <= clicked_lat <= 90.0):
                st.warning(f"Clicked lat {clicked_lat} out of bounds.")
            elif not (-180.0 <= clicked_lon <= 180.0):
                st.warning(f"Clicked lon {clicked_lon} out of bounds.")
            else:
                current_click = (clicked_lat, clicked_lon)
                if st.session_state["last_click"] != current_click:
                    st.session_state["lat"], st.session_state["lon"] = current_click
                    city = reverse_geocode(clicked_lat, clicked_lon, LOCATIONIQ_TOKEN)
                    if city:
                        st.session_state["city"] = city
                        st.success(f"Location updated to {city} ({clicked_lat:.4f}, {clicked_lon:.4f})")
                    else:
                        st.warning("City not found for that location.")
                    st.session_state["last_click"] = current_click

    # Calculate
    st.markdown("####")
    calculate_button = st.button("Calculate")

    progress_placeholder = st.empty()
    progress_bar = progress_placeholder.progress(0)
    progress_text = st.empty()

    st.markdown("#### Progress Console")
    console_placeholder = st.empty()
    console_placeholder.text_area(
        "Progress Console",
        value=st.session_state["progress_console"],
        height=150,
        max_chars=None,
        key="progress_console_display",
        disabled=True,
        label_visibility="collapsed"
    )

    # Day range check
    selected_dates = st.session_state["selected_dates"]
    if len(selected_dates) >= 2:
        start_d, end_d = selected_dates[:2]
    else:
        start_d = end_d = selected_dates[0]
    delta_days = (end_d - start_d).days + 1
    if delta_days > MAX_DAYS:
        st.error(f"Please pick {MAX_DAYS} days or fewer.")
        st.stop()

    # Calculate Button
    if calculate_button:
        if start_d > end_d:
            st.error("Start date must be <= end date.")
            st.stop()

        if delta_days > MAX_DAYS:
            st.warning(f"Selected range exceeds {MAX_DAYS} days.")
            st.stop()

        st.session_state["progress_console"] = ""
        step_min = step_options[step_minutes]

        progress_bar.progress(0)
        progress_text.text("Starting calculations...")

        daily_data = compute_day_details(
            st.session_state["lat"],
            st.session_state["lon"],
            start_d,
            end_d,
            moon_affect,
            step_min,
            progress_bar,
            LOCATIONIQ_TOKEN
        )

        progress_bar.progress(1.0)
        progress_text.text("Calculations completed.")

        if not daily_data:
            st.warning("No data?? Possibly 0-day range or an error.")
            st.stop()

        # Summarize results
        total_astro = 0
        total_moonless = 0
        for d in daily_data:
            astro_parts = d["astro_dark_hours"].split()
            a_h = int(astro_parts[0])
            a_m = int(astro_parts[2])
            moonless_parts = d["moonless_hours"].split()
            m_h = int(moonless_parts[0])
            m_m = int(moonless_parts[2])
            total_astro += a_h * 60 + a_m
            total_moonless += m_h * 60 + m_m

        total_astro_hours = total_astro // 60
        total_astro_minutes = total_astro % 60
        total_moonless_hours = total_moonless // 60
        total_moonless_minutes = total_moonless % 60

        st.markdown("#### Results")
        if moon_affect == "Include Moonlight":
            result_cols = st.columns(2)
            with result_cols[0]:
                st.markdown(f"""
                <div class="result-box">
                    <div class="result-title">Total Astro Darkness</div>
                    <div class="result-value">{total_astro_hours} Hours {total_astro_minutes} Minutes</div>
                </div>
                """, unsafe_allow_html=True)
            with result_cols[1]:
                st.markdown(f"""
                <div class="result-box">
                    <div class="result-title">Moonless Astro Darkness</div>
                    <div class="result-value">{total_moonless_hours} Hours {total_moonless_minutes} Minutes</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            e1, main_col, e2 = st.columns([1,8,1])
            with main_col:
                st.markdown(f"""
                <div class="result-box">
                    <div class="result-title">Total Astro Darkness</div>
                    <div class="result-value">{total_astro_hours} Hours {total_astro_minutes} Minutes</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("#### Day-by-Day Breakdown")
        df = pd.DataFrame(daily_data)
        df.rename(columns={
            "date": "Date",
            "astro_dark_hours": "Astro (hrs)",
            "moonless_hours": "Moonless (hrs)",
            "dark_start": "Dark Start",
            "dark_end":   "Dark End",
            "moon_rise":  "Moonrise",
            "moon_set":   "Moonset",
            "moon_phase": "Phase"
        }, inplace=True)
        df.reset_index(drop=True, inplace=True)
        html_table = df.to_html(index=False)
        st.markdown(html_table, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
