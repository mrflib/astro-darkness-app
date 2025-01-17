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

# We add custom CSS so:
# 1) The "Calculate" button is #218838 for all states
# 2) The progress bar uses #218838
# 3) Attempt to reduce the progress bar's default height 
#    (not 100% guaranteed to match the button on all setups).
st.markdown(r"""
<style>
/* Button normal, hover, active => #218838 */
.stButton > button {
    background-color: #218838 !important;
    border-color: #1e7e34 !important;
    color: white !important;
    height: 38px !important;      /* Force button height (approx) */
    margin-top: 0px !important;
}
/* Keep the button the same color on hover/active. */
.stButton > button:hover:not(:disabled),
.stButton > button:focus:not(:disabled),
.stButton > button:active:not(:disabled) {
    background-color: #218838 !important;
    border-color: #1e7e34 !important;
    color: white !important;
}

/* Force progress bar to be the same "height" as button, approx */
div[data-testid="stProgressBar"] div[role="progressbar"] {
    height: 38px !important;    /* same as button's forced height */
    margin-top: 0px !important;
}
/* Also color the bar #218838 */
div[role='progressbar'] div {
    background-color: #218838 !important;
}

/* Remove default form styling. */
div[data-testid="stForm"] {
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
}

/* Slightly smaller radius for .result-box */
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
    # ... same as before ...
    pass

def reverse_geocode(lat, lon, token):
    """(lat, lon)->city from LocationIQ /v1/reverse. Returns None if not found."""
    # ... same as before ...
    pass


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
    """Example day-by-day loop with partial progress updates."""
    from skyfield.api import load, Topos
    ts = load.timescale()
    eph = load('de421.bsp')
    observer = eph['Earth'] + Topos(latitude_degrees=lat, longitude_degrees=lon)

    # etc. ...
    pass


########################################
# MAIN
########################################
def main():
    st.title("Astronomical Darkness Calculator (Night-Labeled)")

    # ... same layout code for city, lat/lon, map as before ...
    # ... map logic also the same ...
    
    st.markdown("### Calculate Darkness")
    with st.form("calc_form"):
        row2 = st.columns(3)
        with row2[0]:
            dval = st.date_input(...)
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
                index=2,
                help=thr_tooltip
            )
            twilight_threshold = threshold_opts[thr_label]
        with row2[2]:
            step_opts = ["1","2","5","10","15","30"]
            step_str = st.selectbox("Time Step (Mins)", step_opts, index=0)
            step_minutes = int(step_str)

        # Now place button & progress bar in the same row.
        # We'll use st.columns => first column is button, second is bar
        row_btn = st.columns([1,4])  # left: narrow for button, right: wide for bar
        with row_btn[0]:
            calc_btn = st.form_submit_button("Calculate")
        with row_btn[1]:
            # placeholder for progress bar
            pbar_placeholder = st.empty()

    # If user pressed "Calculate"
    if calc_btn:
        # parse date range, etc ...
        # Check day_count, etc ...
        
        st.session_state["progress_console"] = ""
        debug_print("Starting calculations...")

        # create an actual progress bar in that placeholder
        progress_bar = pbar_placeholder.progress(0)

        nights_data = compute_night_details(
            # pass lat, lon, start_d, end_d, etc...
            pbar=progress_bar  # pass the bar object
        )

        # Summation, show results, etc ...
        # Also show the console text_area
        

if __name__ == "__main__":
    main()
