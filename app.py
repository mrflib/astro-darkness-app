# app.py - Minimal stepping approach (1-hour increments), up to 3 days
# -------------------------------------------------------------------

import streamlit as st
from datetime import date, datetime, timedelta
import pytz
from timezonefinder import TimezoneFinder
import pandas as pd
from skyfield.api import load, Topos

# -------------------------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Astronomical Darkness Calculator (1-hour stepping)",
    page_icon="🌑",
    layout="centered"
)

# -------------------------------------------------------------------
# INTRO
# -------------------------------------------------------------------
st.title("Astronomical Darkness (1-hour stepping, up to 3 days)")
st.write(
    "No external calls, no city geocoding, no IP location, just lat/lon.\n"
    "Stepping 1-hour increments for up to 3 days with debug prints.\n"
    "If this still fails on Streamlit Cloud, it's likely a platform/env issue."
)

# -------------------------------------------------------------------
# UTILS
# -------------------------------------------------------------------
def moon_phase_icon(phase_deg):
    """Return an emoji for the moon phase based on angle in [0..360]."""
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

# -------------------------------------------------------------------
# MAIN CALC: 1-hour stepping, 3 days max
# -------------------------------------------------------------------
@st.cache_data
def compute_day_details_1hr(lat, lon, start_date, end_date, no_moon):
    st.write("DEBUG: Entering compute_day_details_1hr()")

    ts = load.timescale()
    eph = load('de421.bsp()
    st.write("DEBUG: Loaded timescale & ephemeris")

    # Hard-coded 3-day limit
    max_days = 3

    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
    local_tz = pytz.timezone(tz_name)
    st.write(f"DEBUG: local_tz={tz_name}")

    # Build observer
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

    while current <= end_date and day_count < max_days:
        st.write(f"DEBUG: Day {day_count}, date={current}")
        local_mid = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)

        # Convert local->UTC
        start_aware = local_tz.localize(local_mid)
        end_aware = local_tz.localize(local_next)
        start_utc = start_aware.astimezone(pytz.utc)
        end_utc = end_aware.astimezone(pytz.utc)
        t_start = ts.from_datetime(start_utc)
        t_end = ts.from_datetime(end_utc)

        step_minutes = 60
        steps_per_day = 24
        st.write(f"DEBUG: steps_per_day={steps_per_day} for date={current}")

        # Build times
        times_list = []
        for i in range(steps_per_day+1):
            dt_utc = start_utc + timedelta(minutes=i*step_minutes)
            times_list.append(ts.from_datetime(dt_utc))

        # alt arrays
        sun_alts = []
        moon_alts = []
        for i in range(len(times_list)):
            alt_sun = sun_alt_deg(times_list[i])
            alt_moon = moon_alt_deg(times_list[i])
            sun_alts.append(alt_sun)
            moon_alts.append(alt_moon)

        st.write("DEBUG: built alt arrays, length=", len(sun_alts))

        # Summation
        astro_minutes = 0
        moonless_minutes = 0
        for i in range(len(times_list)-1):
            s_mid = (sun_alts[i] + sun_alts[i+1]) / 2.0
            m_mid = (moon_alts[i] + moon_alts[i+1]) / 2.0
            if s_mid < -18.0:
                astro_minutes += step_minutes
                if no_moon:
                    if m_mid < 0.0:
                        moonless_minutes += step_minutes
                else:
                    moonless_minutes += step_minutes
        astro_hrs = astro_minutes/60.0
        moonless_hrs = moonless_minutes/60.0
        st.write(f"DEBUG: date={current}, astro_hrs={astro_hrs:.2f}, moonless_hrs={moonless_hrs:.2f}")

        # Dark start/end
        start_dark_str = "-"
        end_dark_str = "-"
        found_dark = False
        for i in range(len(sun_alts)-1):
            if sun_alts[i] < -18 and not found_dark:
                # start
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                start_dark_str = dt_loc.strftime("%H:%M")
                found_dark = True
            if found_dark and sun_alts[i]>=-18:
                # end
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
        day_count += 1

    st.write("DEBUG: Exiting compute_day_details_1hr(), returning results.")
    return day_results

# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------
def main():
    st.subheader("Inputs: 3-day limit, lat/lon only (no city, no IP)")

    # Session defaults
    if "lat" not in st.session_state:
        st.session_state["lat"] = 31.6258
    if "lon" not in st.session_state:
        st.session_state["lon"] = -7.9892

    lat_in = st.number_input("Latitude", value=st.session_state["lat"], format="%.6f")
    lon_in = st.number_input("Longitude", value=st.session_state["lon"], format="%.6f")
    if abs(lat_in - st.session_state["lat"])>1e-9 or abs(lon_in - st.session_state["lon"])>1e-9:
        st.session_state["lat"] = lat_in
        st.session_state["lon"] = lon_in

    c1, c2 = st.columns([2,1])
    with c1:
        d_range = st.date_input("Date Range (3 days max)", [date(2025,10,15), date(2025,10,16)])
        if len(d_range)==1:
            start_d = d_range[0]
            end_d = d_range[0]
        else:
            start_d, end_d = d_range[0], d_range[-1]
    with c2:
        no_moon = st.checkbox("No Moon", value=False)

    delta_days = (end_d - start_d).days + 1
    if delta_days>3:
        st.error("Please pick 3 days or fewer.")
        return

    if st.button("Calculate"):
        if start_d> end_d:
            st.error("Start date must be <= end date.")
            return

        st.write("DEBUG: Starting calculation (1-hr stepping).")
        daily_data = compute_day_details_1hr(
            st.session_state["lat"],
            st.session_state["lon"],
            start_d,
            end_d,
            no_moon
        )
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
