# app.py - A flexible version with bullet toggling only
# -------------------------------------------------------------------

############################
# CONFIGURATION BLOCK
############################
MAX_DAYS = 30         # how many days to allow
STEP_MINUTES = 1      # how many minutes between each step (default 1)
USE_CITY_SEARCH = True # toggle city input on or off
DEBUG = True           # set to False if you want to hide debug prints
SHOW_BULLETS = True    # new toggle to show/hide the bullet points
############################
# END CONFIGURATION BLOCK
############################

import streamlit as st
from datetime import date, datetime, timedelta
import pytz
from timezonefinder import TimezoneFinder
import pandas as pd
from skyfield.api import load, Topos

# (1) PAGE CONFIG
st.set_page_config(
    page_title="Astronomical Darkness Calculator (Configurable)",
    page_icon="🌑",
    layout="centered"
)

# (2) INTRO
def maybe_show_bullets():
    """Show bullet points if SHOW_BULLETS=True."""
    if SHOW_BULLETS:
        st.write(f"- Up to **{MAX_DAYS} days**")
        st.write(f"- **{STEP_MINUTES}-minute** stepping")
        st.write(f"- City search is **{'ON' if USE_CITY_SEARCH else 'OFF'}**")
        st.write(f"- Debug prints: **{'YES' if DEBUG else 'NO'}**")

st.title("Astronomical Darkness Calculator (Configurable)")
maybe_show_bullets()  # Show bullet points if toggled on

# (3) UTILS
def debug_print(msg: str):
    """Helper to conditionally print debug statements."""
    if DEBUG:
        st.write(msg)

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

# If city search is ON, we import geopy and define geocode
if USE_CITY_SEARCH:
    from geopy.geocoders import Nominatim

    def geocode_place(place_name):
        # The only change: add a longer timeout to reduce "City not found" errors
        geolocator = Nominatim(user_agent="astro_app", timeout=10)
        try:
            loc = geolocator.geocode(place_name)
            if loc:
                return (loc.latitude, loc.longitude)
        except:
            pass
        return None
else:
    def geocode_place(place_name):
        # Dummy, does nothing if search is off
        return None

# (4) A CACHED day-details function
@st.cache_data
def compute_day_details(lat, lon, start_date, end_date, no_moon):
    debug_print("DEBUG: Entering compute_day_details")

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
        alt_moon, _, _ = app_moon.altaz()
        return alt_moon.degrees

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

        # Build times
        steps_per_day = (24*60)//STEP_MINUTES
        debug_print(f"DEBUG: steps_per_day={steps_per_day} for date={current}")
        times_list = []
        for i in range(steps_per_day+1):
            dt_utc = start_utc + timedelta(minutes=i*STEP_MINUTES)
            times_list.append(ts.from_datetime(dt_utc))

        sun_alts = []
        moon_alts = []
        for i in range(len(times_list)):
            alt_sun = sun_alt_deg(times_list[i])
            alt_moon = moon_alt_deg(times_list[i])
            sun_alts.append(alt_sun)
            moon_alts.append(alt_moon)

        debug_print(f"DEBUG: built alt arrays, length={len(sun_alts)}")

        # Summation
        astro_minutes = 0
        moonless_minutes = 0
        for i in range(len(times_list)-1):
            s_mid = (sun_alts[i] + sun_alts[i+1]) / 2.0
            m_mid = (moon_alts[i] + moon_alts[i+1]) / 2.0
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
            if prev_alt<0 and moon_alts[i]>=0 and m_rise_str=="-":
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                m_rise_str = dt_loc.strftime("%H:%M")
            if prev_alt>=0 and moon_alts[i]<0 and m_set_str=="-":
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
        day_count+=1

    debug_print("DEBUG: Exiting compute_day_details, returning results.")
    return day_results

def main():
    # We only remove the bullet points in the intro. Everything else is the same.
    # No bullet points or summary lines at the top.

    st.subheader("Input Lat/Lon (Optional City if USE_CITY_SEARCH=True)")

    lat_default = 31.6258
    lon_default = -7.9892

    if USE_CITY_SEARCH:
        city_input = st.text_input(
            "City Name (optional)", 
            value="Marrakech"  # default
        )
        if city_input:
            coords = geocode_place(city_input)
            if coords:
                lat_default, lon_default = coords
            else:
                st.warning("City not found. Check spelling or use lat/lon below.")

    lat_in = st.number_input("Latitude", value=lat_default, format="%.6f")
    lon_in = st.number_input("Longitude", value=lon_default, format="%.6f")

    d_range = st.date_input(f"Pick up to {MAX_DAYS} days", [date(2025,10,15), date(2025,10,16)])
    if len(d_range)==1:
        start_d = d_range[0]
        end_d = d_range[0]
    else:
        start_d, end_d = d_range[0], d_range[-1]

    delta_days = (end_d - start_d).days + 1
    if delta_days>MAX_DAYS:
        st.error(f"Please pick {MAX_DAYS} days or fewer.")
        return

    no_moon = st.checkbox("No Moon", value=False)

    if st.button("Calculate"):
        if start_d> end_d:
            st.error("Start date must be <= end date.")
            return

        st.write(f"DEBUG: Starting calc with {STEP_MINUTES}-min steps, up to {MAX_DAYS} days.")
        daily_data = compute_day_details(lat_in, lon_in, start_d, end_d, no_moon)
        if not daily_data:
            st.warning("No data?? Possibly 0-day range.")
            return

        total_astro = sum(d["astro_dark_hours"] for d in daily_data)
        total_moonless = sum(d["moonless_hours"] for d in daily_data)

        st.subheader("Results")
        cA, cB = st.columns(2)
        with cA:
            st.success(f"Total Astronomical Darkness: {total_astro:.2f} hrs")
        with cB:
            st.success(f"Moonless Darkness: {total_moonless:.2f} hrs")

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

if __name__ == "__main__":
    main()
