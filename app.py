import streamlit as st
from datetime import date, datetime, timedelta
import pytz
from timezonefinder import TimezoneFinder
import pandas as pd
from skyfield.api import load, wgs84
from skyfield.searchlib import find_discrete
from geopy.geocoders import Nominatim
import requests
import folium
from streamlit_folium import st_folium

# --------------------------------------------------
# PAGE CONFIG: Single column, center layout
# --------------------------------------------------
st.set_page_config(
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="centered"
)

# --------------------------------------------------
# INTRO
# --------------------------------------------------
st.title("Astronomical Darkness Calculator")
st.write(
    "Find how many hours of astro darkness you get in a given location "
    "for up to a two-week period, and how many of those hours include "
    "the Moon being up. Great for holiday planning!"
)

# --------------------------------------------------
# GEOLOCATION UTILS
# --------------------------------------------------
def get_ip_location():
    """Approx user location by IP (ipapi.co)."""
    try:
        r = requests.get("https://ipapi.co/json/")
        if r.status_code == 200:
            data = r.json()
            return (data.get("latitude"), data.get("longitude"))
    except:
        pass
    return (None, None)

def geocode_place(place_name):
    """City name -> (lat, lon)."""
    geolocator = Nominatim(user_agent="astro_app")
    try:
        loc = geolocator.geocode(place_name)
        if loc:
            return (loc.latitude, loc.longitude)
    except:
        pass
    return None

def reverse_geocode(lat, lon):
    """(lat, lon) -> city name (approx)."""
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

# --------------------------------------------------
# MOON PHASE ICON (optional)
# --------------------------------------------------
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

# --------------------------------------------------
# ASTRONOMY LOGIC with find_discrete
# --------------------------------------------------
@st.cache_data
def compute_day_details(
    lat, lon, start_date, end_date, no_moon
):
    """
    Day-by-day astro dark times using Skyfield's find_discrete for:
      - Sun altitude crossing -18
      - Moon altitude crossing 0
    in local time. Return up to 14 days of results.
    """
    # Up to 14 days
    max_days = 14
    # Load ephemeris
    ts = load.timescale()
    eph = load('de421.bsp')

    # Timezone
    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
    local_tz = pytz.timezone(tz_name)

    # Build observer
    # For easier approach: use wgs84.latlon
    # then 'observer = wgs84.latlon(lat, lon).at(t)'
    # Or do a direct Topos. We'll do wgs84 here for demonstration.
    day_results = []
    day_count = 0
    current = start_date

    # We'll define functions for find_discrete
    def sun_alt_func(t):
        # altitude of sun minus -18 deg
        observer = wgs84.latlon(lat, lon).at(t)
        alt, _, _ = observer.observe(eph['Sun']).apparent().altaz()
        return alt.degrees - (-18.0)

    def moon_alt_func(t):
        observer = wgs84.latlon(lat, lon).at(t)
        alt, _, _ = observer.observe(eph['Moon']).apparent().altaz()
        return alt.degrees  # difference from 0

    while current <= end_date and day_count < max_days:
        # local day start: local midnight
        local_mid = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)

        # Convert local day start/end to UTC for skyfield
        start_local_aware = local_tz.localize(local_mid)
        end_local_aware = local_tz.localize(local_next)

        start_utc = start_local_aware.astimezone(pytz.utc)
        end_utc = end_local_aware.astimezone(pytz.utc)

        t_start = ts.from_datetime(start_utc)
        t_end = ts.from_datetime(end_utc)

        # 1) find times sun crosses -18 using find_discrete
        sun_times, sun_values = find_discrete(t_start, t_end, sun_alt_func)
        # sun_values is sign of alt_func: negative => altitude < -18, positive => altitude > -18
        # crossing points where it changes sign => start or end of darkness

        # 2) find times moon crosses horizon
        moon_times, moon_values = find_discrete(t_start, t_end, moon_alt_func)
        # negative => below horizon, positive => above horizon

        # We'll record total astro darkness & moonless darkness
        # We'll step between the sign changes in sun_values. 
        # We can parse intervals where sun_values is negative => astro dark
        # Then check if moon is above horizon in that interval if no_moon==True

        # First, let's gather intervals of astro darkness
        # We'll do a piecewise approach: find intervals in [t_start..t_end]
        # where sun_alt < -18. Then sum lengths.
        intervals_astro = []
        # We include start_t = t_start, end_t = t_end in the search results
        # We'll build a timeline of times + signs.

        # Build timeline for sun
        combined_times = [t_start] + list(sun_times) + [t_end]
        combined_signs = []
        prev_sign = (sun_alt_func(t_start) < 0)  # is it negative at start?
        for i in range(len(sun_times)):
            combined_signs.append(sun_values[i] < 0)
        # That leaves us with len(sun_times) sign states, but we want them interleaved with start/end
        # We'll do a simpler approach:

        intervals_astro_minutes = 0
        # We'll iterate each segment
        for i in range(len(combined_times)-1):
            seg_start = combined_times[i]
            seg_end = combined_times[i+1]
            # Evaluate sign in the middle
            mid_t = seg_start.tt + (seg_end.tt - seg_start.tt)/2
            mid_alt = sun_alt_func(ts.tt_jd(mid_t))
            sun_neg = (mid_alt < 0)  # is < -18 ?

            # If it's negative => astro dark in entire segment
            if sun_neg:
                # add length in minutes
                length_days = seg_end.tt - seg_start.tt
                length_min = length_days * 24 * 60
                intervals_astro_minutes += length_min

        # Now intervals_astro_minutes is total astro darkness in minutes
        astro_hrs = intervals_astro_minutes / 60.0

        # For moonless: if no_moon is false, then total= astro_hrs
        # If no_moon is true => subtract intervals where moon is up from astro intervals
        # We'll do similarly for the moon:
        if no_moon:
            # We want intervals sun < -18 AND moon < 0
            # We'll do a finer approach: step each discrete sign change from BOTH sun+moon
            # Merge them. 
            # For brevity, let's do the same sign approach but for "sun_neg AND moon_neg"
            all_times = sorted(set([t_start, t_end] + list(sun_times) + list(moon_times)), key=lambda x: x.tt)
            moonless_minutes = 0.0
            for i in range(len(all_times)-1):
                seg_a = all_times[i]
                seg_b = all_times[i+1]
                mid_tt = seg_a.tt + (seg_b.tt - seg_a.tt)/2
                s_alt = sun_alt_func(ts.tt_jd(mid_tt))
                m_alt = moon_alt_func(ts.tt_jd(mid_tt))
                if s_alt < 0 and m_alt < 0:
                    # fully in astro darkness + moon below horizon
                    length_days = seg_b.tt - seg_a.tt
                    length_min = length_days * 24*60
                    moonless_minutes += length_min
            moonless_hrs = moonless_minutes/60.0
        else:
            moonless_hrs = astro_hrs

        # Now let's find "start_of_astro_dark" => first crossing from alt> -18 to alt< -18
        # end_of_astro_dark => crossing from alt< -18 to alt> -18
        # We'll store them as times
        # We'll do a simpler approach: see if there's a sign change from positive->negative => start
        # negative->positive => end, in chronological order
        def alt_sign(t):
            return sun_alt_func(t) < 0
        start_dark_local = "-"
        end_dark_local = "-"

        # The array: [ t_start, crossing1, crossing2, ..., t_end ]
        bigT = [t_start] + list(sun_times) + [t_end]
        bigV = [alt_sign(tt) for tt in bigT]
        # parse
        for i in range(len(bigT)-1):
            if not bigV[i] and bigV[i+1]:
                # positive -> negative => start
                cross_t = bigT[i+1]
                # store local time
                dt_utc = cross_t.utc_datetime()
                dt_local = dt_utc.astimezone(local_tz)
                start_dark_local = dt_local.strftime("%H:%M")
            if bigV[i] and not bigV[i+1]:
                # negative -> positive => end
                cross_t = bigT[i+1]
                dt_utc = cross_t.utc_datetime()
                dt_local = dt_utc.astimezone(local_tz)
                end_dark_local = dt_local.strftime("%H:%M")

        # Moonrise / moonset
        # We'll do similarly with 'moon_alt_func' sign changes
        # negative->positive => rise, positive->negative => set
        def moon_sign(t):
            return (moon_alt_func(t) >= 0)  # True => above horizon
        bigM = [t_start] + list(moon_times) + [t_end]
        bigMv = [moon_sign(tt) for tt in bigM]
        m_rise_local = "-"
        m_set_local = "-"
        for i in range(len(bigM)-1):
            if not bigMv[i] and bigMv[i+1]:
                # below->above => rise
                cross_t = bigM[i+1]
                dt_utc = cross_t.utc_datetime()
                dt_local = dt_utc.astimezone(local_tz)
                m_rise_local = dt_local.strftime("%H:%M")
            if bigMv[i] and not bigMv[i+1]:
                # above->below => set
                cross_t = bigM[i+1]
                dt_utc = cross_t.utc_datetime()
                dt_local = dt_utc.astimezone(local_tz)
                m_set_local = dt_local.strftime("%H:%M")

        # Moon phase => check local noon
        local_noon = datetime(current.year, current.month, current.day, 12, 0, 0)
        local_noon_aware = local_tz.localize(local_noon)
        noon_utc = local_noon_aware.astimezone(pytz.utc)
        t_noon = ts.from_datetime(noon_utc)
        # compute angle
        observer = wgs84.latlon(lat, lon).at(t_noon)
        sun_alt, _, _ = observer.observe(eph['Sun']).apparent().altaz()
        moon_alt, _, _ = observer.observe(eph['Moon']).apparent().altaz()
        sun_ecl = observer.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = observer.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360

        day_results.append({
            "date": current.strftime("%Y-%m-%d"),
            "astro_dark_hours": round(astro_hrs, 2),
            "moonless_hours": round(moonless_hrs, 2),
            "dark_start": start_dark_local,
            "dark_end": end_dark_local,
            "moon_rise": m_rise_local,
            "moon_set": m_set_local,
            "moon_phase": moon_phase_icon(phase_angle)
        })

        current += timedelta(days=1)
        day_count += 1

    return day_results

# --------------------------------------------------
# MAIN APP
# --------------------------------------------------
def main():
    # Session defaults
    if "lat" not in st.session_state:
        st.session_state["lat"] = 31.6258  # e.g. Marrakech
    if "lon" not in st.session_state:
        st.session_state["lon"] = -7.9892
    if "city" not in st.session_state:
        st.session_state["city"] = "Marrakech"

    st.subheader("Location & Date Range")

    # Row: City input + Use IP side by side
    row1_col1, row1_col2 = st.columns([2,1])
    with row1_col1:
        city_input = st.text_input("City (optional)", value=st.session_state["city"])
    with row1_col2:
        # Make button same height by using a dummy label
        st.write("")  # forces alignment
        if st.button("Use IP Location"):
            lat_ip, lon_ip = get_ip_location()
            if lat_ip and lon_ip:
                st.session_state["lat"] = lat_ip
                st.session_state["lon"] = lon_ip
                found_city = reverse_geocode(lat_ip, lon_ip)
                if found_city:
                    st.session_state["city"] = found_city
                st.success(f"Set lat={lat_ip:.4f}, lon={lon_ip:.4f}")
            else:
                st.warning("No IP location found.")

    # If city changed
    if city_input != st.session_state["city"]:
        st.session_state["city"] = city_input
        coords = geocode_place(city_input)
        if coords:
            st.session_state["lat"], st.session_state["lon"] = coords
        else:
            st.warning("City not found. Check spelling or use lat/lon.")

    # Row: lat,lon
    row2_col1, row2_col2 = st.columns(2)
    with row2_col1:
        new_lat = st.number_input("Latitude", value=st.session_state["lat"], format="%.6f")
    with row2_col2:
        new_lon = st.number_input("Longitude", value=st.session_state["lon"], format="%.6f")

    # If changed
    if abs(new_lat - st.session_state["lat"])>1e-9 or abs(new_lon - st.session_state["lon"])>1e-9:
        st.session_state["lat"] = new_lat
        st.session_state["lon"] = new_lon
        # reverse geocode?
        guess = reverse_geocode(new_lat, new_lon)
        if guess:
            st.session_state["city"] = guess

    # row: date range + no_moon
    row3_col1, row3_col2 = st.columns([2,1])
    with row3_col1:
        d_range = st.date_input("Date Range (up to 14 days)", [date(2025,10,15), date(2025,10,22)])
        if len(d_range) == 1:
            start_d = d_range[0]
            end_d = d_range[0]
        else:
            start_d, end_d = d_range[0], d_range[-1]

    with row3_col2:
        # Make checkbox same height as text field with an empty write
        st.write("")
        no_moon = st.checkbox("No Moon", value=False)

    # Expander for optional map
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
            ccity = reverse_geocode(clat, clng)
            if ccity:
                st.session_state["city"] = ccity
            st.info(f"Selected lat={clat:.4f}, lon={clng:.4f}")

    # CALCULATE
    if st.button("Calculate"):
        if start_d > end_d:
            st.error("Start date must be <= end date.")
            return
        # compute
        daily_data = compute_day_details(
            st.session_state["lat"],
            st.session_state["lon"],
            start_d,
            end_d,
            no_moon
        )
        if not daily_data:
            st.warning("No data (maybe more than 14 days?).")
            return

        # Summaries
        total_astro = sum(x["astro_dark_hours"] for x in daily_data)
        total_moonless = sum(x["moonless_hours"] for x in daily_data)

        st.write("---")
        st.subheader("Results")
        colA, colB = st.columns(2)
        with colA:
            st.success(f"Total Astronomical Darkness: {total_astro:.2f} hrs")
        with colB:
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
