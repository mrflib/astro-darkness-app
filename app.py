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

# CHANGED: import from streamlit_date_picker
from streamlit_date_picker import date_range_picker, PickerType

########################################
# PAGE CONFIG + Custom CSS
########################################
st.set_page_config(
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="centered"
)

st.markdown("""
<style>
    /* ... your custom CSS as before ... */
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

# ... same geocode_city, reverse_geocode, find_dark_crossings, etc. ...

########################################
# Astro Calculation (unchanged)
########################################
def compute_day_details(lat, lon, start_date, end_date, moon_affect, step_minutes, progress_bar, token):
    # ... your existing code for load timescale, iterate days, etc. ...
    return day_results

########################################
# MAIN
########################################
def main():
    st.markdown("<h2>Astronomical Darkness Calculator</h2>", unsafe_allow_html=True)
    st.markdown("<h4>Find how many hours of true night...</h4>", unsafe_allow_html=True)

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
        # Two default days
        st.session_state["selected_dates"] = [date.today(), date.today() + timedelta(days=1)]
    if "last_click" not in st.session_state:
        st.session_state["last_click"] = None

    # Retrieve token
    LOCATIONIQ_TOKEN = st.secrets["locationiq"]["token"]

    # Inputs
    st.markdown("#### Inputs")
    input_cols = st.columns(3)
    with input_cols[0]:
        # City
        if USE_CITY_SEARCH:
            cval = st.text_input(
                "City (optional)",
                value=st.session_state["city"],
                help="Enter a city name..."
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
        # CHANGED: Use date_range_picker instead of st.date_input
        st.markdown("**Select Date Range**")

        # Provide a default range from st.session_state
        default_start = st.session_state["selected_dates"][0]
        default_end   = st.session_state["selected_dates"][1]
        # Convert them to datetime if needed
        default_start_dt = datetime(default_start.year, default_start.month, default_start.day)
        default_end_dt   = datetime(default_end.year,   default_end.month,   default_end.day)

        date_range_res = date_range_picker(
            picker_type=PickerType.date,   # pure date picking
            start=default_start_dt,        # set default start
            end=default_end_dt,            # set default end
            key="custom_date_range_picker"
        )
        if date_range_res:
            # The function returns a tuple (datetime_start, datetime_end)
            d_start, d_end = date_range_res
            # Convert to date objects
            st.session_state["selected_dates"] = [d_start.date(), d_end.date()]

    with input_cols[2]:
        # Step minutes as before
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
            help="This setting determines how precise..."
        )

    # Coordinates & Moon Influence
    st.markdown("#### Coordinates & Moon Influence")
    coord_cols = st.columns(3)
    with coord_cols[0]:
        lat_in = st.number_input(
            "Latitude",
            value=st.session_state["lat"],
            format="%.6f",
            min_value=-90.0,
            max_value=90.0,
            help="Latitude in decimal degrees."
        )
        if abs(lat_in - st.session_state["lat"]) > 1e-8:
            st.session_state["lat"] = lat_in

    with coord_cols[1]:
        lon_in = st.number_input(
            "Longitude",
            value=st.session_state["lon"],
            format="%.6f",
            min_value=-180.0,
            max_value=180.0,
            help="Longitude in decimal degrees."
        )
        if abs(lon_in - st.session_state["lon"]) > 1e-8:
            st.session_state["lon"] = lon_in

    with coord_cols[2]:
        moon_options = [
            "Include Moonlight",
            "Ignore Moonlight"
        ]
        moon_affect = st.selectbox(
            "Moon Influence",
            options=moon_options,
            index=0
        )

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
            # Validate coords
            if not (-90.0 <= clicked_lat <= 90.0):
                st.warning(f"Clicked latitude {clicked_lat} is out of bounds.")
            elif not (-180.0 <= clicked_lon <= 180.0):
                st.warning(f"Clicked longitude {clicked_lon} is out of bounds.")
            else:
                current_click = (clicked_lat, clicked_lon)
                if st.session_state["last_click"] != current_click:
                    st.session_state["lat"], st.session_state["lon"] = current_click
                    city = reverse_geocode(clicked_lat, clicked_lon, LOCATIONIQ_TOKEN)
                    if city:
                        st.session_state["city"] = city
                        st.success(f"Location updated to {city} ({clicked_lat:.4f}, {clicked_lon:.4f})")
                    else:
                        st.warning("City not found for the selected location.")
                    st.session_state["last_click"] = current_click

    # Calculate Button
    st.markdown("####")
    calculate_button = st.button("Calculate")

    # Progress placeholders
    progress_placeholder = st.empty()
    progress_bar = progress_placeholder.progress(0)
    progress_text = st.empty()

    # Console
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

    # Calculate
    if calculate_button:
        if start_d > end_d:
            st.error("Start date must be <= end date.")
            st.stop()

        if delta_days > MAX_DAYS:
            st.warning(f"Selected range exceeds {MAX_DAYS} days.")
            st.stop()

        st.session_state["progress_console"] = ""  # reset console
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
            st.warning("No data?? Possibly 0-day range.")
            st.stop()

        # Summaries
        total_astro = 0
        total_moonless = 0
        for d in daily_data:
            astro_parts = d["astro_dark_hours"].split()
            a_h, a_m = int(astro_parts[0]), int(astro_parts[2])

            moonless_parts = d["moonless_hours"].split()
            m_h, m_m = int(moonless_parts[0]), int(moonless_parts[2])

            total_astro += a_h * 60 + a_m
            total_moonless += m_h * 60 + m_m

        total_astro_hours = total_astro // 60
        total_astro_minutes = total_astro % 60
        total_moonless_hours = total_moonless // 60
        total_moonless_minutes = total_moonless % 60

        st.markdown("#### Results")
        if moon_affect == "Include Moonlight":
            rc = st.columns(2)
            with rc[0]:
                st.markdown(f"""
                <div class="result-box">
                    <div class="result-title">Total Astro Darkness</div>
                    <div class="result-value">{total_astro_hours} Hours {total_astro_minutes} Minutes</div>
                </div>
                """, unsafe_allow_html=True)
            with rc[1]:
                st.markdown(f"""
                <div class="result-box">
                    <div class="result-title">Moonless Astro Darkness</div>
                    <div class="result-value">{total_moonless_hours} Hours {total_moonless_minutes} Minutes</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            e1, c, e2 = st.columns([1,8,1])
            with c:
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
            "dark_end": "Dark End",
            "moon_rise": "Moonrise",
            "moon_set": "Moonset",
            "moon_phase": "Phase"
        }, inplace=True)
        df.reset_index(drop=True, inplace=True)
        html_table = df.to_html(index=False)
        st.markdown(html_table, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
