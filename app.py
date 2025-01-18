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
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="centered"
)

# Distinguish track (#aaa) vs. fill (#218838) for progress bar
st.markdown(r"""
<style>
/* Button normal/hover/active => #218838 */
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

/* Progress bar outer track => #aaa, fill => #218838 */
div[data-testid="stProgressBar"] > div[role="progressbar"] {
    background-color: #aaa !important;       /* track */
}
div[data-testid="stProgressBar"] > div[role="progressbar"] > div {
    background-color: #218838 !important;    /* fill */
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
# NIGHT-LABELED NOON->NOON CALC
########################################
def compute_night_details(
    lat, lon,
    start_date, end_date,
    twilight_threshold,
    step_minutes,
    pbar
):
    """
    For each local day in [start_date, end_date], label it "Night of D" (noon->noon).
    We track times sun < -twilight_threshold, plus moon < 0 => "moonless."
    We update 'pbar' each day with a short time.sleep to allow partial increments visually.
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
        fraction = (i + 1) / total_days
        pbar.progress(fraction)
        time.sleep(0.1)  # ensure partial increments are visible

        day_label = start_date + timedelta(days=i)
        debug_print(f"Processing 'Night of {day_label}' (noon->noon).")

        # Local noon for day_label -> next day
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
            # crossing from >= -th to < -th => dark start
            if sun_alts[idx] >= -twilight_threshold and sun_alts[idx+1] < -twilight_threshold and dark_start == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                dark_start = dt_loc.strftime("%H:%M")
            # crossing from < -th to >= -th => dark end
            if sun_alts[idx] < -twilight_threshold and sun_alts[idx+1] >= -twilight_threshold and dark_end == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                dark_end = dt_loc.strftime("%H:%M")

        for idx in range(len(moon_alts)-1):
            # crossing from <0 to >=0 => moon rise
            if moon_alts[idx] < 0.0 and moon_alts[idx+1] >= 0.0 and moon_rise == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                moon_rise = dt_loc.strftime("%H:%M")
            # crossing from >=0 to <0 => moon set
            if moon_alts[idx] >= 0.0 and moon_alts[idx+1] < 0.0 and moon_set == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                moon_set = dt_loc.strftime("%H:%M")

        # Format sums
        a_hrs = astro_minutes // 60
        a_min = astro_minutes % 60
        astro_str = f"{a_hrs}hrs {a_min}min"

        m_hrs = moonless_minutes // 60
        m_min = moonless_minutes % 60
        moonl_str = f"{m_hrs}hrs {m_min}min"

        # Moon phase
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
    # --- Initialize session state keys at the very top (fixes KeyError) ---
    if "city" not in st.session_state:
        st.session_state["city"] = "Marrakech"
    if "lat" not in st.session_state:
        st.session_state["lat"] = 31.6258
    if "lon" not in st.session_state:
        st.session_state["lon"] = -7.9892
    if "dates_range" not in st.session_state:
        st.session_state["dates_range"] = (date.today(), date.today() + timedelta(days=1))
    if "progress_console" not in st.session_state:
        st.session_state["progress_console"] = ""
    if "last_map_click" not in st.session_state:
        st.session_state["last_map_click"] = None
    # ---------------------------------------------------------------------

    st.title("Astronomical Darkness Calculator")

    # Friendly explanation
    st.write("""This tool calculates how many hours of proper darkness you get each night, 
    factoring in the Sun’s altitude and the Moon’s position. 
    It’s ideal for planning astronomy trips or holidays, 
    so you can pick dates and locations with the most moon-free dark sky time! 
    Simply choose your location (via city or map or lat/lon) and your date range. 
    Then hit **Calculate** and we’ll do the rest.""")

    # Coordinates & City Input
    st.markdown("#### Coordinates & City Input")
    st.write("Either enter a city, lat/long, or click the map, then pick date range & press Calculate.")

    rowc = st.columns(3)
    with rowc[0]:
        cval = st.text_input(
            "City (optional)",
            value=st.session_state["city"],
            help="Type a city name (e.g. 'London'). If recognized, lat/lon will update automatically."
        )
        if cval != st.session_state["city"]:
            coords = geocode_city(cval, st.secrets["locationiq"]["token"])
            if coords:
                st.session_state["lat"], st.session_state["lon"] = coords
                st.session_state["city"] = cval
                st.success(f"Location updated => {coords}")
            else:
                st.warning("City not found or usage limit. Keeping old coords.")

    with rowc[1]:
        lat_in = st.number_input(
            "Latitude",
            value=st.session_state["lat"],
            format="%.6f",
            min_value=-90.0,
            max_value=90.0,
            help="Decimal degrees (e.g. 31.6258). Range: -90 to 90."
        )
        if abs(lat_in - st.session_state["lat"]) > 1e-7:
            st.session_state["lat"] = lat_in

    with rowc[2]:
        lon_in = st.number_input(
            "Longitude",
            value=st.session_state["lon"],
            format="%.6f",
            min_value=-180.0,
            max_value=180.0,
            help="Decimal degrees (e.g. -7.9892). Range: -180 to 180."
        )
        if abs(lon_in - st.session_state["lon"]) > 1e-7:
            st.session_state["lon"] = lon_in

    # Map
    st.markdown("#### Location on Map")
    # Here is the custom-styled box
    st.markdown(
        """
<div style="
    background-color: #FFF3CD; 
    padding: 10px; 
    border-radius: 5px; 
    border: 1px solid #FFEEBA;
    margin-bottom: 1rem;">
  <p style="color: #856404; font-weight: bold;">
    You may need to click the map a few times to make it work! Free API fun! :)
  </p>
</div>
""",
        unsafe_allow_html=True
    )

    fol_map = folium.Map(location=[st.session_state["lat"], st.session_state["lon"]], zoom_start=6)
    folium.Marker(
        [st.session_state["lat"], st.session_state["lon"]], 
        popup="Current"
    ).add_to(fol_map)
    map_out = st_folium(fol_map, width=700, height=450)
    if map_out and "last_clicked" in map_out and map_out["last_clicked"]:
        clat = map_out["last_clicked"]["lat"]
        clon = map_out["last_clicked"]["lng"]
        if -90 <= clat <= 90 and -180 <= clon <= 180:
            if "last_map_click" not in st.session_state or st.session_state["last_map_click"] != (clat, clon):
                st.session_state["lat"] = clat
                st.session_state["lon"] = clon
                found_city = reverse_geocode(clat, clon, st.secrets["locationiq"]["token"])
                if found_city:
                    st.session_state["city"] = found_city
                    st.success(f"Map => {found_city} ({clat:.4f}, {clon:.4f})")
                else:
                    st.success(f"Map => lat/lon=({clat:.4f}, {clon:.4f})")
                st.session_state["last_map_click"] = (clat, clon)

    # Next row: Calculation form
    st.markdown("### Calculate Darkness")
    st.write("""Under the hood, we calculate Sun & Moon altitudes at each time step—no paid external API needed!
    This can take a bit longer for large date ranges, so please be patient while the progress bar updates.""")

    with st.form("calc_form"):
        row2 = st.columns(3)
        with row2[0]:
            dval = st.date_input(
                "Pick up to 30 days",
                value=st.session_state["dates_range"],
                help="Select a start & end date. We label each day from local noon→next noon."
            )
        with row2[1]:
            threshold_opts = {
                "Civil (−6°)": 6,
                "Nautical (−12°)": 12,
                "Astronomical (−18°)": 18
            }
            thr_label = st.selectbox(
                "Twilight Threshold",
                options=list(threshold_opts.keys()),
                index=2,
                help="How many degrees below the horizon must the Sun be?\n- Civil: sun < -6°\n- Nautical: < -12°\n- Astro: < -18°"
            )
            twi_val = threshold_opts[thr_label]

        with row2[2]:
            step_opts = ["1", "2", "5", "10", "15", "30"]
            step_str = st.selectbox(
                "Time Step (Mins)",
                options=step_opts,
                index=0,
                help="""How finely we calculate the Sun & Moon. 
- 1 min => ~1440 calculations/day (precise).
- 15 min => ~96 calculations/day (faster, less detail).
"""
            )
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

        # Show progress bar
        pbar_placeholder = st.empty()
        pbar = pbar_placeholder.progress(0)

        nights_data = compute_night_details(
            st.session_state["lat"],
            st.session_state["lon"],
            sd,
            ed,
            twi_val,
            step_minutes,
            pbar
        )

        if not nights_data:
            st.warning("No data?? Possibly 0-day range or error.")
            st.stop()

        # Summation
        total_astro_min = 0
        total_moonless_min = 0
        for rowd in nights_data:
            d_hrs_str = rowd["Dark Hours"].split("hrs")[0].strip()
            d_min_str = rowd["Dark Hours"].split("hrs")[1].replace("min","").strip()
            d_hrs = int(d_hrs_str)
            d_m   = int(d_min_str)

            m_hrs_str = rowd["Moonless Hours"].split("hrs")[0].strip()
            m_min_str = rowd["Moonless Hours"].split("hrs")[1].replace("min","").strip()
            m_hrs = int(m_hrs_str)
            m_m   = int(m_min_str)

            total_astro_min += (d_hrs*60 + d_m)
            total_moonless_min += (m_hrs*60 + m_m)

        st.markdown("#### Results")
        box_cols = st.columns(2)
        with box_cols[0]:
            A_h = total_astro_min // 60
            A_m = total_astro_min % 60
            st.markdown(f"""
            <div class="result-box">
              <div class="result-title">Total Astro Darkness</div>
              <div class="result-value">{A_h}hrs {A_m}min</div>
            </div>
            """, unsafe_allow_html=True)
        with box_cols[1]:
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
        st.text_area(
            "Progress Console",
            value=st.session_state["progress_console"],
            height=150,
            disabled=True,
            label_visibility="collapsed"
        )

if __name__ == "__main__":
    main()
