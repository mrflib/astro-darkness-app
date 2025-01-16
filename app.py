import streamlit as st
from datetime import date, datetime, timedelta
from skyfield.api import Topos, load
from geopy.geocoders import Nominatim
import requests

# Optional: If you want local times:
import pytz
from timezonefinder import TimezoneFinder

# ------------------------------------------------------
# PAGE CONFIG
# ------------------------------------------------------
st.set_page_config(
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="centered"
)

# ------------------------------------------------------
# GLOBALS / UTILS
# ------------------------------------------------------
def geocode_place(place_name):
    """Convert city/place name -> (lat, lon). Returns None if not found."""
    geolocator = Nominatim(user_agent="astro_darkness_app")
    try:
        location = geolocator.geocode(place_name)
        if location:
            return (location.latitude, location.longitude)
    except:
        pass
    return None

def reverse_geocode(lat, lon):
    """Convert lat/lon -> city name (approx) using reverse geocoding."""
    geolocator = Nominatim(user_agent="astro_darkness_app")
    try:
        location = geolocator.reverse((lat, lon), language='en')
        if location and location.address:
            # location.raw has more detail if you want it
            # We'll just return the 'city' or fallback to 'town', else the full address
            address_dict = location.raw.get('address', {})
            city = address_dict.get('city') or address_dict.get('town') or address_dict.get('village')
            if city:
                return city
            else:
                # fallback to full address
                return location.address
    except:
        pass
    return ""

def get_ip_location():
    """
    Approximate location from IP using ipapi.co or similar.
    Returns (lat, lon) or (None, None).
    """
    try:
        resp = requests.get("https://ipapi.co/json/")
        if resp.status_code == 200:
            data = resp.json()
            lat = data.get("latitude")
            lon = data.get("longitude")
            return (lat, lon)
    except:
        pass
    return (None, None)

# ------------------------------------------------------
# ASTRONOMY CALCULATIONS
# ------------------------------------------------------
def get_astronomical_darkness_hours(lat, lon, start_date, end_date, no_moon=False):
    """
    Calculate hours of astronomical darkness (sun < -18 deg)
    for a location between start_date and end_date.
    If no_moon=True, subtract any time the moon is above horizon.
    Limited to ~14 days.
    """
    # 1. Load ephemeris data
    ts = load.timescale()
    eph = load('de421.bsp')
    
    # 2. Create observer location
    location = Topos(latitude_degrees=lat, longitude_degrees=lon)
    
    # 3. Setup date iteration
    current_date = start_date
    total_darkness_hours = 0.0
    total_darkness_with_no_moon_hours = 0.0

    max_days = 14
    days_counted = 0

    while current_date <= end_date and days_counted < max_days:
        day_start = ts.utc(current_date.year, current_date.month, current_date.day, 0, 0, 0)
        step_minutes = 5
        n_steps = (24 * 60) // step_minutes
        
        times_list = []
        for step in range(n_steps + 1):
            fraction_of_day = (step * step_minutes) / (24.0 * 60.0)
            times_list.append(day_start.tt + fraction_of_day)

        sun_altitudes = []
        moon_altitudes = []
        sun = eph['Sun']
        moon = eph['Moon']
        observer = eph['Earth'] + location

        for t_tt in times_list:
            t = ts.tt_jd(t_tt)
            # Sun altitude
            app_sun = observer.at(t).observe(sun).apparent()
            alt_sun, _, _ = app_sun.altaz()
            sun_altitudes.append(alt_sun.degrees)

            # Moon altitude
            app_moon = observer.at(t).observe(moon).apparent()
            alt_moon, _, _ = app_moon.altaz()
            moon_altitudes.append(alt_moon.degrees)

        darkness_minutes = 0
        darkness_no_moon_minutes = 0
        for i in range(len(times_list) - 1):
            sun_mid = (sun_altitudes[i] + sun_altitudes[i+1]) / 2.0
            moon_mid = (moon_altitudes[i] + moon_altitudes[i+1]) / 2.0
            if sun_mid < -18.0:
                darkness_minutes += step_minutes
                if no_moon:
                    if moon_mid < 0.0:
                        darkness_no_moon_minutes += step_minutes
                else:
                    darkness_no_moon_minutes += step_minutes

        total_darkness_hours += darkness_minutes / 60.0
        total_darkness_with_no_moon_hours += darkness_no_moon_minutes / 60.0

        current_date += timedelta(days=1)
        days_counted += 1

    if no_moon:
        return total_darkness_with_no_moon_hours
    else:
        return total_darkness_hours


# ------------------------------------------------------
# MAIN STREAMLIT APP
# ------------------------------------------------------
def main():
    st.title("Astronomical Darkness Calculator")
    st.write("Find how many hours of true night you get, anywhere in the world.")

    st.markdown("**Note**: You can provide *either* City *or* Latitude/Longitude. Whichever you update last will override the other.")
    
    # Setup session states to store lat/lon/city
    if "lat" not in st.session_state:
        st.session_state["lat"] = 51.5074
    if "lon" not in st.session_state:
        st.session_state["lon"] = -0.1278
    if "city" not in st.session_state:
        st.session_state["city"] = "London"

    # --------------- Location Entry Section ---------------
    col1, col2 = st.columns([1,1])
    with col1:
        # City input
        city_input = st.text_input("City Name", value=st.session_state["city"])
    with col2:
        st.write(" ")
        # Crosshair button to auto-fill from IP
        if st.button("➕ Crosshair (Use My Location)"):
            ip_lat, ip_lon = get_ip_location()
            if ip_lat and ip_lon:
                st.session_state["lat"] = ip_lat
                st.session_state["lon"] = ip_lon
                # Optionally do a reverse geocode to get city name
                found_city = reverse_geocode(ip_lat, ip_lon)
                if found_city:
                    st.session_state["city"] = found_city
                st.success(f"Location set to lat={ip_lat:.4f}, lon={ip_lon:.4f}, city={st.session_state['city']}")
            else:
                st.warning("Could not get location from IP. Please enter manually.")

    # If user changes city, we want to override lat/lon
    if city_input != st.session_state["city"]:
        st.session_state["city"] = city_input
        coords = geocode_place(city_input)
        if coords:
            lat, lon = coords
            st.session_state["lat"] = lat
            st.session_state["lon"] = lon
        else:
            st.warning("Could not find city. Please check spelling or enter lat/lon manually.")

    # Show lat/lon fields
    col3, col4 = st.columns(2)
    with col3:
        lat_input = st.number_input("Latitude", value=st.session_state["lat"], format="%.6f")
    with col4:
        lon_input = st.number_input("Longitude", value=st.session_state["lon"], format="%.6f")

    # If lat_input or lon_input changed, override city
    if abs(lat_input - st.session_state["lat"]) > 1e-9 or abs(lon_input - st.session_state["lon"]) > 1e-9:
        st.session_state["lat"] = lat_input
        st.session_state["lon"] = lon_input
        # Reverse geocode to city
        found_city = reverse_geocode(lat_input, lon_input)
        if found_city:
            st.session_state["city"] = found_city

    st.write("---")

    # Date range
    st.subheader("Date Range Selection")
    date_range = st.date_input("Select a date range (up to 14 days)", [date(2025, 1, 1), date(2025, 1, 7)])
    if len(date_range) == 1:
        start_date = date_range[0]
        end_date = date_range[0]
    else:
        start_date = date_range[0]
        end_date = date_range[-1]

    no_moon = st.checkbox("No Moon", value=False)

    # Calculate button
    if st.button("Calculate"):
        if start_date > end_date:
            st.error("Start date must be <= end date.")
        else:
            # Perform astro darkness calc
            darkness = get_astronomical_darkness_hours(
                st.session_state["lat"],
                st.session_state["lon"],
                start_date,
                end_date,
                no_moon=False
            )
            result_str = f"Total astronomical darkness: {darkness:.2f} hours"

            if no_moon:
                darkness_no_moon = get_astronomical_darkness_hours(
                    st.session_state["lat"],
                    st.session_state["lon"],
                    start_date,
                    end_date,
                    no_moon=True
                )
                result_str += f"\nMoonless darkness: {darkness_no_moon:.2f} hours"

            st.success(result_str)


if __name__ == "__main__":
    main()
