import streamlit as st
from datetime import date, datetime, time, timedelta
import pytz
from timezonefinder import TimezoneFinder
import pandas as pd
from skyfield.api import Topos, load
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium
import math

# -------------------------------------------------------------------
# CONFIG: Single-column for mobile
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="centered"
)

# -------------------------------------------------------------------
# GEOLOCATION HELPERS
# -------------------------------------------------------------------
def get_ip_location():
    """Approx user location by IP (ipapi.co)."""
    import requests
    try:
        r = requests.get("https://ipapi.co/json/")
        if r.status_code == 200:
            data = r.json()
            return (data.get("latitude"), data.get("longitude"))
    except:
        pass
    return (None, None)

def geocode_place(place_name):
    """Convert city/place name -> (lat, lon)."""
    from geopy.geocoders import Nominatim
    geolocator = Nominatim(user_agent="astro_app")
    try:
        loc = geolocator.geocode(place_name)
        if loc:
            return (loc.latitude, loc.longitude)
    except:
        pass
    return None

def reverse_geocode(lat, lon):
    """Convert lat/lon -> city name (approx)."""
    from geopy.geocoders import Nominatim
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

# -------------------------------------------------------------------
# MOON PHASE ICON
# -------------------------------------------------------------------
def moon_phase_icon(angle_deg):
    """Return an emoji for the moon phase based on angle in [0..360]."""
    angle = angle_deg % 360
    if angle < 22.5 or angle >= 337.5:
        return "🌑"  # new
    elif angle < 67.5:
        return "🌒"
    elif angle < 112.5:
        return "🌓"
    elif angle < 157.5:
        return "🌔"
    elif angle < 202.5:
        return "🌕"
    elif angle < 247.5:
        return "🌖"
    elif angle < 292.5:
        return "🌗"
    else:
        return "🌘"

# -------------------------------------------------------------------
# DAY-BY-DAY ASTRONOMY WITH LOCAL TIME
# -------------------------------------------------------------------
def compute_daily_details_local(lat, lon, start_date, end_date, no_moon=False):
    """
    For each day from start_date to end_date (max 14 days):
      - find local timezone
      - step from local midnight to local midnight in 1-minute increments
      - convert each local time -> UTC for Skyfield
      - compute sun alt, moon alt
      - sum times sun alt < -18 => astro darkness
      - if no_moon => exclude times moon alt >= 0
      - find minute of crossing for dark start/end, moon rise/set (with interpolation)
      - store times in local format HH:MM
      - also compute moon phase at local noon or so
    Return a list of daily dicts.
    """
    # Load ephemeris
    ts = load.timescale()
    eph = load('de421.bsp')
    # We figure out local timezone
    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
    local_tz = pytz.timezone(tz_name)
    
    # We will store up to 14 days
    max_days = 14
    day_count = 0
    results = []
    
    # Predefine planet references
    sun = eph['Sun']
    moon = eph['Moon']
    observer = eph['Earth'] + Topos(lat, lon)
    
    current = start_date
    while current <= end_date and day_count < max_days:
        # local midnight start
        local_midnight = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_midnight_end = local_midnight + timedelta(days=1)
        
        # We'll do 1-minute increments
        # That is 1440 steps => might be slow for 14 days = 20160 steps. 
        # If it's too slow, do 2-minute increments. Let's keep 1-min for better accuracy.

        step_minutes = 1
        # We'll store altitudes
        sun_alts = []
        moon_alts = []
        times_local = []
        
        # We'll generate local times from midnight to midnight
        dt_local = local_midnight
        while dt_local < local_midnight_end:
            times_local.append(dt_local)
            dt_local += timedelta(minutes=step_minutes)
        
        # Convert each local time to UTC for skyfield
        # Then compute alt
        for i, loc_dt in enumerate(times_local):
            # convert local -> UTC
            loc_dt_utc = local_tz.normalize(local_tz.localize(loc_dt)).astimezone(pytz.utc)
            # Build skyfield time
            t = ts.from_datetime(loc_dt_utc)

            # compute alt
            app_sun = observer.at(t).observe(sun).apparent()
            alt_sun, _, _ = app_sun.altaz()
            sun_deg = alt_sun.degrees
            
            app_moon = observer.at(t).observe(moon).apparent()
            alt_moon, _, _ = app_moon.altaz()
            moon_deg = alt_moon.degrees

            sun_alts.append(sun_deg)
            moon_alts.append(moon_deg)
        
        # Summation approach
        astro_minutes = 0
        moonless_minutes = 0
        dark_start_minute = None
        dark_end_minute = None
        darkness_started = False

        for i in range(len(times_local)-1):
            sun_mid = (sun_alts[i] + sun_alts[i+1]) / 2.0
            moon_mid = (moon_alts[i] + moon_alts[i+1]) / 2.0
            if sun_mid < -18.0:
                astro_minutes += step_minutes
                if no_moon:
                    if moon_mid < 0.0:
                        moonless_minutes += step_minutes
                else:
                    moonless_minutes += step_minutes
                
                if not darkness_started:
                    darkness_started = True
                    dark_start_minute = i  # approximate
            else:
                if darkness_started:
                    dark_end_minute = i
                    darkness_started = False
        if darkness_started and dark_end_minute is None:
            dark_end_minute = len(times_local)-1
        
        # Convert these start/end minute indexes to local time strings
        if dark_start_minute is not None:
            dark_start_local = times_local[dark_start_minute]
            dark_start_str = dark_start_local.strftime("%H:%M")
        else:
            dark_start_str = "-"
        if dark_end_minute is not None:
            dark_end_local = times_local[dark_end_minute]
            dark_end_str = dark_end_local.strftime("%H:%M")
        else:
            dark_end_str = "-"

        # Moon rise/set detection
        # We'll note the first crossing from negative -> positive as rise,
        # and positive -> negative as set.
        moonrise_minute = None
        moonset_minute = None
        prev_alt = moon_alts[0]
        for i in range(1, len(moon_alts)):
            curr_alt = moon_alts[i]
            if prev_alt < 0 and curr_alt >= 0 and moonrise_minute is None:
                # We'll do a linear interpolation to find the crossing minute
                # alt changes from prev_alt to curr_alt over 1 min
                # crossing 0 => fraction
                fraction = 0.0
                if (curr_alt - prev_alt) != 0:
                    fraction = -prev_alt / (curr_alt - prev_alt)
                cross_minute = i - 1 + fraction
                cross_idx = int(math.floor(cross_minute))
                fraction_of_min = cross_minute - cross_idx
                cross_time = times_local[cross_idx] + timedelta(minutes=(fraction_of_min))
                moonrise_minute = cross_time
            if prev_alt >= 0 and curr_alt < 0 and moonset_minute is None:
                fraction = 0.0
                if (curr_alt - prev_alt) != 0:
                    fraction = -prev_alt / (curr_alt - prev_alt)
                cross_minute = i - 1 + fraction
                cross_idx = int(math.floor(cross_minute))
                fraction_of_min = cross_minute - cross_idx
                cross_time = times_local[cross_idx] + timedelta(minutes=(fraction_of_min))
                moonset_minute = cross_time
            prev_alt = curr_alt

        if moonrise_minute:
            moonrise_str = moonrise_minute.strftime("%H:%M")
        else:
            moonrise_str = "-"
        if moonset_minute:
            moonset_str = moonset_minute.strftime("%H:%M")
        else:
            moonset_str = "-"

        # Let's pick local noon to find moon phase
        # or pick the midpoint times_local[len(times_local)//2]
        mid_idx = len(times_local)//2
        mid_t_local = times_local[mid_idx]
        mid_t_utc = local_tz.normalize(local_tz.localize(mid_t_local)).astimezone(pytz.utc)
        t_mid = load.timescale().from_datetime(mid_t_utc)
        # compute phase angle
        sun_ecl = observer.at(t_mid).observe(sun).apparent().ecliptic_latlon()
        moon_ecl = observer.at(t_mid).observe(moon).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees)%360
        
        day_info = {
            "date": current.strftime("%Y-%m-%d"),
            "astro_dark_hours": round(astro_minutes/60, 4),
            "moonless_hours": round(moonless_minutes/60, 4),
            "dark_start": dark_start_str,
            "dark_end": dark_end_str,
            "moon_rise": moonrise_str,
            "moon_set": moonset_str,
            "moon_phase": moon_phase_icon(phase_angle)
        }

        results.append(day_info)
        current += timedelta(days=1)
        day_count += 1
    
    return results


# -------------------------------------------------------------------
# MAIN APP
# -------------------------------------------------------------------
def main():
    st.title("Astronomical Darkness Calculator")
    st.write("Find how many hours of true night you get, with local times for sunset/moon times.")
    
    # If you prefer a single column, let's do minimal columns for the inputs
    if "lat" not in st.session_state:
        st.session_state["lat"] = 31.6258  # e.g. Marrakech
    if "lon" not in st.session_state:
        st.session_state["lon"] = -7.9892
    if "city" not in st.session_state:
        st.session_state["city"] = "Marrakech"

    st.subheader("Inputs")
    # Row 1: City, IP, lat/lon
    row1_col1, row1_col2 = st.columns([1.7,1])
    with row1_col1:
        city_input = st.text_input("City (optional)", value=st.session_state["city"], help="If used, lat/lon will update.")
    with row1_col2:
        if st.button("Use IP Location"):
            lat_ip, lon_ip = get_ip_location()
            if lat_ip and lon_ip:
                st.session_state["lat"] = lat_ip
                st.session_state["lon"] = lon_ip
                guess_city = reverse_geocode(lat_ip, lon_ip)
                if guess_city:
                    st.session_state["city"] = guess_city
                st.success(f"Set lat={lat_ip:.4f}, lon={lon_ip:.4f}")
            else:
                st.warning("No location from IP.")
    # If city changed
    if city_input != st.session_state["city"]:
        st.session_state["city"] = city_input
        coords = geocode_place(city_input)
        if coords:
            st.session_state["lat"], st.session_state["lon"] = coords
        else:
            st.warning("City not found or ambiguous. Check spelling or use lat/lon.")

    # Row 2 lat/lon
    row2_col1, row2_col2 = st.columns(2)
    with row2_col1:
        new_lat = st.number_input("Latitude", value=st.session_state["lat"], format="%.6f")
    with row2_col2:
        new_lon = st.number_input("Longitude", value=st.session_state["lon"], format="%.6f")
    if abs(new_lat - st.session_state["lat"])>1e-9 or abs(new_lon - st.session_state["lon"])>1e-9:
        st.session_state["lat"] = new_lat
        st.session_state["lon"] = new_lon
        # optional reverse geocode
        back_city = reverse_geocode(new_lat, new_lon)
        if back_city:
            st.session_state["city"] = back_city

    # Expander for map
    with st.expander("Pick on Map (optional)"):
        st.write("Click location on map to choose lat/lon.")
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
            guessed = reverse_geocode(clat, clng)
            if guessed:
                st.session_state["city"] = guessed
            st.info(f"Selected lat={clat:.4f}, lon={clng:.4f}")

    # Date range
    row3_col1, row3_col2 = st.columns([1.4,1])
    with row3_col1:
        d_range = st.date_input("Pick up to 14 days", [date(2025,10,15), date(2025,10,22)])
        if len(d_range)==1:
            start_d = d_range[0]
            end_d = d_range[0]
        else:
            start_d, end_d = d_range[0], d_range[-1]
    with row3_col2:
        no_moon = st.checkbox("No Moon", value=False, help="Exclude times the Moon is above horizon")

    # Calculate
    if st.button("Calculate"):
        if start_d> end_d:
            st.error("Start date must be <= end date.")
            return

        # 1) compute day-by-day
        daily_data = compute_daily_details_local(
            st.session_state["lat"], st.session_state["lon"],
            start_d, end_d, no_moon=no_moon
        )
        if not daily_data:
            st.warning("No data (range may exceed 14 days?).")
            return
        # Summation
        total_astro = sum(d["astro_dark_hours"] for d in daily_data)
        total_moonless = sum(d["moonless_hours"] for d in daily_data)

        st.write("---")
        st.subheader("Results")
        # Darkness boxes
        cA, cB = st.columns(2)
        with cA:
            st.success(f"Total Astronomical Darkness: {total_astro:.2f} hrs")
        with cB:
            st.success(f"Moonless Darkness: {total_moonless:.2f} hrs")

        # day-by-day table
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
