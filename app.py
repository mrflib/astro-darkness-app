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

# Custom CSS:
# 1) Two result boxes still #218838 green
# 2) "6hrs 32min" format in code (not in CSS)
# 3) Button + progress bar in #218838
st.markdown("""
<style>
/* Button color override */
.stButton > button {
    background-color: #218838 !important;
    border-color: #1e7e34 !important;
    color: white !important;
}
/* Progress bar override */
div[role='progressbar'] div {
    background-color: #218838 !important;
}
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
    """Return a Moon phase emoji with no header text."""
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
    twilight_threshold,  # e.g. -6 for civil, -12 for nautical, -18 for astro
    step_minutes
):
    """
    For each local day from local noon->noon, label it "Night of D".
    We sum times sun_alt < (twilight_threshold * -1),
      i.e. if threshold=-12 => sun_alt < -12 => "dark".
    Then also check if moon_alt < 0 => "moonless".

    Return columns:
      * Night
      * Dark Start, Dark End
      * Moon Rise, Moon Set
      * Dark Hours (with "Xhrs Ymin" format)
      * Moonless Hours (with "Xhrs Ymin" format)
      * "" => phase emoji
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
    day_count = (end_date - start_date).days + 1
    for i in range(day_count):
        label_date = start_date + timedelta(days=i)
        debug_print(f"Processing 'Night of {label_date}' (noon->noon).")

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
            tsky = ts.from_datetime(dt_utc)
            sun_alt_deg = observer.at(tsky).observe(eph['Sun']).apparent().altaz()[0].degrees
            moon_alt_deg = observer.at(tsky).observe(eph['Moon']).apparent().altaz()[0].degrees
            times_list.append(tsky)
            sun_alts.append(sun_alt_deg)
            moon_alts.append(moon_alt_deg)

        # Summations
        astro_minutes = 0
        moonless_minutes = 0
        for idx in range(len(times_list)-1):
            if sun_alts[idx] < -twilight_threshold:  # e.g. -(-12)=12 => sun_alt < -12
                astro_minutes += step_minutes
                if moon_alts[idx] < 0.0:
                    moonless_minutes += step_minutes

        # crossing times
        dark_start_str = "-"
        dark_end_str   = "-"
        moon_rise_str  = "-"
        moon_set_str   = "-"

        for idx in range(len(sun_alts)-1):
            # crossing from >= -threshold to < -threshold => dark start
            if sun_alts[idx] >= -twilight_threshold and sun_alts[idx+1] < -twilight_threshold and dark_start_str == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                dark_start_str = dt_loc.strftime("%H:%M")
            # crossing from < -threshold to >= -threshold => dark end
            if sun_alts[idx] < -twilight_threshold and sun_alts[idx+1] >= -twilight_threshold and dark_end_str == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                dark_end_str = dt_loc.strftime("%H:%M")

        for idx in range(len(moon_alts)-1):
            # crossing from <0 to >=0 => moon rise
            if moon_alts[idx] < 0.0 and moon_alts[idx+1] >= 0.0 and moon_rise_str == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                moon_rise_str = dt_loc.strftime("%H:%M")
            # crossing from >=0 to <0 => moon set
            if moon_alts[idx] >= 0.0 and moon_alts[idx+1] < 0.0 and moon_set_str == "-":
                dt_loc = times_list[idx+1].utc_datetime().astimezone(local_tz)
                moon_set_str = dt_loc.strftime("%H:%M")

        # Convert sums to "Xhrs Ymin"
        d_hrs = astro_minutes // 60
        d_min = astro_minutes % 60
        m_hrs = moonless_minutes // 60
        m_min = moonless_minutes % 60
        dark_str = f"{d_hrs}hrs {d_min}min"
        moonl_str= f"{m_hrs}hrs {m_min}min"

        # moon phase at local noon
        from skyfield.api import load
        t_noon = load.timescale().from_datetime(local_noon_aware.astimezone(pytz.utc))
        observer_noon = observer.at(t_noon)
        sun_ecl  = observer_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = observer_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360
        phase_emoji = moon_phase_icon(phase_angle)

        nights_data.append({
            "Night": label_date.strftime("%Y-%m-%d"),
            "Dark Start": dark_start_str,
            "Dark End": dark_end_str,
            "Moon Rise": moon_rise_str,
            "Moon Set": moon_set_str,
            "Dark Hours": dark_str,
            "Moonless Hours": moonl_str,
            "": phase_emoji  # no column header
        })

    return nights_data

########################################
# MAIN
########################################
def main():
    st.title("Astronomical Darkness Calculator (Night-Labeled)")
    st.write("Either enter a city, lat/long, or click the map, then pick date range & press Calculate.")

    # session defaults
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

    # top row: city, lat, lon, outside form
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
                st.warning("City not found or usage limit reached. Keeping old coords.")

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

    st.markdown("#### Location on Map (click to update lat/lon)")

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
                # optional reverse
                cfound = reverse_geocode(clat, clon, LOCATIONIQ_TOKEN)
                if cfound:
                    st.session_state["city"] = cfound
                    st.success(f"Map => {cfound} ({clat:.4f}, {clon:.4f})")
                else:
                    st.success(f"Map => lat/lon=({clat:.4f}, {clon:.4f})")
                st.session_state["last_map_click"] = (clat, clon)

    # row 2 form: date range, twilight threshold, time step, button
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
                index=2,  # default = Astronomical
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
        # parse date range
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

        # Show progress bar in same green
        pbar_holder = st.empty()
        pbar = pbar_holder.progress(0)

        nights = compute_night_details(
            st.session_state["lat"],
            st.session_state["lon"],
            start_d,
            end_d,
            twilight_threshold,
            step_minutes
        )
        pbar.progress(1.0)

        if not nights:
            st.warning("No data?? Possibly 0-day range or error.")
            st.stop()

        # Summation for total astro vs moonless
        total_astro_min = 0
        total_moonless_min = 0
        for rowd in nights:
            # "Dark Hours" => "6hrs 32min"
            spl = rowd["Dark Hours"].split()
            # e.g. ["6hrs","32min"]
            # strip "hrs" / "min"
            d_hrs = int(spl[0].replace("hrs",""))
            d_min = int(spl[1].replace("min",""))
            total_astro_min += d_hrs*60 + d_min

            # "Moonless Hours" => "3hrs 12min"
            s2 = rowd["Moonless Hours"].split()
            m_hrs = int(s2[0].replace("hrs",""))
            m_min = int(s2[1].replace("min",""))
            total_moonless_min += m_hrs*60 + m_min

        # 2 green boxes
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
        df = pd.DataFrame(nights)
        st.dataframe(df)  # "smart" table with index

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
