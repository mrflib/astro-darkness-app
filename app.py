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

# Additional custom CSS:
# 1) Dark-green (#218838) for the "Calculate" button and progress bar
# 2) Remove the default form background/border/padding
# 3) Slightly smaller border-radius for result boxes
st.markdown(r"""
<style>
/* Make the "Calculate" button #218838 */
.stButton > button {
    background-color: #218838 !important;
    border-color: #1e7e34 !important;
    color: white !important;
}
/* Progress bar override to the same #218838 */
div[role='progressbar'] div {
    background-color: #218838 !important;
}

/* Remove any default styling on st.form */
div[data-testid="stForm"] {
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
}

/* Slightly smaller radius for the result-box */
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
    twilight_threshold,  # e.g. 6 for civil, 12 for nautical, 18 for astro
    step_minutes
):
    """
    For each local day from local noon->noon, label it "Night of D".
    We count:
      - astro_minutes if sun_alt < -threshold
      - moonless_minutes if moon_alt < 0 as well
    Then find crossing times for:
      - Dark Start, Dark End (sun crossing -threshold)
      - Moon Rise, Moon Set (moon crossing 0)
    Return: 
      Night, Dark Start, Dark End, Moon Rise, Moon Set, 
      Dark Hours, Moonless Hours, Phase
    Where 'Dark Hours' is "6hrs 32min" format.
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
            # Sun & Moon alt
            sun_alt = observer.at(tsky).observe(eph['Sun']).apparent().altaz()[0].degrees
            moon_alt = observer.at(tsky).observe(eph['Moon']).apparent().altaz()[0].degrees
            times_list.append(tsky)
            sun_alts.append(sun_alt)
            moon_alts.append(moon_alt)

        astro_minutes = 0
        moonless_minutes = 0
        for idx in range(len(times_list)-1):
            # Sun < -threshold
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
            # crossing from >= -threshold to < -threshold => dark start
            if sun_alts[idx] >= -twilight_threshold and sun_alts[idx+1] < -twilight_threshold and dark_start == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                dark_start = dt_loc.strftime("%H:%M")
            # crossing from < -threshold to >= -threshold => dark end
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

        # Convert sums to "Xhrs Ymin"
        a_hrs = astro_minutes // 60
        a_min = astro_minutes % 60
        astro_str = f"{a_hrs}hrs {a_min}min"

        m_hrs = moonless_minutes // 60
        m_min = moonless_minutes % 60
        moonl_str = f"{m_hrs}hrs {m_min}min"

        # moon phase at local noon
        from skyfield.api import load
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

    # Row for city/lat/lon
    st.markdown("#### Coordinates & City Input")
    top_cols = st.columns(3)
    with top_cols[0]:
        cval = st.text_input(
            "City (optional)",
            value=st.session_state["city"],
            help="Type a city name. If recognized, lat/lon updates immediately."
        )
        if cval != st.session_state["city"]:
            coords = geocode_city(cval, LOCATIONIQ_TOKEN)
            if coords:
                st.session_state["lat"], st.session_state["lon"] = coords
                st.session_state["city"] = cval
                st.success(f"Updated location => {coords}")
            else:
                st.warning("City not found or usage limit. Keeping old coords.")

    with top_cols[1]:
        lat_in = st.number_input(
            "Latitude",
            value=st.session_state["lat"],
            format="%.6f",
            min_value=-90.0,
            max_value=90.0
        )
        if abs(lat_in - st.session_state["lat"]) > 1e-7:
            st.session_state["lat"] = lat_in

    with top_cols[2]:
        lon_in = st.number_input(
            "Longitude",
            value=st.session_state["lon"],
            format="%.6f",
            min_value=-180.0,
            max_value=180.0
        )
        if abs(lon_in - st.session_state["lon"]) > 1e-7:
            st.session_state["lon"] = lon_in

    # Map
    st.markdown("#### Location on Map")
    fol_map = folium.Map(location=[st.session_state["lat"], st.session_state["lon"]], zoom_start=6)
    folium.Marker([st.session_state["lat"], st.session_state["lon"]], popup="Current").add_to(fol_map)
    map_res = st_folium(fol_map, width=700, height=450)
    if map_res and "last_clicked" in map_res and map_res["last_clicked"]:
        clat = map_res["last_clicked"]["lat"]
        clon = map_res["last_clicked"]["lng"]
        if -90 <= clat <= 90 and -180 <= clon <= 180:
            if st.session_state["last_map_click"] != (clat, clon):
                st.session_state["lat"] = clat
                st.session_state["lon"] = clon
                cfound = reverse_geocode(clat, clon, LOCATIONIQ_TOKEN)
                if cfound:
                    st.session_state["city"] = cfound
                    st.success(f"Map => {cfound} ({clat:.4f}, {clon:.4f})")
                else:
                    st.success(f"Map => lat/lon=({clat:.4f}, {clon:.4f})")
                st.session_state["last_map_click"] = (clat, clon)

    st.write("You may need to click the map a few times to make it work! Free API fun! :)")

    # Next row (form) for date range, threshold, time step
    st.markdown("### Calculate Darkness")
    with st.form("calc_form"):
        row2 = st.columns(3)
        with row2[0]:
            dval = st.date_input(
                "Pick up to 30 days",
                value=st.session_state["dates_range"],
                help="Select 2 dates. We'll treat each day noon->noon."
            )
        with row2[1]:
            thr_tooltip = (
                "Choose the twilight threshold:\n"
                "- Civil: Sun < -6°\n"
                "- Nautical: Sun < -12°\n"
                "- Astronomical: Sun < -18° (default)"
            )
            threshold_opts = {
                "Civil (−6)": 6,
                "Nautical (−12)": 12,
                "Astronomical (−18)": 18
            }
            thr_label = st.selectbox(
                "Twilight Threshold",
                options=list(threshold_opts.keys()),
                index=2,  # default = "Astronomical (−18)"
                help=thr_tooltip
            )
            twilight_threshold = threshold_opts[thr_label]

        with row2[2]:
            step_opts = ["1", "2", "5", "10", "15", "30"]
            step_str = st.selectbox(
                "Time Step (Mins)",
                options=step_opts,
                index=0,
                help="Lower => more precise but slower (1 => 1440 checks/day)."
            )
            step_minutes = int(step_str)

        calc_btn = st.form_submit_button("Calculate")

    if calc_btn:
        if len(dval) == 1:
            start_d = dval[0]
            end_d   = dval[0]
        else:
            start_d, end_d = dval[0], dval[-1]
        if start_d > end_d:
            st.error("Start date must be <= end date.")
            st.stop()

        day_count = (end_d - start_d).days + 1
        if day_count > MAX_DAYS:
            st.error(f"You picked {day_count} days, max allowed is {MAX_DAYS}.")
            st.stop()

        st.session_state["dates_range"] = (start_d, end_d)
        st.session_state["progress_console"] = ""
        debug_print("Starting night-labeled calculations...")

        # Show progress bar
        pbar_holder = st.empty()
        pbar = pbar_holder.progress(0)

        nights_data = compute_night_details(
            st.session_state["lat"],
            st.session_state["lon"],
            start_d,
            end_d,
            twilight_threshold,
            step_minutes
        )
        pbar.progress(1.0)

        if not nights_data:
            st.warning("No data?? Possibly 0-day range or error.")
            st.stop()

        # Summation
        total_astro_min = 0
        total_moonless_min = 0
        for rowdict in nights_data:
            # "Dark Hours" => "6hrs 32min"
            d_hrs_str = rowdict["Dark Hours"].split("hrs")[0].strip()
            d_min_str = rowdict["Dark Hours"].split("hrs")[1].replace("min","").strip()
            d_hrs = int(d_hrs_str)
            d_m   = int(d_min_str)

            # "Moonless Hours" => "4hrs 17min"
            m_hrs_str = rowdict["Moonless Hours"].split("hrs")[0].strip()
            m_min_str = rowdict["Moonless Hours"].split("hrs")[1].replace("min","").strip()
            m_hrs = int(m_hrs_str)
            m_m   = int(m_min_str)

            total_astro_min += (d_hrs*60 + d_m)
            total_moonless_min += (m_hrs*60 + m_m)

        st.markdown("#### Results")
        r_cols = st.columns(2)
        with r_cols[0]:
            a_h = total_astro_min // 60
            a_m = total_astro_min % 60
            st.markdown(f"""
            <div class="result-box">
              <div class="result-title">Total Astro Darkness</div>
              <div class="result-value">{a_h}hrs {a_m}min</div>
            </div>
            """, unsafe_allow_html=True)
        with r_cols[1]:
            mo_h = total_moonless_min // 60
            mo_m = total_moonless_min % 60
            st.markdown(f"""
            <div class="result-box">
              <div class="result-title">Total Moonless Dark</div>
              <div class="result-value">{mo_h}hrs {mo_m}min</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("#### Night-by-Night Breakdown")
        df = pd.DataFrame(nights_data)

        # We'll center all cells, including headers, and center the table. 
        df_styled = df.style.set_properties(**{'text-align': 'center'})
        df_styled.set_table_styles([
            {'selector': 'th', 'props': [('text-align', 'center')]},
            {'selector': 'td', 'props': [('text-align', 'center')]},
            {'selector': 'table', 'props': [('margin', '0 auto')]},  # center table
        ])

        st.markdown(df_styled.to_html(index=True), unsafe_allow_html=True)

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
