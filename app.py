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
    progress_bar
):
    """
    For each local day from local noon -> next local noon, label it "Night of D".
    We always compute:
      - astro_minutes (Sun < -18)
      - moonless_minutes (Sun < -18 and Moon < 0)
    Then "Dark Hours" in the table is always astro_minutes, 
    "Moonless Hours" is always the smaller subset.

    For the final summary, if user picks:
      - "Ignore Moon" => we sum astro_minutes 
      - "Subtract Moonlight" => we sum moonless_minutes
    We also find crossing times for Sun @ -18°, Moon @ 0°.
    """
    debug_print("Starting Night-labeled calculations...")

    ts = load.timescale()
    eph = load('de421.bsp')
    observer = eph['Earth'] + Topos(latitude_degrees=lat, longitude_degrees=lon)

    # find local tz
    from timezonefinder import TimezoneFinder
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
    day_count = (end_date - start_date).days + 1
    if day_count < 1:
        debug_print("No days in range => returning empty.")
        return []

    for i in range(day_count):
        fraction = (i+1) / day_count
        progress_bar.progress(min(fraction, 1.0))

        label_date = start_date + timedelta(days=i)
        debug_print(f"Processing 'Night of {label_date}' (noon->noon).")

        local_noon = datetime(label_date.year, label_date.month, label_date.day, 12, 0, 0)
        try:
            local_noon_aware = local_tz.localize(local_noon, is_dst=None)
        except:
            local_noon_aware = pytz.utc.localize(local_noon)

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
            sky_t  = ts.from_datetime(dt_utc)
            times_list.append(sky_t)
            sun_alt = observer.at(sky_t).observe(eph['Sun']).apparent().altaz()[0].degrees
            moon_alt = observer.at(sky_t).observe(eph['Moon']).apparent().altaz()[0].degrees
            sun_alts.append(sun_alt)
            moon_alts.append(moon_alt)

        # Summations
        astro_minutes = 0
        moonless_minutes = 0
        for idx in range(len(times_list)-1):
            if sun_alts[idx] < -18.0:
                astro_minutes += step_minutes
                if moon_alts[idx] < 0.0:
                    moonless_minutes += step_minutes

        # crossing times
        dark_start_str = "-"
        dark_end_str   = "-"
        moon_rise_str  = "-"
        moon_set_str   = "-"

        for idx in range(len(sun_alts)-1):
            # dark start
            if sun_alts[idx] >= -18.0 and sun_alts[idx+1] < -18.0 and dark_start_str == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                dark_start_str = dt_loc.strftime("%H:%M")
            # dark end
            if sun_alts[idx] < -18.0 and sun_alts[idx+1] >= -18.0 and dark_end_str == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                dark_end_str = dt_loc.strftime("%H:%M")

        for idx in range(len(moon_alts)-1):
            # moon rise
            if moon_alts[idx] < 0.0 and moon_alts[idx+1] >= 0.0 and moon_rise_str == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                moon_rise_str = dt_loc.strftime("%H:%M")
            # moon set
            if moon_alts[idx] >= 0.0 and moon_alts[idx+1] < 0.0 and moon_set_str == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                moon_set_str = dt_loc.strftime("%H:%M")

        # store
        # "Dark Hours" => astro_minutes, "Moonless Hours" => moonless_minutes
        # We'll convert them to "X Hours Y Minutes" strings
        d_h  = astro_minutes // 60
        d_m  = astro_minutes % 60
        ml_h = moonless_minutes // 60
        ml_m = moonless_minutes % 60

        nights_data.append({
            "Night": label_date.strftime("%Y-%m-%d"),
            "Dark Start": dark_start_str,
            "Dark End":   dark_end_str,
            "Moon Rise":  moon_rise_str,
            "Moon Set":   moon_set_str,
            "Dark Hours":   f"{d_h} Hours {d_m} Minutes",
            "Moonless Hours": f"{ml_h} Hours {ml_m} Minutes"
        })

    return nights_data

########################################
# MAIN
########################################
def main():
    st.title("Astronomical Darkness Calculator (Night-Labeled)")
    st.markdown("""
    **Either enter a city, or lat/long, or select a location on the map, 
    then pick your date range and press Calculate.**  
    """)

    # Session defaults
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

    # ========== TOP ROW (City / Lat / Lon) outside form =============
    st.markdown("### Coordinates")
    coord_cols = st.columns(3)

    with coord_cols[0]:
        city_val = st.text_input(
            "City (optional)",
            value=st.session_state["city"],
            help="Type a city name. If recognized, lat/lon will update automatically."
        )
        # If user typed a new city, geocode immediately
        if city_val != st.session_state["city"]:
            coords = geocode_city(city_val, LOCATIONIQ_TOKEN)
            if coords:
                st.session_state["lat"], st.session_state["lon"] = coords
                st.session_state["city"] = city_val
                st.success(f"Location updated for {city_val} => {coords}")
            else:
                st.warning("City not found or usage limit. Keeping old coords.")

    with coord_cols[1]:
        lat_in = st.number_input(
            "Latitude",
            value=st.session_state["lat"],
            format="%.6f",
            min_value=-90.0,
            max_value=90.0
        )
        if abs(lat_in - st.session_state["lat"]) > 1e-7:
            st.session_state["lat"] = lat_in

    with coord_cols[2]:
        lon_in = st.number_input(
            "Longitude",
            value=st.session_state["lon"],
            format="%.6f",
            min_value=-180.0,
            max_value=180.0
        )
        if abs(lon_in - st.session_state["lon"]) > 1e-7:
            st.session_state["lon"] = lon_in

    st.markdown("#### Map (Click to Update Lat/Lon)")

    fol_map = folium.Map(location=[st.session_state["lat"], st.session_state["lon"]], zoom_start=6)
    folium.Marker([st.session_state["lat"], st.session_state["lon"]], popup="Current Location").add_to(fol_map)
    map_out = st_folium(fol_map, width=700, height=450)

    if map_out and "last_clicked" in map_out and map_out["last_clicked"]:
        clat = map_out["last_clicked"]["lat"]
        clon = map_out["last_clicked"]["lng"]
        if -90 <= clat <= 90 and -180 <= clon <= 180:
            if st.session_state["last_map_click"] != (clat, clon):
                st.session_state["lat"] = clat
                st.session_state["lon"] = clon
                # Optionally do reverse geocode
                found_city = reverse_geocode(clat, clon, LOCATIONIQ_TOKEN)
                if found_city:
                    st.session_state["city"] = found_city
                    st.success(f"Map => {found_city} ({clat:.4f}, {clon:.4f})")
                else:
                    st.success(f"Map => lat/lon=({clat:.4f}, {clon:.4f})")
                st.session_state["last_map_click"] = (clat, clon)

    # ========== SECOND ROW (in a Form) for Date Range, Moon Influence, Time Steps, Calculate =============
    st.markdown("### Calculation Options")

    with st.form("calc_form"):
        row = st.columns(3)
        with row[0]:
            # date input
            date_range_val = st.date_input(
                "Pick up to 30 days",
                value=st.session_state["dates_range"],
                help="2-element date range. We treat each day as local noon→noon."
            )
        with row[1]:
            # moon influence
            moon_mode = st.selectbox(
                "Moon Influence",
                options=["Ignore Moon", "Subtract Moonlight"],
                help="Ignore => bigger total. Subtract => sun<-18 & moon<0 => smaller total."
            )
        with row[2]:
            # time step
            step_opts = ["1", "2", "5", "10", "15", "30"]
            step_str = st.selectbox(
                "Time Step (Mins)",
                step_opts,
                0,
                help="Lower => more accurate but slower. E.g. '1' => 1440 steps/day"
            )
            step_minutes = int(step_str)

        calc_submitted = st.form_submit_button("Calculate")

    # placeholders for progress + console
    progress_placeholder = st.empty()
    progress_bar = progress_placeholder.progress(0)
    console_placeholder = st.empty()

    if "progress_console" not in st.session_state:
        st.session_state["progress_console"] = ""

    if calc_submitted:
        # store date range
        # If user only selected one date, we do start=end
        if len(date_range_val) == 1:
            start_d = date_range_val[0]
            end_d   = date_range_val[0]
        else:
            start_d, end_d = date_range_val[0], date_range_val[-1]

        if start_d > end_d:
            st.error("Start date must be <= end date.")
            st.stop()

        daycount = (end_d - start_d).days + 1
        if daycount > MAX_DAYS:
            st.error(f"You picked {daycount} days. Max allowed is {MAX_DAYS}.")
            st.stop()

        # store final session
        st.session_state["dates_range"] = (start_d, end_d)

        st.session_state["progress_console"] = ""
        debug_print("Starting night-labeled astro calculations...")

        nights_list = compute_night_details(
            st.session_state["lat"],
            st.session_state["lon"],
            start_d,
            end_d,
            moon_mode,
            step_minutes,
            progress_bar
        )

        progress_bar.progress(1.0)
        if not nights_list:
            st.warning("No data?? Possibly 0-day range or error.")
            st.stop()

        # Summation for final total depends on user choice
        total_minutes = 0
        total_moonless = 0
        for rowdict in nights_list:
            # "Dark Hours" => e.g. "5 Hours 12 Minutes"
            dsplit = rowdict["Dark Hours"].split()
            d_h, d_m = int(dsplit[0]), int(dsplit[2])

            # "Moonless Hours" => e.g. "3 Hours 45 Minutes"
            msplit = rowdict["Moonless Hours"].split()
            mm_h, mm_m = int(msplit[0]), int(msplit[2])

            if moon_mode == "Ignore Moon":
                total_minutes += d_h*60 + d_m
            else:  # Subtract
                total_minutes += mm_h*60 + mm_m

            # We'll also track total moonless just for reference if we want
            total_moonless += mm_h*60 + mm_m

        # Display final total
        T_h = total_minutes // 60
        T_m = total_minutes % 60

        st.markdown("#### Results")
        if moon_mode == "Ignore Moon":
            st.markdown(f"""
            <div class="result-box">
              <div class="result-title">Total Dark Hours (Ignoring Moon)</div>
              <div class="result-value">{T_h}h {T_m}m</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="result-box">
              <div class="result-title">Total Dark Hours (Subtract Moonlight)</div>
              <div class="result-value">{T_h}h {T_m}m</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("#### Night-by-Night Breakdown")

        # Convert to DataFrame, remove index, show columns:
        # Night, Dark Start, Dark End, Moon Rise, Moon Set, Dark Hours, Moonless Hours
        df = pd.DataFrame(nights_list)
        # We don't want row indexes, so convert to HTML with index=False
        html_table = df.to_html(index=False)
        st.markdown(html_table, unsafe_allow_html=True)

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
