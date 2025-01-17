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

# Custom CSS: slightly darker green (#218838), 
# plus a box style for city/lat/lon+map container
st.markdown("""
<style>
textarea {
    font-family: "Courier New", monospace;
}
.result-box {
    background-color: #218838; /* darker green */
    color: white;
    border-radius: 12px;
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
.city-map-box {
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 12px;
    padding: 15px;
    margin-bottom: 20px;
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
    """Return a Moon phase emoji (no text label)."""
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
def compute_night_details(lat, lon, start_date, end_date, step_minutes):
    """
    For each local day from local noon->noon, label it "Night of D".
    We compute:
      - astro_minutes = sun < -18
      - moonless_minutes = sun < -18 & moon < 0
    Then find crossing times for 
      - Dark Start/End (sun crossing -18)
      - Moon Rise/Set (moon crossing 0)
    Also compute a "phase_emoji" for the day.

    Returns a list of dicts for each day with columns:
      "Night",
      "Dark Start",
      "Dark End",
      "Moon Rise",
      "Moon Set",
      "Dark Hours",
      "Moonless Hours",
      "Phase" (the emoji).
    """
    from skyfield.api import load, Topos
    ts = load.timescale()
    eph = load('de421.bsp')
    observer = eph['Earth'] + Topos(latitude_degrees=lat, longitude_degrees=lon)

    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lon)
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

    for d_i in range(total_days):
        label_date = start_date + timedelta(days=d_i)
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

        from skyfield.api import load
        for s in range(steps+1):
            dt_utc = start_utc + timedelta(minutes=s*step_minutes)
            tsky = ts.from_datetime(dt_utc)
            times_list.append(tsky)
            sun_alt = observer.at(tsky).observe(eph['Sun']).apparent().altaz()[0].degrees
            moon_alt = observer.at(tsky).observe(eph['Moon']).apparent().altaz()[0].degrees
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

        # convert to X Hours Y Minutes
        d_h  = astro_minutes // 60
        d_m  = astro_minutes % 60
        ml_h = moonless_minutes // 60
        ml_m = moonless_minutes % 60

        # Moon phase at local noon
        t_noon = ts.from_datetime(local_noon_aware.astimezone(pytz.utc))
        obs_noon = observer.at(t_noon)
        sun_ecl  = obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360
        phase_emoji = moon_phase_icon(phase_angle)

        nights_data.append({
            "Night": label_date.strftime("%Y-%m-%d"),
            "Dark Start": dark_start_str,
            "Dark End":   dark_end_str,
            "Moon Rise":  moon_rise_str,
            "Moon Set":   moon_set_str,
            "Dark Hours": f"{d_h} Hours {d_m} Minutes",
            "Moonless Hours": f"{ml_h} Hours {ml_m} Minutes",
            "": phase_emoji  # blank column header => just the icon
        })

    return nights_data


########################################
# MAIN
########################################
def main():
    st.title("Astronomical Darkness Calculator (Night-Labeled)")
    st.write("Either enter a city, or lat/long, or select a location on the map, then pick your date range and press Calculate.")

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

    # Box container for city/lat/lon + map
    st.markdown('<div class="city-map-box">', unsafe_allow_html=True)
    row1 = st.columns(3)
    with row1[0]:
        city_val = st.text_input(
            "City (optional)",
            value=st.session_state["city"],
            help="Type a city name. If recognized, lat/lon updates immediately."
        )
        if city_val != st.session_state["city"]:
            coords = geocode_city(city_val, LOCATIONIQ_TOKEN)
            if coords:
                st.session_state["lat"], st.session_state["lon"] = coords
                st.session_state["city"] = city_val
                st.success(f"Updated location => {coords}")
            else:
                st.warning("City not found or usage limit reached. Keeping old coords.")

    with row1[1]:
        lat_in = st.number_input(
            "Latitude",
            value=st.session_state["lat"],
            format="%.6f",
            min_value=-90.0,
            max_value=90.0
        )
        if abs(lat_in - st.session_state["lat"]) > 1e-7:
            st.session_state["lat"] = lat_in

    with row1[2]:
        lon_in = st.number_input(
            "Longitude",
            value=st.session_state["lon"],
            format="%.6f",
            min_value=-180.0,
            max_value=180.0
        )
        if abs(lon_in - st.session_state["lon"]) > 1e-7:
            st.session_state["lon"] = lon_in

    st.markdown("#### Map (Click to update Lat/Lon)")
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
                # optional reverse geocode
                found_c = reverse_geocode(clat, clon, LOCATIONIQ_TOKEN)
                if found_c:
                    st.session_state["city"] = found_c
                    st.success(f"Map => {found_c} ({clat:.4f}, {clon:.4f})")
                else:
                    st.success(f"Map => lat/lon=({clat:.4f}, {clon:.4f})")
                st.session_state["last_map_click"] = (clat, clon)

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("### Calculation")
    with st.form("calc_form"):
        row2 = st.columns(3)
        with row2[0]:
            date_range_val = st.date_input(
                "Pick up to 30 days",
                value=st.session_state["dates_range"],
                help="Select 2 dates (noon-labeled)."
            )
        with row2[1]:
            moon_opts = ["Ignore Moon", "Subtract Moonlight"]
            moon_mode = st.selectbox(
                "Moon Influence",
                options=moon_opts,
                help="Ignore => bigger astro total, Subtract => only sun<-18 & moon<0 for final total."
            )
        with row2[2]:
            step_opts = ["1", "2", "5", "10", "15", "30"]
            step_str = st.selectbox(
                "Time Step (Mins)",
                options=step_opts,
                index=0,
                help="Lower => more precise but slower. e.g. 1 => 1440 checks/day"
            )
            step_minutes = int(step_str)

        calc_submitted = st.form_submit_button("Calculate")

    if calc_submitted:
        # parse date range carefully
        if len(date_range_val) == 1:
            start_d = date_range_val[0]
            end_d   = date_range_val[0]
        else:
            start_d, end_d = date_range_val[0], date_range_val[-1]

        if start_d > end_d:
            st.error("Start date must be <= end date.")
            st.stop()

        dayc = (end_d - start_d).days + 1
        if dayc > MAX_DAYS:
            st.error(f"You selected {dayc} days. Max is {MAX_DAYS}.")
            st.stop()

        st.session_state["dates_range"] = (start_d, end_d)
        st.session_state["progress_console"] = ""
        debug_print("Starting calculations...")

        # show progress bar
        pbar_placeholder = st.empty()
        pbar = pbar_placeholder.progress(0)

        # compute
        nights_list = compute_night_details(
            st.session_state["lat"],
            st.session_state["lon"],
            start_d,
            end_d,
            step_minutes
        )
        pbar.progress(1.0)

        if not nights_list:
            st.warning("No data?? Possibly zero-day range or error.")
            st.stop()

        # Summaries
        total_astro_min = 0
        total_moonless_min = 0
        for rowdict in nights_list:
            # rowdict["Dark Hours"] => "3 Hours 15 Minutes"
            sp = rowdict["Dark Hours"].split()
            ah, am = int(sp[0]), int(sp[2])
            total_astro_min += (ah*60 + am)

            # rowdict["Moonless Hours"] => "1 Hours 45 Minutes"
            s2 = rowdict["Moonless Hours"].split()
            mh, mm = int(s2[0]), int(s2[2])
            total_moonless_min += (mh*60 + mm)

        # 2 green boxes
        st.markdown("#### Results")
        results_cols = st.columns(2)
        with results_cols[0]:
            A_h = total_astro_min // 60
            A_m = total_astro_min % 60
            st.markdown(f"""
            <div class="result-box">
                <div class="result-title">Total Astro Darkness</div>
                <div class="result-value">{A_h} Hours {A_m} Minutes</div>
            </div>
            """, unsafe_allow_html=True)
        with results_cols[1]:
            M_h = total_moonless_min // 60
            M_m = total_moonless_min % 60
            st.markdown(f"""
            <div class="result-box">
                <div class="result-title">Total Moonless Dark</div>
                <div class="result-value">{M_h} Hours {M_m} Minutes</div>
            </div>
            """, unsafe_allow_html=True)

        # day by day
        st.markdown("#### Night-by-Night Breakdown")
        df = pd.DataFrame(nights_list)
        # let it show index for a "smart" table with row numbers
        st.dataframe(df)  # shows index, plus columns, including the no-header "" for phase icon

        # show console
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
