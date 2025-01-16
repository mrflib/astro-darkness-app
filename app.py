import streamlit as st
from datetime import date, datetime, timedelta
import pandas as pd

# Astronomy
from skyfield.api import Topos, load

# Geocoding
from geopy.geocoders import Nominatim
import requests

# Map
import folium
from streamlit_folium import st_folium

# Timezone
import pytz
from timezonefinder import TimezoneFinder

# ------------------------------------------------------
# PAGE CONFIG
# ------------------------------------------------------
st.set_page_config(
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="wide"  # using wide for more space, especially for side-by-side results
)

# ------------------------------------------------------
# CLIMATE DATA (MONTHLY) - Example placeholder
# ------------------------------------------------------
# In a real scenario, you'd have different data for different locations or an API.
# Here, we store a single global set of "average" monthly values as a demo.
monthly_climate_data = {
    1: {"name": "January",   "day_cloud": 60, "night_cloud": 70, "day_temp": 5,  "night_temp": 0,  "day_humid": 80, "night_humid": 90, "day_dew": 2,   "night_dew": -1},
    2: {"name": "February",  "day_cloud": 55, "night_cloud": 65, "day_temp": 6,  "night_temp": 1,  "day_humid": 78, "night_humid": 88, "day_dew": 1,   "night_dew": -2},
    3: {"name": "March",     "day_cloud": 50, "night_cloud": 60, "day_temp": 10, "night_temp": 3,  "day_humid": 76, "night_humid": 86, "day_dew": 3,   "night_dew": 0},
    4: {"name": "April",     "day_cloud": 45, "night_cloud": 55, "day_temp": 14, "night_temp": 6,  "day_humid": 70, "night_humid": 80, "day_dew": 5,   "night_dew": 2},
    5: {"name": "May",       "day_cloud": 40, "night_cloud": 50, "day_temp": 18, "night_temp": 10, "day_humid": 68, "night_humid": 78, "day_dew": 10,  "night_dew": 6},
    6: {"name": "June",      "day_cloud": 35, "night_cloud": 45, "day_temp": 22, "night_temp": 14, "day_humid": 65, "night_humid": 75, "day_dew": 15,  "night_dew": 12},
    7: {"name": "July",      "day_cloud": 40, "night_cloud": 50, "day_temp": 25, "night_temp": 17, "day_humid": 60, "night_humid": 70, "day_dew": 18,  "night_dew": 15},
    8: {"name": "August",    "day_cloud": 45, "night_cloud": 55, "day_temp": 24, "night_temp": 16, "day_humid": 62, "night_humid": 72, "day_dew": 17,  "night_dew": 14},
    9: {"name": "September","day_cloud": 50, "night_cloud": 60, "day_temp": 20, "night_temp": 12, "day_humid": 70, "night_humid": 80, "day_dew": 12,  "night_dew": 9},
    10: {"name":"October",  "day_cloud": 55, "night_cloud": 65, "day_temp": 15, "night_temp": 8,  "day_humid": 75, "night_humid": 85, "day_dew": 8,   "night_dew": 5},
    11: {"name":"November", "day_cloud": 60, "night_cloud": 70, "day_temp": 9,  "night_temp": 4,  "day_humid": 80, "night_humid": 90, "day_dew": 5,   "night_dew": 2},
    12: {"name":"December", "day_cloud": 65, "night_cloud": 75, "day_temp": 6,  "night_temp": 1,  "day_humid": 85, "night_humid": 95, "day_dew": 3,   "night_dew": 0},
}

def get_monthly_averages_for_range(start_dt, end_dt):
    """
    Weighted average of the monthly climate data over the chosen date range.
    """
    if start_dt > end_dt:
        return None

    total_days = 0
    accum = {
        "day_cloud": 0, "night_cloud": 0, "day_temp": 0, "night_temp": 0,
        "day_humid": 0, "night_humid": 0, "day_dew": 0, "night_dew": 0
    }
    current = start_dt
    while current <= end_dt:
        m = current.month
        if m in monthly_climate_data:
            accum["day_cloud"]   += monthly_climate_data[m]["day_cloud"]
            accum["night_cloud"] += monthly_climate_data[m]["night_cloud"]
            accum["day_temp"]    += monthly_climate_data[m]["day_temp"]
            accum["night_temp"]  += monthly_climate_data[m]["night_temp"]
            accum["day_humid"]   += monthly_climate_data[m]["day_humid"]
            accum["night_humid"] += monthly_climate_data[m]["night_humid"]
            accum["day_dew"]     += monthly_climate_data[m]["day_dew"]
            accum["night_dew"]   += monthly_climate_data[m]["night_dew"]
            total_days += 1
        current += timedelta(days=1)

    if total_days == 0:
        return None

    for k in accum:
        accum[k] /= total_days

    return accum

# ------------------------------------------------------
# SQM + BORTLE
# ------------------------------------------------------
def sqm_to_bortle(sqm):
    """
    Rough approximation from SQM (mag/arcsec^2) to Bortle scale.
    """
    if sqm >= 22:
        return 1
    elif sqm >= 21.5:
        return 2
    elif sqm >= 21.3:
        return 3
    elif sqm >= 20.9:
        return 4
    elif sqm >= 20.3:
        return 5
    elif sqm >= 19.5:
        return 6
    elif sqm >= 18.0:
        return 7
    else:
        return 8

# ------------------------------------------------------
# GEOCODING
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
            address_dict = location.raw.get('address', {})
            city = (address_dict.get('city') or 
                    address_dict.get('town') or
                    address_dict.get('village') or
                    address_dict.get('hamlet'))
            return city if city else location.address
    except:
        pass
    return ""

def get_ip_location():
    """
    Approximate location from IP using ipapi.co.
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
# OPTIONAL: If you'd like to speed up repeated calculations, uncomment the @st.cache_data line
# @st.cache_data
def get_astronomical_darkness_hours(lat, lon, start_date, end_date, no_moon=False, step_minutes=5):
    """
    Calculate hours of astronomical darkness (sun < -18 deg).
    If no_moon=True, subtract time Moon is above horizon.
    NOTE: step_minutes=5 is fairly fine. For performance, you could do 10 or 15.
    """
    ts = load.timescale()
    eph = load('de421.bsp')
    
    location = Topos(latitude_degrees=lat, longitude_degrees=lon)

    current_date = start_date
    total_darkness_hours = 0.0
    total_darkness_no_moon = 0.0
    max_days = 14
    days_counted = 0

    while current_date <= end_date and days_counted < max_days:
        day_start = ts.utc(current_date.year, current_date.month, current_date.day, 0, 0, 0)
        n_steps = (24 * 60) // step_minutes
        
        times_list = []
        for step_i in range(n_steps + 1):
            fraction_of_day = (step_i * step_minutes) / (24.0 * 60.0)
            times_list.append(day_start.tt + fraction_of_day)

        sun_altitudes = []
        moon_altitudes = []
        sun = eph['Sun']
        moon = eph['Moon']
        observer = eph['Earth'] + location

        for t_tt in times_list:
            t = ts.tt_jd(t_tt)
            app_sun = observer.at(t).observe(sun).apparent()
            alt_sun, _, _ = app_sun.altaz()
            sun_alt = alt_sun.degrees

            app_moon = observer.at(t).observe(moon).apparent()
            alt_moon, _, _ = app_moon.altaz()
            moon_alt = alt_moon.degrees

            sun_altitudes.append(sun_alt)
            moon_altitudes.append(moon_alt)

        # Summation approach
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

        total_darkness_hours += (darkness_minutes / 60.0)
        total_darkness_no_moon += (darkness_no_moon_minutes / 60.0)

        current_date += timedelta(days=1)
        days_counted += 1

    if no_moon:
        return total_darkness_no_moon
    else:
        return total_darkness_hours

# ------------------------------------------------------
# MAIN STREAMLIT APP
# ------------------------------------------------------
def main():
    st.title("Astronomical Darkness Calculator")
    st.write("Find how many hours of true night you get, anywhere in the world.")

    # Provide a note about possible slow calculations
    st.info("**Note**: Calculations can take a while for large date ranges or 'No Moon' mode. Please be patient!")
    
    # Columns for layout
    col_left, col_right = st.columns([1.2, 1])
    
    with col_left:
        st.subheader("Location")
        st.markdown("You can **search by city**, **click the map**, or **type lat/lon**.")

        # We'll store location in session state
        if "lat" not in st.session_state:
            st.session_state["lat"] = 51.5074
        if "lon" not in st.session_state:
            st.session_state["lon"] = -0.1278
        if "city" not in st.session_state:
            st.session_state["city"] = "London"

        # City input
        city_input = st.text_input("City Name (optional)", value=st.session_state["city"])

        # Crosshair (Use My Location) button
        if st.button("📍 Use My Location"):
            ip_lat, ip_lon = get_ip_location()
            if ip_lat and ip_lon:
                st.session_state["lat"] = ip_lat
                st.session_state["lon"] = ip_lon
                # Reverse geocode
                found_city = reverse_geocode(ip_lat, ip_lon)
                if found_city:
                    st.session_state["city"] = found_city
                st.success(f"Location set: lat={ip_lat:.4f}, lon={ip_lon:.4f}, city={st.session_state['city']}")
            else:
                st.warning("Could not get location from IP. Please enter manually.")

        # If city changed
        if city_input != st.session_state["city"]:
            st.session_state["city"] = city_input
            coords = geocode_place(city_input)
            if coords:
                st.session_state["lat"] = coords[0]
                st.session_state["lon"] = coords[1]
            else:
                st.warning("Could not find city. Check spelling or specify lat/lon manually.")

        # Show lat/lon
        lat_input = st.number_input("Latitude", value=st.session_state["lat"], format="%.6f")
        lon_input = st.number_input("Longitude", value=st.session_state["lon"], format="%.6f")

        # If user typed new lat/lon
        if abs(lat_input - st.session_state["lat"]) > 1e-9 or abs(lon_input - st.session_state["lon"]) > 1e-9:
            st.session_state["lat"] = lat_input
            st.session_state["lon"] = lon_input
            found_city = reverse_geocode(lat_input, lon_input)
            if found_city:
                st.session_state["city"] = found_city

        # Map with Folium
        st.markdown("**Pick on Map** (optional):")
        default_location = [st.session_state["lat"], st.session_state["lon"]]
        m = folium.Map(location=default_location, zoom_start=4)
        folium.TileLayer('OpenStreetMap').add_to(m)
        m.add_child(folium.LatLngPopup())

        map_data = st_folium(m, width=600, height=400)
        if map_data and map_data['last_clicked'] is not None:
            clicked_lat = map_data['last_clicked']['lat']
            clicked_lon = map_data['last_clicked']['lng']
            # Update lat/lon
            st.session_state["lat"] = clicked_lat
            st.session_state["lon"] = clicked_lon
            found_city = reverse_geocode(clicked_lat, clicked_lon)
            if found_city:
                st.session_state["city"] = found_city
            st.info(f"You clicked lat={clicked_lat:.4f}, lon={clicked_lon:.4f}. Updated location.")
        
        st.write("---")

        # Date range
        st.subheader("Date Range")
        date_range = st.date_input("Select a date range (up to 14 days)", [date(2025, 1, 1), date(2025, 1, 7)])
        if len(date_range) == 1:
            start_date = date_range[0]
            end_date = date_range[0]
        else:
            start_date, end_date = date_range[0], date_range[-1]

        # No Moon checkbox with tooltip
        no_moon = st.checkbox(
            "No Moon",
            value=False,
            help="Excludes times when the Moon is above the horizon. Note: This increases calculation time!"
        )

        # SQM & Bortle
        st.subheader("SQM & Bortle")
        sqm_value = st.number_input("Sky Quality Meter (mag/arcsec²)", value=21.0, format="%.2f")
        derived_bortle = sqm_to_bortle(sqm_value)
        st.write(f"Approx Bortle Scale: **{derived_bortle}**")

        # Climate data
        st.subheader("Average Climate")
        climate_summary = get_monthly_averages_for_range(start_date, end_date)
        if climate_summary:
            st.write(f"Estimated Daytime Cloud: {climate_summary['day_cloud']:.1f}%")
            st.write(f"Estimated Nighttime Cloud: {climate_summary['night_cloud']:.1f}%")
            st.write(f"Estimated Daytime Temp: {climate_summary['day_temp']:.1f} °C")
            st.write(f"Estimated Nighttime Temp: {climate_summary['night_temp']:.1f} °C")
            st.write(f"Estimated Daytime Humidity: {climate_summary['day_humid']:.1f}%")
            st.write(f"Estimated Nighttime Humidity: {climate_summary['night_humid']:.1f}%")
            st.write(f"Estimated Daytime Dew Pt: {climate_summary['day_dew']:.1f} °C")
            st.write(f"Estimated Nighttime Dew Pt: {climate_summary['night_dew']:.1f} °C")
        else:
            st.write("No climate data found for that range (check your dates).")

        # Performance tip
        st.caption("For faster performance, consider smaller date ranges or bigger time steps (e.g. 10-15 minutes).")

    with col_right:
        st.subheader("Calculate Darkness")

        if st.button("Go!"):
            if start_date > end_date:
                st.error("Start date must be <= end date.")
            else:
                lat_final = st.session_state["lat"]
                lon_final = st.session_state["lon"]
                # Calculate
                astro_dark = get_astronomical_darkness_hours(
                    lat_final, lon_final, start_date, end_date, no_moon=False, step_minutes=5
                )
                moonless_dark = get_astronomical_darkness_hours(
                    lat_final, lon_final, start_date, end_date, no_moon=True, step_minutes=5
                )

                # Display results side by side
                left_res, right_res = st.columns(2)
                with left_res:
                    st.success(f"Total astro darkness: {astro_dark:.2f} hours")
                with right_res:
                    st.success(f"Moonless darkness: {moonless_dark:.2f} hours")


if __name__ == "__main__":
    main()
