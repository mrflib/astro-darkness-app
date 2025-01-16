############################
# app.py (Discrete Approach)
############################

########## CONFIGURATION BLOCK ##########
MAX_DAYS = 30         # how many days to allow (default 30)
STEP_DAYS = 60  # ~1 minute in fraction of a day if we want "1-min stepping" 
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
from skyfield.searchlib import find_discrete

if USE_CITY_SEARCH:
    from geopy.geocoders import Nominatim

# For the map expander
import folium
from streamlit_folium import st_folium

##################################
# PAGE CONFIG
##################################
st.set_page_config(
    page_title="Astronomical Darkness Calculator (Discrete)",
    page_icon="🌑",
    layout="centered"
)

##################################
# Optional bullet points at top
##################################
def maybe_show_bullets():
    if SHOW_BULLETS:
        st.write(f"- Up to {MAX_DAYS} days")
        st.write(f"- Discrete approach with ~1-minute stepping (`step_days = {STEP_DAYS}`)")
        st.write(f"- City search is {'ON' if USE_CITY_SEARCH else 'OFF'}")
        st.write(f"- Debug prints: {'YES' if DEBUG else 'NO'}")

##################################
# Debug printing
##################################
def debug_print(msg: str):
    if DEBUG:
        st.write(msg)

##################################
# Optionally geocode city
##################################
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

##################################
# Moon phase icon
##################################
def moon_phase_icon(angle_deg):
    x = angle_deg % 360
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

##################################
# Discrete-based astro darkness
##################################
@st.cache_data
def compute_day_details_discrete(lat, lon, start_date, end_date, no_moon):
    debug_print("DEBUG: Entering compute_day_details_discrete...")

    ts = load.timescale()
    eph = load('de421.bsp')
    debug_print("DEBUG: Loaded timescale & ephemeris")

    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
    local_tz = pytz.timezone(tz_name)
    debug_print(f"DEBUG: local_tz={tz_name}")

    day_results = []
    day_count = 0
    current = start_date

    # We'll define functions for sun alt crossing -18 & moon alt crossing 0
    def sun_alt_func(t):
        topos = Topos(latitude_degrees=lat, longitude_degrees=lon)
        observer = eph['Earth'] + topos
        alt, _, _ = observer.at(t).observe(eph['Sun']).apparent().altaz()
        return alt.degrees - (-18.0)
    sun_alt_func.step_days = STEP_DAYS

    def moon_alt_func(t):
        topos = Topos(latitude_degrees=lat, longitude_degrees=lon)
        observer = eph['Earth'] + topos
        alt, _, _ = observer.at(t).observe(eph['Moon']).apparent().altaz()
        return alt.degrees
    moon_alt_func.step_days = STEP_DAYS

    # We allow up to MAX_DAYS
    while current <= end_date and day_count < MAX_DAYS:
        debug_print(f"DEBUG: day {day_count}, date={current}")
        local_mid = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)

        start_aware = local_tz.localize(local_mid)
        end_aware = local_tz.localize(local_next)
        start_utc = start_aware.astimezone(pytz.utc)
        end_utc = end_aware.astimezone(pytz.utc)
        ts_start = ts.from_datetime(start_utc)
        ts_end = ts.from_datetime(end_utc)

        debug_print("DEBUG: about to call find_discrete for Sun")
        sun_times, sun_values = find_discrete(ts_start, ts_end, sun_alt_func)
        debug_print(f"DEBUG: find_discrete for Sun gave {len(sun_times)} crossing points")

        debug_print("DEBUG: about to call find_discrete for Moon")
        moon_times, moon_values = find_discrete(ts_start, ts_end, moon_alt_func)
        debug_print(f"DEBUG: find_discrete for Moon gave {len(moon_times)} crossing points")

        # Summation approach
        combined_sun = [ts_start] + list(sun_times) + [ts_end]
        astro_minutes = 0.0
        for i in range(len(combined_sun)-1):
            seg_a = combined_sun[i]
            seg_b = combined_sun[i+1]
            mid_t = seg_a.tt + 0.5*(seg_b.tt - seg_a.tt)
            val_mid = sun_alt_func(ts.tt_jd(mid_t))
            if val_mid < 0:
                length_days = seg_b.tt - seg_a.tt
                length_min = length_days*24*60
                astro_minutes += length_min
        astro_hrs = astro_minutes/60.0

        # no_moon logic
        if no_moon:
            debug_print("DEBUG: Doing no_moon logic")
            all_times = sorted({ts_start, ts_end, *sun_times, *moon_times}, key=lambda x: x.tt)
            moonless_minutes = 0.0
            for i in range(len(all_times)-1):
                seg_a = all_times[i]
                seg_b = all_times[i+1]
                mid_tt = seg_a.tt + 0.5*(seg_b.tt - seg_a.tt)
                s_val = sun_alt_func(ts.tt_jd(mid_tt))
                m_val = moon_alt_func(ts.tt_jd(mid_tt))
                if s_val < 0 and m_val < 0:
                    length_days = seg_b.tt - seg_a.tt
                    length_min = length_days*24*60
                    moonless_minutes += length_min
            moonless_hrs = moonless_minutes/60.0
        else:
            moonless_hrs = astro_hrs

        debug_print(f"DEBUG: date={current}, astro_hrs={astro_hrs:.2f}, moonless_hrs={moonless_hrs:.2f}")

        # Start/end darkness
        def alt_sign_sun(t):
            return (sun_alt_func(t) < 0)
        big_sun = [ts_start] + list(sun_times) + [ts_end]
        big_v = [alt_sign_sun(tt) for tt in big_sun]
        start_dark_str = "-"
        end_dark_str = "-"
        # We keep the same approach
        found_dark = False
        for i in range(len(big_sun)-1):
            if not big_v[i] and big_v[i+1]:
                cross_t = big_sun[i+1]
                dt_loc = cross_t.utc_datetime().astimezone(local_tz)
                start_dark_str = dt_loc.strftime("%H:%M")
            if big_v[i] and not big_v[i+1]:
                cross_t = big_sun[i+1]
                dt_loc = cross_t.utc_datetime().astimezone(local_tz)
                end_dark_str = dt_loc.strftime("%H:%M")

        # Moon rise/set
        def alt_sign_moon(t):
            return (moon_alt_func(t) >= 0)
        big_moon = [ts_start] + list(moon_times) + [ts_end]
        big_mv = [alt_sign_moon(tt) for tt in big_moon]
        m_rise_str = "-"
        m_set_str = "-"
        for i in range(len(big_moon)-1):
            if not big_mv[i] and big_mv[i+1]:
                cross_t = big_moon[i+1]
                dt_loc = cross_t.utc_datetime().astimezone(local_tz)
                m_rise_str = dt_loc.strftime("%H:%M")
            if big_mv[i] and not big_mv[i+1]:
                cross_t = big_moon[i+1]
                dt_loc = cross_t.utc_datetime().astimezone(local_tz)
                m_set_str = dt_loc.strftime("%H:%M")

        # Moon phase
        local_noon = datetime(current.year, current.month, current.day, 12, 0, 0)
        local_noon_aware = local_tz.localize(local_noon)
        noon_utc = local_noon_aware.astimezone(pytz.utc)
        t_noon = ts.from_datetime(noon_utc)
        topos_noon = Topos(latitude_degrees=lat, longitude_degrees=lon)
        obs_noon = eph['Earth'] + topos_noon
        sun_ecl = obs_noon.at(t_noon).observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.at(t_noon).observe(eph['Moon']).apparent().ecliptic_latlon()
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

    debug_print("DEBUG: Exiting compute_day_details_discrete")
    return day_results

##################################
# MAIN
##################################
def main():
    maybe_show_bullets()

    st.subheader("Location & Date Range")

    # Single row for city + date
    row1_col1, row1_col2 = st.columns(2)
    # By default, lat & lon
    lat_default = 31.6258
    lon_default = -7.9892

    with row1_col1:
        if USE_CITY_SEARCH:
            city_input = st.text_input("City (optional)", "Marrakech")
            if city_input:
                coords = geocode_place(city_input)
                if coords:
                    lat_default, lon_default = coords
                else:
                    st.warning("City not found. Check spelling or use lat/lon below.")
        else:
            st.write("City search is OFF")

    with row1_col2:
        d_range = st.date_input("Select up to 30 days", [date(2025,10,15), date(2025,10,16)])
        if len(d_range)==1:
            start_d = d_range[0]
            end_d = d_range[0]
        else:
            start_d, end_d = d_range[0], d_range[-1]

    # Single row for lat/lon
    row2_col1, row2_col2 = st.columns(2)
    with row2_col1:
        lat_in = st.number_input("Latitude", value=lat_default, format="%.6f")
    with row2_col2:
        lon_in = st.number_input("Longitude", value=lon_default, format="%.6f")

    # Map in an expander
    with st.expander("Pick on Map (optional)"):
        st.write("Click on the map to set lat/lon:")
        map_loc = [lat_in, lon_in]
        fol_map = folium.Map(location=map_loc, zoom_start=5)
        folium.TileLayer("OpenStreetMap").add_to(fol_map)
        fol_map.add_child(folium.LatLngPopup())
        map_data = st_folium(fol_map, width=600, height=400)
        if map_data and map_data["last_clicked"]:
            clat = map_data["last_clicked"]["lat"]
            clng = map_data["last_clicked"]["lng"]
            lat_in, lon_in = clat, clng
            st.info(f"Selected lat={clat:.4f}, lon={clng:.4f}")

    # Limit days
    delta_days = (end_d - start_d).days + 1
    if delta_days>MAX_DAYS:
        st.error(f"Please pick {MAX_DAYS} days or fewer.")
        return

    no_moon = st.checkbox("No Moon", value=False)

    if st.button("Calculate"):
        if start_d> end_d:
            st.error("Start date must be <= end date.")
            return

        st.write(f"DEBUG: Starting discrete calc with step_days={STEP_DAYS}, up to {MAX_DAYS} days.")
        daily_data = compute_day_details_discrete(
            lat_in, lon_in, start_d, end_d, no_moon
        )
        if not daily_data:
            st.warning("No data (maybe 0-day range?).")
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
