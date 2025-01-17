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
    """Append debug info to session-based console if DEBUG is True."""
    if DEBUG:
        st.session_state["progress_console"] += msg + "\n"

def moon_phase_icon(phase_deg):
    """Return an emoji for the moon phase based on ecliptic longitude difference."""
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
    """City -> (lat, lon) using LocationIQ /v1/search. Returns None if not found."""
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
    """(lat, lon)->city from LocationIQ /v1/reverse. Returns None if not found."""
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
    moon_affect,       # "Ignore Moon" or "Subtract Moonlight"
    step_minutes,
    progress_bar,
    token
):
    """
    For each local day from local noon -> next local noon, 
    label that block "Night of D" (where D is that local noon date).
    We sum times sun<-18 for 'astro_minutes', plus times sun<-18 & moon<0 => 'moonless_minutes'.
    Then depending on 'moon_affect':
      - "Ignore Moon" => final astro = astro_minutes (bigger).
      - "Subtract Moonlight" => final astro = moonless_minutes (smaller).

    We also find crossing times:
      - A.Start & A.End (Sun crossing -18°)
      - M.Rise & M.Set (Moon crossing 0°)
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
    except:
        local_tz = pytz.utc
        debug_print(f"Unknown tz for {lat},{lon}, using UTC.")
    debug_print(f"Local timezone: {tz_name}")

    nights_data = []
    total_days = (end_date - start_date).days + 1
    if total_days < 1:
        debug_print("No days in range => returning empty.")
        return []

    for day_i in range(total_days):
        fraction = (day_i+1) / total_days
        progress_bar.progress(min(fraction, 1.0))

        label_date = start_date + timedelta(days=day_i)
        debug_print(f"Processing 'Night of {label_date}' (noon->noon).")

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
        sun_alts = []
        moon_alts = []

        for s in range(steps+1):
            dt_utc = start_utc + timedelta(minutes=s*step_minutes)
            sky_t = ts.from_datetime(dt_utc)
            times_list.append(sky_t)

            # alt deg
            sun_alt_deg = observer.at(sky_t).observe(eph['Sun']).apparent().altaz()[0].degrees
            moon_alt_deg = observer.at(sky_t).observe(eph['Moon']).apparent().altaz()[0].degrees
            sun_alts.append(sun_alt_deg)
            moon_alts.append(moon_alt_deg)

        # Summations
        astro_minutes = 0
        moonless_minutes = 0
        for idx in range(len(times_list)-1):
            if sun_alts[idx] < -18.0:
                astro_minutes += step_minutes
                if moon_alts[idx] < 0.0:
                    moonless_minutes += step_minutes

        if moon_affect == "Ignore Moon":
            final_astro = astro_minutes
        else:
            # "Subtract Moonlight"
            final_astro = moonless_minutes

        a_h = final_astro // 60
        a_m = final_astro % 60

        # Crossings
        a_start_str = "-"
        a_end_str   = "-"
        m_rise_str  = "-"
        m_set_str   = "-"

        for i in range(len(sun_alts)-1):
            # A.Start crossing
            if sun_alts[i] >= -18.0 and sun_alts[i+1] < -18.0 and a_start_str == "-":
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                a_start_str = dt_loc.strftime("%H:%M")
            # A.End crossing
            if sun_alts[i] < -18.0 and sun_alts[i+1] >= -18.0 and a_end_str == "-":
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                a_end_str = dt_loc.strftime("%H:%M")

        for i in range(len(moon_alts)-1):
            # M.Rise
            if moon_alts[i] < 0.0 and moon_alts[i+1] >= 0.0 and m_rise_str == "-":
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                m_rise_str = dt_loc.strftime("%H:%M")
            # M.Set
            if moon_alts[i] >= 0.0 and moon_alts[i+1] < 0.0 and m_set_str == "-":
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                m_set_str = dt_loc.strftime("%H:%M")

        # Moon phase at local noon
        local_noon_utc = local_noon_aware.astimezone(pytz.utc)
        t_noon = ts.from_datetime(local_noon_utc)
        obs_noon = observer.at(t_noon)
        sun_ecl  = obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360

        nights_data.append({
            "Night": label_date.strftime("%Y-%m-%d"),
            "A.Start": a_start_str,
            "A.End":   a_end_str,
            "M.Rise":  m_rise_str,
            "M.Set":   m_set_str,
            "Astro(Hrs)": f"{a_h} Hours {a_m} Minutes",
            "Phase": moon_phase_icon(phase_angle)
        })

    return nights_data

########################################
# MAIN
########################################
def main():
    st.markdown("<h2>Astronomical Darkness Calculator (Night-Labeled)</h2>", unsafe_allow_html=True)
    st.markdown("""
    **Either enter a city, or lat/long, or select a location on the map, 
    then pick your date range and press Calculate.**
    """)

    # Prepare session defaults
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

    # ROW 1: city, lat, lon (all in the form)
    with st.form("main_form"):
        row1 = st.columns(3)
        with row1[0]:
            city_val = st.text_input(
                "City (optional)",
                value=st.session_state["city"],
                help="Type a city name. We'll attempt to look up lat/lon if recognized."
            )
        with row1[1]:
            lat_in = st.number_input(
                "Latitude",
                value=st.session_state["lat"],
                format="%.6f",
                min_value=-90.0,
                max_value=90.0,
                help="Decimal degrees (e.g. 51.5074 for London)."
            )
        with row1[2]:
            lon_in = st.number_input(
                "Longitude",
                value=st.session_state["lon"],
                format="%.6f",
                min_value=-180.0,
                max_value=180.0,
                help="Decimal degrees (e.g. -0.1278 for London)."
            )

        # ROW 2: date range, moon influence, time step
        row2 = st.columns(3)
        with row2[0]:
            drange = st.date_input(
                "Pick up to 30 days",
                value=st.session_state["dates_range"],
                help="2-element date range. We'll treat each day as noon→noon."
            )
        with row2[1]:
            moon_mode = st.selectbox(
                "Moon Influence",
                options=["Ignore Moon", "Subtract Moonlight"],
                help=("Ignore Moon => don't subtract times moon is up. Subtract => require moon<0 => smaller total.")
            )
        with row2[2]:
            step_opts = ["1", "2", "5", "10", "15", "30"]
            step_str = st.selectbox(
                "Time Step (Mins)",
                options=step_opts,
                index=0,
                help="Lower => more accurate but slower. E.g. '1' => 1440 steps/day"
            )
            step_minutes = int(step_str)

        # SUBMIT button
        calc_submitted = st.form_submit_button("Calculate")

    # The map is outside the form so user can select location in real-time
    st.markdown("#### Select Location on Map")
    fol_map = folium.Map(location=[st.session_state["lat"], st.session_state["lon"]], zoom_start=6)
    folium.Marker(
        [st.session_state["lat"], st.session_state["lon"]],
        popup="Current Location"
    ).add_to(fol_map)
    map_out = st_folium(fol_map, width=700, height=450)

    if map_out and "last_clicked" in map_out and map_out["last_clicked"]:
        clat = map_out["last_clicked"]["lat"]
        clon = map_out["last_clicked"]["lng"]
        # On each click, update lat/lon in real time
        if -90 <= clat <= 90 and -180 <= clon <= 180:
            if st.session_state["last_map_click"] != (clat, clon):
                st.session_state["lat"] = clat
                st.session_state["lon"] = clon
                # Optionally do reverse geocode
                city_found = reverse_geocode(clat, clon, LOCATIONIQ_TOKEN)
                if city_found:
                    st.session_state["city"] = city_found
                    st.success(f"Location updated => {city_found} ({clat:.4f}, {clon:.4f})")
                else:
                    st.success(f"lat/lon=({clat:.4f}, {clon:.4f}), no city found")
                st.session_state["last_map_click"] = (clat, clon)

    # Minimal placeholders
    progress_placeholder = st.empty()
    progress_bar = progress_placeholder.progress(0)
    console_placeholder = st.empty()
    if "progress_console" not in st.session_state:
        st.session_state["progress_console"] = ""

    if calc_submitted:
        # City -> lat/lon if typed
        if city_val != st.session_state["city"]:
            coords = geocode_city(city_val, LOCATIONIQ_TOKEN)
            if coords:
                lat_in, lon_in = coords
                st.session_state["city"] = city_val
                st.success(f"Updated lat/lon for {city_val} => {coords}")
            else:
                st.warning("City not found or usage limit reached. Keeping old coords.")

        # Store final lat/lon back
        st.session_state["lat"] = lat_in
        st.session_state["lon"] = lon_in
        st.session_state["dates_range"] = drange

        # Validate date range
        start_d, end_d = drange[0], drange[-1] if len(drange) > 1 else (drange[0], drange[0])
        if start_d > end_d:
            st.error("Start date must be <= end date.")
            st.stop()

        day_count = (end_d - start_d).days + 1
        if day_count > MAX_DAYS:
            st.error(f"You picked {day_count} days. Max is {MAX_DAYS}.")
            st.stop()

        # Clear console
        st.session_state["progress_console"] = ""
        debug_print("Starting night-labeled astro calculations...")

        # Perform calcs
        nights_list = compute_night_details(
            st.session_state["lat"],
            st.session_state["lon"],
            start_d,
            end_d,
            moon_mode,
            step_minutes,
            progress_bar,
            LOCATIONIQ_TOKEN
        )
        progress_bar.progress(1.0)

        if not nights_list:
            st.warning("No data?? Possibly 0-day range or an error.")
            st.stop()

        # Summaries
        total_astro_min = 0
        for row in nights_list:
            # "Astro(Hrs)" => "3 Hours 42 Minutes"
            spl = row["Astro(Hrs)"].split()
            h_, m_ = int(spl[0]), int(spl[2])
            total_astro_min += h_*60 + m_

        ta_h = total_astro_min // 60
        ta_m = total_astro_min % 60

        st.markdown("#### Results")
        if moon_mode == "Ignore Moon":
            st.markdown(f"""
            <div class="result-box">
                <div class="result-title">Total Astro (Ignoring Moon)</div>
                <div class="result-value">{ta_h}h {ta_m}m</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="result-box">
                <div class="result-title">Total Astro (Subtract Moonlight)</div>
                <div class="result-value">{ta_h}h {ta_m}m</div>
            </div>
            """, unsafe_allow_html=True)

        # Show table with columns: 
        # Night, A.Start, A.End, M.Rise, M.Set, Astro(Hrs), Phase
        df = pd.DataFrame(nights_list)
        st.markdown("#### Night-by-Night Breakdown")
        st.dataframe(df, use_container_width=True)

    # Show console
    st.markdown("#### Debug / Progress Console")
    console_placeholder.text_area(
        "Progress Console",
        value=st.session_state["progress_console"],
        height=150,
        disabled=True,
        label_visibility="collapsed"
    )

if __name__ == "__main__":
    main()
