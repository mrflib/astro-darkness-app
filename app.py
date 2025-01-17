############################
# app.py
############################

########## CONFIGURATION-BLOCK ##########
MAX_DAYS = 30           # Max days user can pick
USE_CITY_SEARCH = True  # Whether city name->lat/lon from LocationIQ is enabled
DEBUG = True            # If True, log debug messages in session console
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
    """Append debug info to console if DEBUG is True."""
    if DEBUG:
        st.session_state["progress_console"] += msg + "\n"

def moon_phase_icon(phase_deg):
    """Return a Moon phase emoji based on ecliptic longitude difference."""
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
    """(lat, lon)->city name from LocationIQ /v1/reverse. Returns None if not found."""
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
    For each local day in [start_date, end_date], define day D as local noon D->D+1,
    label that block "Night of D". We sum:
      - astro_minutes = sun < -18
      - moonless_minutes = sun < -18 & moon < 0
    Then decide which to present based on 'moon_affect'.

    We also find the crossing times for:
      - A.Start & A.End (sun altitude crossing -18)
      - M.Rise & M.Set (moon altitude crossing 0)
    Times are local.
    If not found, we store "-".
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

            sun_alt_deg = observer.at(sky_t).observe(eph['Sun']).apparent().altaz()[0].degrees
            moon_alt_deg = observer.at(sky_t).observe(eph['Moon']).apparent().altaz()[0].degrees
            sun_alts.append(sun_alt_deg)
            moon_alts.append(moon_alt_deg)

        # Summations
        astro_minutes = 0
        moonless_minutes = 0
        for i in range(len(times_list)-1):
            if sun_alts[i] < -18.0:
                astro_minutes += step_minutes
                if moon_alts[i] < 0.0:
                    moonless_minutes += step_minutes

        if moon_affect == "Ignore Moon":
            # bigger total
            final_astro = astro_minutes
        else:
            # "Subtract Moonlight" => smaller total
            final_astro = moonless_minutes

        a_h = final_astro // 60
        a_m = final_astro % 60

        # We also want crossing times: 
        # A.Start => crossing from sun_alt >= -18 to < -18
        # A.End   => crossing from sun_alt < -18 to >= -18
        # M.Rise  => crossing from moon_alt < 0 to >= 0
        # M.Set   => crossing from moon_alt >= 0 to < 0
        a_start_str = "-"
        a_end_str = "-"
        m_rise_str = "-"
        m_set_str  = "-"

        for i in range(len(sun_alts)-1):
            # Check astro start crossing
            if sun_alts[i] >= -18.0 and sun_alts[i+1] < -18.0 and a_start_str == "-":
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                a_start_str = dt_loc.strftime("%H:%M")

            # Check astro end crossing
            if sun_alts[i] < -18.0 and sun_alts[i+1] >= -18.0 and a_end_str == "-":
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                a_end_str = dt_loc.strftime("%H:%M")

        for i in range(len(moon_alts)-1):
            # Check moon rise crossing
            if moon_alts[i] < 0.0 and moon_alts[i+1] >= 0.0 and m_rise_str == "-":
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                m_rise_str = dt_loc.strftime("%H:%M")

            # Check moon set crossing
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
            "night_label": label_date.strftime("%Y-%m-%d"),
            "A.Start": a_start_str,
            "A.End":   a_end_str,
            "M.Rise":  m_rise_str,
            "M.Set":   m_set_str,
            "astro_dark_hours": f"{a_h} Hours {a_m} Minutes",
            "moonless_minutes": moonless_minutes,  # for optional reference
            "moon_phase": moon_phase_icon(phase_angle)
        })

    return nights_data

########################################
# MAIN
########################################
def main():
    st.markdown("<h2>Astronomical Darkness Calculator (Night-Labeled)</h2>", unsafe_allow_html=True)
    st.markdown("""
    <h4>
    This tool calculates how many hours of 'astro dark' (Sun below -18°) you get, 
    labeling each night by the local noon date it starts (noon→noon). 
    Perfect for planning extended nights without splitting at midnight!
    </h4>
    """, unsafe_allow_html=True)

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

    # Retrieve secrets
    LOCATIONIQ_TOKEN = st.secrets["locationiq"]["token"]

    # Use a form so the date widget won't re-run after every click
    with st.form("main_form"):
        st.write("**Inputs**")

        # Row 1: city, date range, time step
        row1 = st.columns(3)
        with row1[0]:
            city_val = st.text_input(
                "City (optional)",
                value=st.session_state["city"],
                help="Enter a city name. We'll try to find lat/lon if recognized."
            )

        with row1[1]:
            # 2-element date input => single pop-up
            dates_range = st.date_input(
                "Pick up to 30 days (Night-labeled)",
                value=st.session_state["dates_range"],
                help="Select two dates in one pop-up. We'll handle each local day noon->noon."
            )

        with row1[2]:
            step_opts = ["1", "2", "5", "10", "15", "30"]
            step_mins_str = st.selectbox(
                "Time Step (Mins)",
                options=step_opts,
                index=0,
                help="Lower = more accurate, but slower. E.g. '1' => 1440 steps/day"
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
                help="Decimal degrees. E.g. 51.5074 for London."
            )
        with row2[1]:
            lon_in = st.number_input(
                "Longitude",
                value=st.session_state["lon"],
                format="%.6f",
                min_value=-180.0,
                max_value=180.0,
                help="Decimal degrees. E.g. -0.1278 for London."
            )
        with row2[2]:
            # Two short labels
            moon_mode = st.selectbox(
                "Moon Influence",
                options=["Ignore Moon", "Subtract Moonlight"],
                help="Ignore Moon => bigger total. Subtract => only times moon<0 => smaller total."
            )

        st.write("#### Select Location on Map")
        fol_map = folium.Map(location=[lat_in, lon_in], zoom_start=6)
        folium.Marker([lat_in, lon_in], popup="Current Location").add_to(fol_map)
        map_out = st_folium(fol_map, width=700, height=450)

        # Submit
        submitted = st.form_submit_button("Submit")

    # A simple progress + console
    prog_placeholder = st.empty()
    progress_bar = prog_placeholder.progress(0)
    if "progress_console" not in st.session_state:
        st.session_state["progress_console"] = ""
    console_box = st.empty()

    if submitted:
        # City logic
        if city_val != st.session_state["city"]:
            coords = geocode_city(city_val, LOCATIONIQ_TOKEN)
            if coords:
                lat_in, lon_in = coords
                st.session_state["city"] = city_val
                st.success(f"Updated lat/lon for '{city_val}' => {coords}")
            else:
                st.warning("City not found or usage limit reached. Keeping old coords.")

        st.session_state["lat"] = lat_in
        st.session_state["lon"] = lon_in
        st.session_state["dates_range"] = dates_range

        # Map
        if map_out and "last_clicked" in map_out and map_out["last_clicked"]:
            clat = map_out["last_clicked"]["lat"]
            clon = map_out["last_clicked"]["lng"]
            if -90 <= clat <= 90 and -180 <= clon <= 180:
                if st.session_state["last_map_click"] != (clat, clon):
                    st.session_state["lat"] = clat
                    st.session_state["lon"] = clon
                    ccity = reverse_geocode(clat, clon, LOCATIONIQ_TOKEN)
                    if ccity:
                        st.session_state["city"] = ccity
                        st.success(f"Map click => {ccity} ({clat:.4f}, {clon:.4f})")
                    else:
                        st.success(f"Map click => lat/lon=({clat:.4f}, {clon:.4f})")
                    st.session_state["last_map_click"] = (clat, clon)

        (start_d, end_d) = st.session_state["dates_range"]
        if start_d > end_d:
            st.error("Start date must be <= end date.")
            st.stop()

        days_sel = (end_d - start_d).days + 1
        if days_sel > MAX_DAYS:
            st.error(f"You picked {days_sel} days. Max {MAX_DAYS} allowed.")
            st.stop()

        # Reset console
        st.session_state["progress_console"] = ""
        debug_print("Starting calculations for night-labeled approach...")

        # Do it
        nights = compute_night_details(
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

        if not nights:
            st.warning("No data?? Possibly 0-day range or an error.")
            st.stop()

        # Summaries
        total_astro_min = 0
        for row in nights:
            # e.g. "5 Hours 20 Minutes"
            parts = row["astro_dark_hours"].split()
            ah, am = int(parts[0]), int(parts[2])
            total_astro_min += ah*60 + am

        ta_h = total_astro_min // 60
        ta_m = total_astro_min % 60

        # Display results
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
                <div class="result-title">Total Astro (Subtracting Moonlight)</div>
                <div class="result-value">{ta_h}h {ta_m}m</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("#### Night-by-Night Breakdown")
        # We'll show these columns: Night of, A.Start, A.End, M.Rise, M.Set, astro_dark_hours, Phase
        df = pd.DataFrame(nights)
        # We'll rename "night_label" to "Night", "astro_dark_hours" => "Astro(Hrs)", "moon_phase" => "Phase"
        # "A.Start", "A.End", "M.Rise", "M.Set" we keep as is. 
        df.rename(columns={
            "night_label": "Night",
            "astro_dark_hours": "Astro(Hrs)",
            "moon_phase": "Phase"
        }, inplace=True)
        # "moonless_minutes" we won't show in final table (it's just internal).
        if "moonless_minutes" in df.columns:
            df.drop(columns=["moonless_minutes"], inplace=True)

        st.dataframe(df, use_container_width=True)

    st.markdown("#### Debug / Progress Console")
    console_box.text_area(
        "Progress Console",
        value=st.session_state["progress_console"],
        height=150,
        disabled=True,
        label_visibility="collapsed"
    )

if __name__ == "__main__":
    main()
