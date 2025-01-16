# app.py - Full code with line numbers in comments
# -----------------------------------------------------

# (1) Imports
import streamlit as st               # line 1
from datetime import date, datetime, timedelta  # line 2
import pytz                          # line 3
from timezonefinder import TimezoneFinder  # line 4
import pandas as pd                  # line 5
from skyfield.api import load, wgs84 # line 6
from skyfield.searchlib import find_discrete  # line 7
from geopy.geocoders import Nominatim  # line 8
import requests                      # line 9
import folium                        # line 10
from streamlit_folium import st_folium  # line 11

# (2) Page config - single column, dark theme from config.toml if you have it
st.set_page_config(                  # line 15
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="centered"
)

# (3) Intro text
st.title("Astronomical Darkness Calculator")    # line 23
st.write(                                       # line 24
    "Find how many hours of astro darkness you get in a given location "
    "for up to a two-week period, and how many of those hours include "
    "the Moon being up. Great for holiday planning!"
)

# (4) Utility: IP location
def get_ip_location():                          # line 31
    """Approx user location via ipapi.co."""
    try:
        r = requests.get("https://ipapi.co/json/")
        if r.status_code == 200:
            data = r.json()
            return (data.get("latitude"), data.get("longitude"))
    except:
        pass
    return (None, None)

# (5) Utility: geocode city
def geocode_place(place_name):                  # line 42
    geolocator = Nominatim(user_agent="astro_app")
    try:
        loc = geolocator.geocode(place_name)
        if loc:
            return (loc.latitude, loc.longitude)
    except:
        pass
    return None

# (6) Utility: reverse geocode lat/lon -> city name
def reverse_geocode(lat, lon):                  # line 52
    geolocator = Nominatim(user_agent="astro_app")
    try:
        loc = geolocator.reverse((lat, lon), language='en')
        if loc and loc.address:
            addr = loc.raw.get('address', {})
            guess = addr.get('city') or addr.get('town') or addr.get('village') or loc.address
            return guess
    except:
        pass
    return ""

# (7) Moon phase icon
def moon_phase_icon(phase_deg):                 # line 63
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

# (8) Cached day-details function using find_discrete
@st.cache_data                                # line 82
def compute_day_details(lat, lon, start_date, end_date, no_moon): 
    """
    Day-by-day astro dark times using find_discrete with step_days attribute.
    Up to 14 days.
    """
    # (8a) Setup
    max_days = 14                             # line 89
    ts = load.timescale()                     # line 90
    eph = load('de421.bsp')                   # line 91

    tf = TimezoneFinder()                     # line 93
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
    local_tz = pytz.timezone(tz_name)         # line 97

    day_results = []
    day_count = 0
    current = start_date

    # (8b) Altitude functions, with step_days
    def sun_alt_func(t):                      # line 105
        obs = wgs84.latlon(lat, lon).at(t)
        alt, _, _ = obs.observe(eph['Sun']).apparent().altaz()
        return alt.degrees - (-18.0)  # crossing zero means altitude = -18
    sun_alt_func.step_days = 0.5              # line 110

    def moon_alt_func(t):                     # line 112
        obs = wgs84.latlon(lat, lon).at(t)
        alt, _, _ = obs.observe(eph['Moon']).apparent().altaz()
        return alt.degrees  # crossing zero means altitude = 0
    moon_alt_func.step_days = 0.5             # line 116

    # (8c) For each day, find darkness intervals
    while current <= end_date and day_count < max_days:
        # local midnight -> next midnight
        local_mid = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)

        # convert local->UTC
        start_aware = local_tz.localize(local_mid)
        end_aware = local_tz.localize(local_next)
        start_utc = start_aware.astimezone(pytz.utc)
        end_utc = end_aware.astimezone(pytz.utc)

        t_start = ts.from_datetime(start_utc)
        t_end = ts.from_datetime(end_utc)

        # (8d) Sun crossing -18 deg
        sun_times, sun_values = find_discrete(t_start, t_end, sun_alt_func)  # line 133
        # negative => alt < -18, positive => alt > -18

        # (8e) Moon crossing horizon
        moon_times, moon_values = find_discrete(t_start, t_end, moon_alt_func)  # line 137
        # negative => below horizon, positive => above horizon

        # (8f) Summation of astro darkness
        # Build combined timeline for sun
        combined_sun = [t_start] + list(sun_times) + [t_end]
        astro_minutes = 0.0
        for i in range(len(combined_sun)-1):
            seg_a = combined_sun[i]
            seg_b = combined_sun[i+1]
            # mid point
            mid_tt = seg_a.tt + 0.5 * (seg_b.tt - seg_a.tt)
            val_mid = sun_alt_func(ts.tt_jd(mid_tt))
            if val_mid < 0:
                length_days = seg_b.tt - seg_a.tt
                length_min = length_days * 1440.0
                astro_minutes += length_min
        astro_hrs = astro_minutes/60.0

        # (8g) If no_moon => exclude intervals when moon is up
        if no_moon:
            all_times = sorted(set([t_start, t_end] + list(sun_times) + list(moon_times)), key=lambda x: x.tt)
            moonless_minutes = 0.0
            for i in range(len(all_times)-1):
                seg_a = all_times[i]
                seg_b = all_times[i+1]
                mid_tt = seg_a.tt + 0.5 * (seg_b.tt - seg_a.tt)
                val_sun = sun_alt_func(ts.tt_jd(mid_tt))
                val_moon = moon_alt_func(ts.tt_jd(mid_tt))
                if val_sun < 0 and val_moon < 0:
                    length_days = seg_b.tt - seg_a.tt
                    length_min = length_days * 1440.0
                    moonless_minutes += length_min
            moonless_hrs = moonless_minutes/60.0
        else:
            moonless_hrs = astro_hrs

        # (8h) Start/end of darkness in local time
        def alt_sign_sun(t): 
            return (sun_alt_func(t) < 0)
        big_sun = [t_start] + list(sun_times) + [t_end]
        big_v = [alt_sign_sun(tt) for tt in big_sun]

        start_dark_str = "-"
        end_dark_str = "-"
        for i in range(len(big_sun)-1):
            if not big_v[i] and big_v[i+1]:
                # start crossing
                cross_t = big_sun[i+1]
                dt_loc = cross_t.utc_datetime().astimezone(local_tz)
                start_dark_str = dt_loc.strftime("%H:%M")
            if big_v[i] and not big_v[i+1]:
                # end crossing
                cross_t = big_sun[i+1]
                dt_loc = cross_t.utc_datetime().astimezone(local_tz)
                end_dark_str = dt_loc.strftime("%H:%M")

        # (8i) Moon rise/set in local time
        def alt_sign_moon(t):
            return (moon_alt_func(t) >= 0)  # True => above horizon
        big_moon = [t_start] + list(moon_times) + [t_end]
        big_mv = [alt_sign_moon(tt) for tt in big_moon]
        m_rise_str = "-"
        m_set_str = "-"
        for i in range(len(big_moon)-1):
            if not big_mv[i] and big_mv[i+1]:
                # below->above => rise
                cross_t = big_moon[i+1]
                dt_loc = cross_t.utc_datetime().astimezone(local_tz)
                m_rise_str = dt_loc.strftime("%H:%M")
            if big_mv[i] and not big_mv[i+1]:
                # above->below => set
                cross_t = big_moon[i+1]
                dt_loc = cross_t.utc_datetime().astimezone(local_tz)
                m_set_str = dt_loc.strftime("%H:%M")

        # (8j) Moon phase at local noon
        local_noon = datetime(current.year, current.month, current.day, 12, 0, 0)
        local_noon_aware = local_tz.localize(local_noon)
        noon_utc = local_noon_aware.astimezone(pytz.utc)
        t_noon = ts.from_datetime(noon_utc)

        obs_noon = wgs84.latlon(lat, lon).at(t_noon)
        sun_ecl = obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360

        # (8k) Append
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

    return day_results

# (9) Main streamlit function
def main():                                    # line 226
    # Session defaults
    if "lat" not in st.session_state:
        st.session_state["lat"] = 31.6258
    if "lon" not in st.session_state:
        st.session_state["lon"] = -7.9892
    if "city" not in st.session_state:
        st.session_state["city"] = "Marrakech"

    st.subheader("Location & Date Range")

    # Row: city + IP
    row1_col1, row1_col2 = st.columns([2,1])   # line 238
    with row1_col1:
        city_input = st.text_input("City (optional)", value=st.session_state["city"])
    with row1_col2:
        st.write("")  # to align button
        if st.button("Use IP Location"):
            ip_lat, ip_lon = get_ip_location()
            if ip_lat and ip_lon:
                st.session_state["lat"] = ip_lat
                st.session_state["lon"] = ip_lon
                found_city = reverse_geocode(ip_lat, ip_lon)
                if found_city:
                    st.session_state["city"] = found_city
                st.success(f"Set lat={ip_lat:.4f}, lon={ip_lon:.4f}")
            else:
                st.warning("No IP location found.")

    if city_input != st.session_state["city"]:
        st.session_state["city"] = city_input
        coords = geocode_place(city_input)
        if coords:
            st.session_state["lat"], st.session_state["lon"] = coords
        else:
            st.warning("City not found. Check spelling or use lat/lon.")

    # Row: lat/lon
    row2_col1, row2_col2 = st.columns(2)       # line 265
    with row2_col1:
        new_lat = st.number_input("Latitude", value=st.session_state["lat"], format="%.6f")
    with row2_col2:
        new_lon = st.number_input("Longitude", value=st.session_state["lon"], format="%.6f")

    if abs(new_lat - st.session_state["lat"])>1e-9 or abs(new_lon - st.session_state["lon"])>1e-9:
        st.session_state["lat"] = new_lat
        st.session_state["lon"] = new_lon
        ccity = reverse_geocode(new_lat, new_lon)
        if ccity:
            st.session_state["city"] = ccity

    # row: date range + no moon
    row3_col1, row3_col2 = st.columns([2,1])   # line 279
    with row3_col1:
        d_range = st.date_input("Date Range (up to 14 days)", [date(2025,10,15), date(2025,10,22)])
        if len(d_range) == 1:
            start_d = d_range[0]
            end_d = d_range[0]
        else:
            start_d, end_d = d_range[0], d_range[-1]
    with row3_col2:
        st.write("")  # align checkbox
        no_moon = st.checkbox("No Moon", value=False)

    # optional map
    with st.expander("Pick on Map (optional)"):
        st.write("Click location on map to set lat/lon:")
        map_loc = [st.session_state["lat"], st.session_state["lon"]]
        fol_map = folium.Map(location=map_loc, zoom_start=5)
        folium.TileLayer("OpenStreetMap").add_to(fol_map)
        fol_map.add_child(folium.LatLngPopup())
        map_data = st_folium(fol_map, width=600, height=400)
        if map_data and map_data["last_clicked"]:
            clat = map_data["last_clicked"]["lat"]
            clng = map_data["last_clicked"]["lng"]
            st.session_state["lat"] = clat
            st.session_state["lon"] = clng
            ccity2 = reverse_geocode(clat, clng)
            if ccity2:
                st.session_state["city"] = ccity2
            st.info(f"Selected lat={clat:.4f}, lon={clng:.4f}")

    # Calculate
    if st.button("Calculate"):                 # line 306
        if start_d > end_d:
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
            st.warning("No data (maybe over 14 days?).")
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

# (10) Run main
if __name__ == "__main__":                    # line 346
    main()                                     # line 347

# -----------------------------------------------------
# End of app.py
#
# Key lines changed from your code:
# (a) We added sun_alt_func.step_days = 0.5 and moon_alt_func.step_days = 0.5
#     around lines 110 and 116.
# (b) The rest is the same layout you had previously.
# (c) This ensures "find_discrete" won't error with "missing 'step_days' attribute."
# -----------------------------------------------------
