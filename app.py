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
import time
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

# We color the progress bar's container (#aaa) differently from its fill (#218838)
st.markdown(r"""
<style>
/* Make the "Calculate" button #218838 on normal/hover/active */
.stButton > button {
    background-color: #218838 !important;
    border-color: #1e7e34 !important;
    color: white !important;
}
.stButton > button:hover:not(:disabled),
.stButton > button:focus:not(:disabled),
.stButton > button:active:not(:disabled) {
    background-color: #218838 !important;
    color: white !important;
    border-color: #1e7e34 !important;
}

/* 
   Distinguish between the track (outer container) and the fill portion:
   - Outer track => #aaa
   - Inner fill => #218838
*/
div[data-testid="stProgressBar"] > div[role="progressbar"] {
    background-color: #aaa !important;       /* Outer container/track */
}
div[data-testid="stProgressBar"] > div[role="progressbar"] > div {
    background-color: #218838 !important;    /* Fill portion */
}

/* Remove default styling on st.form */
div[data-testid="stForm"] {
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
}

/* Slightly smaller radius for the .result-box */
.result-box {
    background-color: #218838;
    color: white;
    border-radius: 8px;
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
    """Append debug info to session-based console if DEBUG=True."""
    if DEBUG:
        st.session_state["progress_console"] += msg + "\n"

def moon_phase_icon(phase_deg):
    """Return a Moon phase emoji."""
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
    """City -> (lat, lon) using LocationIQ /v1/search."""
    # (same code as before) ...
    pass

def reverse_geocode(lat, lon, token):
    """(lat, lon)->city from LocationIQ /v1/reverse."""
    # (same code as before) ...
    pass

########################################
# NIGHT-LABELED NOON->NOON CALC
########################################
def compute_night_details(
    lat, lon,
    start_date, end_date,
    twilight_threshold,  # e.g. 6 for civil, 12 for nautical, 18 for astro
    step_minutes,
    pbar
):
    """
    We'll update 'pbar' each day to show partial progress, 
    plus time.sleep(0.1) to ensure the increments appear visually.
    """
    from skyfield.api import load, Topos
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

    for i in range(total_days):
        # partial fraction
        fraction = (i + 1) / total_days
        pbar.progress(fraction)
        time.sleep(0.1)  # force a short pause to let UI render

        day_label = start_date + timedelta(days=i)
        debug_print(f"Processing 'Night of {day_label}' (noon->noon).")

        local_noon_dt = datetime(day_label.year, day_label.month, day_label.day, 12, 0, 0)
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
            tsky = ts.from_datetime(dt_utc)
            sun_alt = observer.at(tsky).observe(eph['Sun']).apparent().altaz()[0].degrees
            moon_alt = observer.at(tsky).observe(eph['Moon']).apparent().altaz()[0].degrees
            times_list.append(tsky)
            sun_alts.append(sun_alt)
            moon_alts.append(moon_alt)

        astro_minutes = 0
        moonless_minutes = 0
        for idx in range(len(times_list)-1):
            if sun_alts[idx] < -twilight_threshold:
                astro_minutes += step_minutes
                if moon_alts[idx] < 0.0:
                    moonless_minutes += step_minutes

        # crossing times
        dark_start = "-"
        dark_end   = "-"
        moon_rise  = "-"
        moon_set   = "-"

        for idx in range(len(sun_alts)-1):
            if sun_alts[idx] >= -twilight_threshold and sun_alts[idx+1] < -twilight_threshold and dark_start == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                dark_start = dt_loc.strftime("%H:%M")
            if sun_alts[idx] < -twilight_threshold and sun_alts[idx+1] >= -twilight_threshold and dark_end == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                dark_end = dt_loc.strftime("%H:%M")

        for idx in range(len(moon_alts)-1):
            if moon_alts[idx] < 0.0 and moon_alts[idx+1] >= 0.0 and moon_rise == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                moon_rise = dt_loc.strftime("%H:%M")
            if moon_alts[idx] >= 0.0 and moon_alts[idx+1] < 0.0 and moon_set == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                moon_set = dt_loc.strftime("%H:%M")

        a_hrs = astro_minutes // 60
        a_min = astro_minutes % 60
        astro_str = f"{a_hrs}hrs {a_min}min"

        m_hrs = moonless_minutes // 60
        m_min = moonless_minutes % 60
        moonl_str = f"{m_hrs}hrs {m_min}min"

        # moon phase
        t_noon = ts.from_datetime(local_noon_aware.astimezone(pytz.utc))
        obs_noon = observer.at(t_noon)
        sun_ecl  = obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360
        phase_emoji = moon_phase_icon(phase_angle)

        nights_data.append({
            "Night": day_label.strftime("%Y-%m-%d"),
            "Dark Start": dark_start,
            "Dark End": dark_end,
            "Moon Rise": moon_rise,
            "Moon Set": moon_set,
            "Dark Hours": astro_str,
            "Moonless Hours": moonl_str,
            "Phase": phase_emoji
        })

    return nights_data

########################################
# MAIN
########################################
def main():
    st.title("Astronomical Darkness Calculator (Night-Labeled)")
    st.write("Either enter a city, lat/long, or click the map, then pick date range & press Calculate.")

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

    # Coordinates + city
    st.markdown("#### Coordinates & City Input")
    rowc = st.columns(3)
    with rowc[0]:
        cval = st.text_input("City (optional)", value=st.session_state["city"])
        if cval != st.session_state["city"]:
            coords = geocode_city(cval, LOCATIONIQ_TOKEN)
            if coords:
                st.session_state["lat"], st.session_state["lon"] = coords
                st.session_state["city"] = cval
                st.success(f"Updated location => {coords}")
            else:
                st.warning("City not found or usage limit. Keeping old coords.")

    with rowc[1]:
        lat_in = st.number_input("Latitude", value=st.session_state["lat"], format="%.6f",
                                 min_value=-90.0, max_value=90.0)
        if abs(lat_in - st.session_state["lat"]) > 1e-7:
            st.session_state["lat"] = lat_in

    with rowc[2]:
        lon_in = st.number_input("Longitude", value=st.session_state["lon"], format="%.6f",
                                 min_value=-180.0, max_value=180.0)
        if abs(lon_in - st.session_state["lon"]) > 1e-7:
            st.session_state["lon"] = lon_in

    # Map
    st.markdown("#### Location on Map")
    st.write("You may need to click the map a few times to make it work! Free API fun! :)")
    fol_map = folium.Map(location=[st.session_state["lat"], st.session_state["lon"]], zoom_start=6)
    folium.Marker([st.session_state["lat"], st.session_state["lon"]], popup="Current").add_to(fol_map)
    map_out = st_folium(fol_map, width=700, height=450)
    if map_out and "last_clicked" in map_out and map_out["last_clicked"]:
        clat = map_out["last_clicked"]["lat"]
        clon = map_out["last_clicked"]["lng"]
        if -90 <= clat <= 90 and -180 <= clon <= 180:
            if st.session_state["last_map_click"] != (clat, clon):
                st.session_state["lat"] = clat
                st.session_state["lon"] = clon
                found_c = reverse_geocode(clat, clon, LOCATIONIQ_TOKEN)
                if found_c:
                    st.session_state["city"] = found_c
                    st.success(f"Map => {found_c} ({clat:.4f}, {clon:.4f})")
                else:
                    st.success(f"Map => lat/lon=({clat:.4f}, {clon:.4f})")
                st.session_state["last_map_click"] = (clat, clon)

    # The form
    st.markdown("### Calculate Darkness")
    with st.form("calc_form"):
        rowx = st.columns(3)
        with rowx[0]:
            dval = st.date_input("Pick up to 30 days", value=st.session_state["dates_range"])
        with rowx[1]:
            thr_dict = {"Civil (−6)": 6, "Nautical (−12)": 12, "Astronomical (−18)": 18}
            thr_label = st.selectbox("Twilight Threshold", list(thr_dict.keys()), index=2)
            threshold_val = thr_dict[thr_label]
        with rowx[2]:
            steps = ["1", "2", "5", "10", "15", "30"]
            step_str = st.selectbox("Time Step (Mins)", steps, 0)
            step_minutes = int(step_str)

        calc_btn = st.form_submit_button("Calculate")

    if calc_btn:
        if len(dval) == 1:
            sd = dval[0]
            ed = dval[0]
        else:
            sd, ed = dval[0], dval[-1]

        days_sel = (ed - sd).days + 1
        if days_sel > MAX_DAYS:
            st.error(f"You picked {days_sel} days, max is {MAX_DAYS}.")
            st.stop()
        if sd > ed:
            st.error("Start date must be <= end date.")
            st.stop()

        st.session_state["dates_range"] = (sd, ed)
        st.session_state["progress_console"] = ""
        debug_print(f"Starting night-labeled calculations for {days_sel} days...")

        # Show progress bar in a placeholder
        pbar_placeholder = st.empty()
        pbar = pbar_placeholder.progress(0)

        # call function
        nights_data = compute_night_details(
            st.session_state["lat"],
            st.session_state["lon"],
            sd, ed,
            threshold_val,
            step_minutes,
            pbar
        )

        if not nights_data:
            st.warning("No data?? Possibly 0-day range or error.")
            st.stop()

        # Summaries
        total_astro_min = 0
        total_moonless_min = 0
        for rowd in nights_data:
            # parse "Dark Hours" => "6hrs 32min"
            parts = rowd["Dark Hours"].split("hrs")
            d_hrs = int(parts[0].strip())
            d_min = int(parts[1].replace("min","").strip())

            # parse "Moonless Hours" => "4hrs 15min"
            parts2 = rowd["Moonless Hours"].split("hrs")
            m_hrs = int(parts2[0].strip())
            m_min = int(parts2[1].replace("min","").strip())

            total_astro_min += d_hrs*60 + d_min
            total_moonless_min += m_hrs*60 + m_min

        st.markdown("#### Results")
        boxes = st.columns(2)
        with boxes[0]:
            A_h = total_astro_min // 60
            A_m = total_astro_min % 60
            st.markdown(f"""
            <div class="result-box">
              <div class="result-title">Total Astro Darkness</div>
              <div class="result-value">{A_h}hrs {A_m}min</div>
            </div>
            """, unsafe_allow_html=True)
        with boxes[1]:
            M_h = total_moonless_min // 60
            M_m = total_moonless_min % 60
            st.markdown(f"""
            <div class="result-box">
              <div class="result-title">Total Moonless Dark</div>
              <div class="result-value">{M_h}hrs {M_m}min</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("#### Night-by-Night Breakdown")
        df = pd.DataFrame(nights_data)
        styled = df.style.set_properties(**{"text-align": "center"})
        styled.set_table_styles([
            {"selector": "th", "props": [("text-align","center")]},
            {"selector": "td", "props": [("text-align","center")]},
            {"selector": "table", "props": [("margin","0 auto")]}
        ])
        st.markdown(styled.to_html(index=True), unsafe_allow_html=True)

        st.markdown("#### Progress Console")
        st.text_area("Progress Console",
            value=st.session_state["progress_console"],
            height=150,
            disabled=True,
            label_visibility="collapsed"
        )

if __name__ == "__main__":
    main()
