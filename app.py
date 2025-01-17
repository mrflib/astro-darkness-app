############################
# app.py
# Non-discrete step-based approach with Date Picker Fix and Map Reintroduction
############################

########## CONFIGURATION BLOCK ##########
MAX_DAYS = 30         # Maximum number of days allowed
STEP_MINUTES = 1      # Stepping in minutes
USE_CITY_SEARCH = True
DEBUG = True
SHOW_BULLETS = True
######## END CONFIG BLOCK ###############

import streamlit as st
from datetime import date, datetime, timedelta
import pytz
from timezonefinder import TimezoneFinder
import pandas as pd
from skyfield.api import load, Topos
import folium
from streamlit_folium import st_folium

if USE_CITY_SEARCH:
    from geopy.geocoders import Nominatim

########################################
# PAGE CONFIG + Custom CSS
########################################
st.set_page_config(
    page_title="Astronomical Darkness Calculator (Non-Discrete)",
    page_icon="🌑",
    layout="centered"
)

# Enlarge the “No Moon” checkbox and set fixed-width font for Progress Console
st.markdown("""
<style>
    .stCheckbox > div:first-child {
        transform: scale(1.2); 
        margin-top: 5px;
        margin-bottom: 5px;
    }
    /* Fixed-width font for Progress Console */
    textarea {
        font-family: "Courier New", Courier, monospace;
    }
</style>
""", unsafe_allow_html=True)

########################################
# UTILS
########################################
def maybe_show_bullets():
    if SHOW_BULLETS:
        st.write(f"- Up to {MAX_DAYS} days")
        st.write(f"- Non-discrete step-based approach, {STEP_MINUTES}-min increments")
        st.write(f"- City search is {'ON' if USE_CITY_SEARCH else 'OFF'}")
        st.write(f"- Debug prints: {'YES' if DEBUG else 'NO'}")

def debug_print(msg: str):
    if DEBUG:
        st.write(msg)

def geocode_place(place_name):
    if not USE_CITY_SEARCH:
        return None
    geolocator = Nominatim(user_agent="astro_app")
    try:
        loc = geolocator.geocode(place_name)
        if loc:
            return (loc.latitude, loc.longitude)
    except:
        pass
    return None

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

def find_dark_crossings(sun_alts, times_list, local_tz):
    """
    Return (dark_start_str, dark_end_str) by scanning from >=-18 -> < -18 for start,
    then < -18 -> >= -18 for end. If dark_end is not found on the same day, it assumes
    dark_end occurs on the next day and returns the time accordingly.
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

    # If dark end wasn't found on the same day, attempt to find it on the next day
    if found_start and end_str == "-":
        for i in range(N-1):
            if sun_alts[i] < -18 and sun_alts[i+1] >= -18:
                dt_loc = times_list[i+1].utc_datetime().astimezone(local_tz)
                end_str = dt_loc.strftime("%H:%M")
                break

    return (start_str, end_str)

def compute_day_details_step(lat, lon, start_date, end_date, no_moon):
    """
    Performs the astronomical darkness calculations.
    Returns the day-by-day results.
    """
    debug_print("DEBUG: Entering compute_day_details_step")

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
        alt, _, _ = app_moon.altaz()
        return alt.degrees

    day_results = []
    day_count = 0
    current = start_date

    while current <= end_date and day_count < MAX_DAYS:
        debug_print(f"DEBUG: Day {day_count}, date={current}")

        local_mid = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)

        start_aware = local_tz.localize(local_mid)
        end_aware = local_tz.localize(local_next)
        start_utc = start_aware.astimezone(pytz.utc)
        end_utc = end_aware.astimezone(pytz.utc)

        # Build stepping
        step_count = int((24*60)//STEP_MINUTES)
        debug_print(f"DEBUG: step_count={step_count} for date={current}")

        times_list = []
        for i in range(step_count+1):
            dt_utc = start_utc + timedelta(minutes=i*STEP_MINUTES)
            times_list.append(ts.from_datetime(dt_utc))

        sun_alts = []
        moon_alts = []
        for i, sky_t in enumerate(times_list):
            alt_sun = sun_alt_deg(sky_t)
            alt_moon = moon_alt_deg(sky_t)
            sun_alts.append(alt_sun)
            moon_alts.append(alt_moon)

        debug_print(f"DEBUG: built alt arrays, length={len(sun_alts)}")

        # Summation
        astro_minutes = 0
        moonless_minutes = 0
        for i in range(len(times_list)-1):
            s_mid = (sun_alts[i] + sun_alts[i+1])/2
            m_mid = (moon_alts[i] + moon_alts[i+1])/2
            if s_mid < -18.0:
                astro_minutes += STEP_MINUTES
                if no_moon:
                    if m_mid < 0.0:
                        moonless_minutes += STEP_MINUTES
                else:
                    moonless_minutes += STEP_MINUTES

        astro_hrs = astro_minutes/60.0
        moonless_hrs = moonless_minutes/60.0
        debug_print(f"DEBUG: date={current}, astro_hrs={astro_hrs:.2f}, moonless_hrs={moonless_hrs:.2f}")

        # Dark start/end
        start_dark_str = "-"
        end_dark_str = "-"
        found_dark = False
        for i in range(len(sun_alts)-1):
            if sun_alts[i] < -18 and not found_dark:
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                start_dark_str = dt_loc.strftime("%H:%M")
                found_dark = True
            if found_dark and sun_alts[i]>=-18:
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                end_dark_str = dt_loc.strftime("%H:%M")
                break
        if found_dark and end_dark_str=="-":
            dt_loc = times_list[-1].utc_datetime().astimezone(local_tz)
            end_dark_str = dt_loc.strftime("%H:%M")

        # Moon rise/set
        m_rise_str = "-"
        m_set_str = "-"
        prev_alt = moon_alts[0]
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
        local_noon_aware = local_tz.localize(local_noon)
        noon_utc = local_noon_aware.astimezone(pytz.utc)
        t_noon = ts.from_datetime(noon_utc)
        obs_noon = observer.at(t_noon)
        sun_ecl = obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360

        day_results.append({
            "date": current.strftime("%Y-%m-%d"),
            "astro_dark_hours": round(astro_hrs,2),
            "moonless_hours": round(moonless_hrs,2),
            "dark_start": start_dark_str,
            "dark_end": end_dark_str,
            "moon_rise": m_rise_str,
            "moon_set": m_set_str,
            "moon_phase": moon_phase_icon(phase_angle)
        })

        current += timedelta(days=1)
        day_count +=1

    debug_print("DEBUG: Exiting compute_day_details_step, returning results.")
    return day_results

##################################
# MAIN
##################################
def main():
    maybe_show_bullets()

    st.subheader("Location & Date Range (Non-Discrete Step)")

    # Initialize session defaults for selected_dates
    if "selected_dates" not in st.session_state:
        st.session_state["selected_dates"] = [date.today(), date.today() + timedelta(days=1)]

    lat_default = 31.6258
    lon_default = -7.9892

    if USE_CITY_SEARCH:
        city_input = st.text_input("City (optional)", "Marrakech")
        if city_input:
            coords = geocode_place(city_input)
            if coords:
                lat_default, lon_default = coords
            else:
                st.warning("City not found. Check spelling or use lat/lon below.")

    # Latitude and Longitude Inputs
    lat_in = st.number_input("Latitude", value=lat_default, format="%.6f", key="latitude_input")
    lon_in = st.number_input("Longitude", value=lon_default, format="%.6f", key="longitude_input")

    # Date Range Selector bound to 'selected_dates' in session state
    d_range = st.date_input(
        f"Pick up to {MAX_DAYS} days",
        value=st.session_state["selected_dates"],
        key="selected_dates",
        help=f"Select a date range of up to {MAX_DAYS} days."
    )

    # Update 'selected_dates' in session state based on user selection
    if isinstance(d_range, list) or isinstance(d_range, tuple):
        if len(d_range) == 1:
            st.session_state["selected_dates"] = [d_range[0], d_range[0]]
        elif len(d_range) >=2:
            st.session_state["selected_dates"] = [d_range[0], d_range[-1]]
    elif isinstance(d_range, date):
        st.session_state["selected_dates"] = [d_range, d_range]

    # Calculate delta_days
    if len(st.session_state["selected_dates"]) >=2:
        start_d, end_d = st.session_state["selected_dates"][:2]
        delta_days = (end_d - start_d).days + 1
        if delta_days > MAX_DAYS:
            st.error(f"Please pick {MAX_DAYS} days or fewer.")
            return
    else:
        start_d = end_d = st.session_state["selected_dates"][0]
        delta_days = 1

    no_moon = st.checkbox("No Moon", value=False)

    # Calculate Button
    calculate_button = st.button("Calculate")

    # Progress Bar Placeholder
    progress_placeholder = st.empty()
    progress_bar = progress_placeholder.progress(0)
    progress_text = st.empty()

    # Progress Console (Full Width)
    st.markdown("#### Progress Console")
    console_placeholder = st.empty()
    console_placeholder.text_area(
        "Progress Console",
        value=st.session_state.get("progress_console", ""),
        height=150,
        max_chars=None,
        key="progress_console_display",  # Ensure this key is unique and used only once
        disabled=True,
        help="Progress Console displaying calculation steps.",
        label_visibility="collapsed"
    )

    # Check day range
    if delta_days > MAX_DAYS:
        st.error(f"Please pick {MAX_DAYS} days or fewer.")
        return

    # Calculate Button Logic
    if calculate_button:
        if start_d > end_d:
            st.error("Start date must be <= end date.")
            return

        # Reset console
        st.session_state["progress_console"] = ""

        # Perform calculations with real-time updates
        daily_data = compute_day_details_step(
            lat_in, lon_in,
            start_d, end_d,
            no_moon
        )

        if not daily_data:
            st.warning("No data?? Possibly 0-day range.")
            return

        total_astro = sum(d["astro_dark_hours"] for d in daily_data)
        total_moonless = sum(d["moonless_hours"] for d in daily_data)

        # Display Results
        st.subheader("Results")
        cA, cB = st.columns(2)
        with cA:
            st.success(f"Total Astronomical Darkness: {total_astro:.2f} hrs")
        with cB:
            st.success(f"Moonless Darkness: {total_moonless:.2f} hrs")

        # Display Day-by-Day Breakdown
        st.subheader("Day-by-Day Breakdown")
        df = pd.DataFrame(daily_data)
        df = df.rename(columns={
            "date":"Date",
            "astro_dark_hours":"Astro (hrs)",
            "moonless_hours":"Moonless (hrs)",
            "dark_start":"Dark Start",
            "dark_end":"Dark End",
            "moon_rise":"Moonrise",
            "moon_set":"Moonset",
            "moon_phase":"Phase"
        })
        st.table(df)

    # Reintroduce the Map in an Expander
    with st.expander("View Map"):
        folium_map = folium.Map(location=[lat_in, lon_in], zoom_start=10)
        folium.Marker([lat_in, lon_in], popup="Location").add_to(folium_map)
        st_folium(folium_map, width=700, height=500)

if __name__ == "__main__":
    main()
