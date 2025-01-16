# app.py - Full code with line references
# --------------------------------------------------

# (1) Imports
import streamlit as st                             # line 1
from datetime import date, datetime, timedelta     # line 2
import pytz                                        # line 3
from timezonefinder import TimezoneFinder          # line 4
import pandas as pd                                # line 5
from skyfield.api import load, Topos               # line 6
from skyfield.searchlib import find_discrete       # line 7
from geopy.geocoders import Nominatim              # line 8

# (2) Page config
st.set_page_config(                                # line 15
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="centered"
)

# (3) Intro text
st.title("Astronomical Darkness Calculator")       # line 23
st.write(
    "Debug version: 3-day limit, bigger step_days=1.0, with debug prints!"
)

# (4) Utility: geocode city
def geocode_place(place_name):                     # line 31
    geolocator = Nominatim(user_agent="astro_app")
    try:
        loc = geolocator.geocode(place_name)
        if loc:
            return (loc.latitude, loc.longitude)
    except:
        pass
    return None

# (5) Utility: reverse geocode lat/lon -> city name
def reverse_geocode(lat, lon):                     # line 41
    geolocator = Nominatim(user_agent="astro_app")
    try:
        loc = geolocator.reverse((lat, lon), language='en')
        if loc and loc.address:
            addr = loc.raw.get('address', {})
            guess = (
                addr.get('city')
                or addr.get('town')
                or addr.get('village')
                or loc.address
            )
            return guess
    except:
        pass
    return ""

# (6) Moon phase icon
def moon_phase_icon(phase_deg):                    # line 57
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

# (7) Cached day-details function, up to 3 days, with debug prints
@st.cache_data                                     # line 73
def compute_day_details(lat, lon, start_date, end_date, no_moon):
    st.write("DEBUG: Entering compute_day_details...")
    ts = load.timescale()
    eph = load('de421.bsp')
    st.write("DEBUG: Loaded timescale & ephemeris")

    max_days = 3  # limit to 3 days
    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
    local_tz = pytz.timezone(tz_name)
    st.write(f"DEBUG: local_tz = {tz_name}")

    # altitude functions with step_days
    def sun_alt_func(t):
        topos = Topos(latitude_degrees=lat, longitude_degrees=lon)
        observer = eph['Earth'] + topos
        alt, _, _ = observer.at(t).observe(eph['Sun']).apparent().altaz()
        return alt.degrees - (-18.0)
    sun_alt_func.step_days = 1.0  # bigger step => fewer computations

    def moon_alt_func(t):
        topos = Topos(latitude_degrees=lat, longitude_degrees=lon)
        observer = eph['Earth'] + topos
        alt, _, _ = observer.at(t).observe(eph['Moon']).apparent().altaz()
        return alt.degrees
    moon_alt_func.step_days = 1.0

    day_results = []
    day_count = 0
    current = start_date

    while current <= end_date and day_count < max_days:
        st.write(f"DEBUG: Starting day {day_count}, date={current}")
        # local midnight
        local_mid = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)

        start_aware = local_tz.localize(local_mid)
        end_aware = local_tz.localize(local_next)
        start_utc = start_aware.astimezone(pytz.utc)
        end_utc = end_aware.astimezone(pytz.utc)
        t_start = ts.from_datetime(start_utc)
        t_end = ts.from_datetime(end_utc)

        st.write("DEBUG: About to call find_discrete for Sun")
        sun_times, sun_values = find_discrete(t_start, t_end, sun_alt_func)
        st.write(f"DEBUG: sun_times len = {len(sun_times)}")

        st.write("DEBUG: About to call find_discrete for Moon")
        moon_times, moon_values = find_discrete(t_start, t_end, moon_alt_func)
        st.write(f"DEBUG: moon_times len = {len(moon_times)}")

        # Summation of astro darkness
        combined_sun = [t_start] + list(sun_times) + [t_end]
        astro_minutes = 0.0
        for i in range(len(combined_sun)-1):
            seg_a = combined_sun[i]
            seg_b = combined_sun[i+1]
            mid_t = seg_a.tt + 0.5*(seg_b.tt - seg_a.tt)
            mid_val = sun_alt_func(ts.tt_jd(mid_t))
            if mid_val < 0:
                length_days = seg_b.tt - seg_a.tt
                length_min = length_days * 24 * 60
                astro_minutes += length_min
        astro_hrs = astro_minutes/60.0
        st.write(f"DEBUG: astro_hrs = {astro_hrs:.2f} for {current}")

        if no_moon:
            st.write("DEBUG: Doing no_moon logic")
            all_times = sorted({t_start, t_end, *sun_times, *moon_times}, key=lambda x: x.tt)
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

        # Start/end darkness
        def alt_sign_sun(tt):
            return sun_alt_func(tt) < 0
        big_sun = [t_start] + list(sun_times) + [t_end]
        big_signs = [alt_sign_sun(x) for x in big_sun]
        start_dark_str = "-"
        end_dark_str = "-"
        for i in range(len(big_sun)-1):
            if not big_signs[i] and big_signs[i+1]:
                cross_t = big_sun[i+1]
                dt_loc = cross_t.utc_datetime().astimezone(local_tz)
                start_dark_str = dt_loc.strftime("%H:%M")
            if big_signs[i] and not big_signs[i+1]:
                cross_t = big_sun[i+1]
                dt_loc = cross_t.utc_datetime().astimezone(local_tz)
                end_dark_str = dt_loc.strftime("%H:%M")

        # Moon rise/set
        def alt_sign_moon(tt):
            return moon_alt_func(tt) >= 0
        big_moon = [t_start] + list(moon_times) + [t_end]
        big_msign = [alt_sign_moon(x) for x in big_moon]
        m_rise_str = "-"
        m_set_str = "-"
        for i in range(len(big_moon)-1):
            if not big_msign[i] and big_msign[i+1]:
                cross_t = big_moon[i+1]
                dt_loc = cross_t.utc_datetime().astimezone(local_tz)
                m_rise_str = dt_loc.strftime("%H:%M")
            if big_msign[i] and not big_msign[i+1]:
                cross_t = big_moon[i+1]
                dt_loc = cross_t.utc_datetime().astimezone(local_tz)
                m_set_str = dt_loc.strftime("%H:%M")

        # Moon phase at local noon
        local_noon = datetime(current.year, current.month, current.day, 12, 0, 0)
        local_noon_aware = local_tz.localize(local_noon)
        noon_utc = local_noon_aware.astimezone(pytz.utc)
        t_noon = ts.from_datetime(noon_utc)
        topos_noon = Topos(latitude_degrees=lat, longitude_degrees=lon)
        obs_noon = eph['Earth'] + topos_noon
        sun_ecl = obs_noon.at(t_noon).observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.at(t_noon).observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360

        # Store results
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

    st.write("DEBUG: Exiting compute_day_details with results.")
    return day_results

# (8) Main function
def main():                                        # line 271
    # Session defaults
    if "lat" not in st.session_state:
        st.session_state["lat"] = 31.6258
    if "lon" not in st.session_state:
        st.session_state["lon"] = -7.9892
    if "city" not in st.session_state:
        st.session_state["city"] = "Marrakech"

    st.subheader("Location & Date Range")

    # Row: city
    col_city1, col_city2 = st.columns([2,1])       # line 282
    with col_city1:
        city_input = st.text_input("City (optional)", value=st.session_state["city"])
    with col_city2:
        st.write("")  # alignment placeholder
        # No IP location to avoid external call - you can re-add if needed

    if city_input != st.session_state["city"]:
        st.session_state["city"] = city_input
        coords = geocode_place(city_input)
        if coords:
            st.session_state["lat"], st.session_state["lon"] = coords
        else:
            st.warning("City not found. Check spelling or specify lat/lon.")

    # Row: lat/lon
    row2c1, row2c2 = st.columns(2)
    with row2c1:
        new_lat = st.number_input("Latitude", value=st.session_state["lat"], format="%.6f")
    with row2c2:
        new_lon = st.number_input("Longitude", value=st.session_state["lon"], format="%.6f")

    if abs(new_lat - st.session_state["lat"])>1e-9 or abs(new_lon - st.session_state["lon"])>1e-9:
        st.session_state["lat"] = new_lat
        st.session_state["lon"] = new_lon
        # Optionally reverse geocode if you like
        guess_city = reverse_geocode(new_lat, new_lon)
        if guess_city:
            st.session_state["city"] = guess_city

    # Row: date range + no_moon
    row3c1, row3c2 = st.columns([2,1])
    with row3c1:
        d_range = st.date_input("Date Range (max 3 days)", [date(2025,10,15), date(2025,10,16)])
        if len(d_range)==1:
            start_d = d_range[0]
            end_d = d_range[0]
        else:
            start_d, end_d = d_range[0], d_range[-1]
    with row3c2:
        st.write("")  # alignment placeholder
        no_moon = st.checkbox("No Moon", value=False)

    # limited to 3 days
    st.write("DEBUG: Checking user date range selection")
    delta_days = (end_d - start_d).days + 1
    if delta_days>3:
        st.error("Please pick a range of 3 days or fewer.")
        return

    # Calculate
    if st.button("Calculate"):
        st.write("DEBUG: Starting calculation...")
        if start_d> end_d:
            st.error("Start date must be <= end date.")
            return

        daily_data = compute_day_details(
            st.session_state["lat"],
            st.session_state["lon"],
            start_d,
            end_d,
            no_moon
        )
        if not daily_data:
            st.warning("No data or maybe 0-day range.")
            return

        total_astro = sum(x["astro_dark_hours"] for x in daily_data)
        total_moonless = sum(x["moonless_hours"] for x in daily_data)

        st.write("---")
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
# ----------------------------------------------------------------
# End of app.py
#
# Key points:
# 1) Range limited to 3 days with explicit check (line ~169).
# 2) step_days=1.0 for both sun_alt_func and moon_alt_func.
# 3) Extra st.write("DEBUG: ...") statements to see logs progression.
# 4) IP location calls removed, so fewer external dependencies.
