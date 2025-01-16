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

# Timezone (optional if you want local times, but we'll keep it simple here)
import pytz
from timezonefinder import TimezoneFinder

# ------------- PAGE CONFIG -------------
st.set_page_config(
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="wide"  # We'll arrange things in columns for a neater look
)

# ------------- SAMPLE MONTHLY CLIMATE DATA -------------
monthly_climate_data = {
    1: {"name":"January", "day_cloud":60, "night_cloud":70, "day_temp":5, "night_temp":0,  "day_humid":80, "night_humid":90, "day_dew":2,  "night_dew":-1},
    2: {"name":"February","day_cloud":55, "night_cloud":65, "day_temp":6, "night_temp":1,  "day_humid":78, "night_humid":88, "day_dew":1,  "night_dew":-2},
    3: {"name":"March",   "day_cloud":50, "night_cloud":60, "day_temp":10,"night_temp":3,  "day_humid":76, "night_humid":86, "day_dew":3,  "night_dew":0},
    4: {"name":"April",   "day_cloud":45, "night_cloud":55, "day_temp":14,"night_temp":6,  "day_humid":70, "night_humid":80, "day_dew":5,  "night_dew":2},
    5: {"name":"May",     "day_cloud":40, "night_cloud":50, "day_temp":18,"night_temp":10, "day_humid":68, "night_humid":78, "day_dew":10, "night_dew":6},
    6: {"name":"June",    "day_cloud":35, "night_cloud":45, "day_temp":22,"night_temp":14, "day_humid":65, "night_humid":75, "day_dew":15, "night_dew":12},
    7: {"name":"July",    "day_cloud":40, "night_cloud":50, "day_temp":25,"night_temp":17, "day_humid":60, "night_humid":70, "day_dew":18, "night_dew":15},
    8: {"name":"August",  "day_cloud":45, "night_cloud":55, "day_temp":24,"night_temp":16, "day_humid":62, "night_humid":72, "day_dew":17, "night_dew":14},
    9: {"name":"September","day_cloud":50,"night_cloud":60, "day_temp":20,"night_temp":12, "day_humid":70, "night_humid":80, "day_dew":12, "night_dew":9},
    10:{"name":"October", "day_cloud":55, "night_cloud":65, "day_temp":15,"night_temp":8,  "day_humid":75, "night_humid":85, "day_dew":8,  "night_dew":5},
    11:{"name":"November","day_cloud":60, "night_cloud":70, "day_temp":9, "night_temp":4,  "day_humid":80, "night_humid":90, "day_dew":5,  "night_dew":2},
    12:{"name":"December","day_cloud":65, "night_cloud":75, "day_temp":6, "night_temp":1,  "day_humid":85, "night_humid":95, "day_dew":3,  "night_dew":0},
}

def get_monthly_averages_for_range(start_dt, end_dt):
    """Weighted average of monthly climate data for the chosen date range."""
    if start_dt > end_dt:
        return None
    total_days = 0
    accum = {
        "day_cloud":0, "night_cloud":0, "day_temp":0, "night_temp":0,
        "day_humid":0, "night_humid":0, "day_dew":0, "night_dew":0
    }
    current = start_dt
    months_used = set()
    while current <= end_dt:
        m = current.month
        months_used.add(m)
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
    # Construct a heading for e.g. "Historical October Weather" or multiple months
    if len(months_used) == 1:
        single_month = months_used.pop()
        months_used.add(single_month)
        month_name = monthly_climate_data[single_month]["name"]
        accum["title"] = f"Historical {month_name} Weather"
    else:
        accum["title"] = "Historical Multi-Month Weather"
    return accum

# ------------- SIMPLE SQM LOOKUP -------------
def approximate_sqm_from_location(lat, lon):
    """
    Approximate an SQM value based on lat/lon. 
    In reality, you'd query a real dataset (e.g. a sky brightness map).
    Here, we just guess.
    """
    # For demonstration, let's guess lat near 0 = darkest sky, lat near 50 = moderate
    # This is obviously not realistic. Replace with real data or an API if desired.
    # e.g. if lat < 30 => 21.9, else lat < 60 => 21.3, else => 20.5
    lat_abs = abs(lat)
    if lat_abs < 30:
        return 21.9
    elif lat_abs < 50:
        return 21.3
    else:
        return 20.5

def sqm_to_bortle(sqm):
    """Convert SQM to Bortle scale (rough approximation)."""
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

# ------------- GEOCODING -------------
def geocode_place(place_name):
    geolocator = Nominatim(user_agent="astro_darkness_app")
    try:
        location = geolocator.geocode(place_name)
        if location:
            return (location.latitude, location.longitude)
    except:
        pass
    return None

def reverse_geocode(lat, lon):
    geolocator = Nominatim(user_agent="astro_darkness_app")
    try:
        location = geolocator.reverse((lat, lon), language='en')
        if location and location.address:
            address_dict = location.raw.get('address', {})
            city = (address_dict.get('city') or 
                    address_dict.get('town') or
                    address_dict.get('village') or
                    address_dict.get('hamlet'))
            if city: 
                return city
            return location.address
    except:
        pass
    return ""

def get_ip_location():
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

# ------------- MOON PHASE UTILS -------------
def moon_phase_icon(angle_deg):
    """
    Return a small moon-phase emoji based on angle between 0-360.
    0 = new moon, 180 = full moon, 90=first quarter, 270=last quarter, etc.
    We'll do simple thresholds for demonstration.
    """
    # Normalize angle 0..360
    angle = angle_deg % 360
    # We'll define 8 phases in ~45-degree increments
    # new (0), waxing crescent, first quarter, waxing gibbous, full, waning gibbous, last quarter, waning crescent
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

# ------------- DAILY DETAILS -------------
def compute_daily_details(lat, lon, start_date, end_date, no_moon=False):
    """
    Returns a list of daily dicts with:
      date, astro_dark_hours, astro_dark_start, astro_dark_end,
      moon_rise, moon_set, moonless_hours, moon_phase_icon
    Using a 10-minute step for each day.
    Limited to 14 days max for performance.
    """
    ts = load.timescale()
    eph = load('de421.bsp')
    location = Topos(latitude_degrees=lat, longitude_degrees=lon)
    sun = eph['Sun']
    moon = eph['Moon']
    observer = eph['Earth'] + location

    day_results = []
    max_days = 14
    days_counted = 0
    current = start_date

    while current <= end_date and days_counted < max_days:
        # We'll step in 10-min increments
        step_minutes = 10
        n_steps = (24 * 60) // step_minutes
        day_start_utc = ts.utc(current.year, current.month, current.day, 0, 0, 0)
        
        # Evaluate altitudes over the day
        times_list = []
        for i in range(n_steps+1):
            fraction = (i * step_minutes) / (24.0 * 60.0)
            times_list.append(day_start_utc.tt + fraction)
        
        sun_alt_list = []
        moon_alt_list = []
        moon_phase_list = []

        for t_tt in times_list:
            t = ts.tt_jd(t_tt)
            # Sun alt
            app_sun = observer.at(t).observe(sun).apparent()
            alt_sun, _, _ = app_sun.altaz()
            sun_alt = alt_sun.degrees
            
            # Moon alt
            app_moon = observer.at(t).observe(moon).apparent()
            alt_moon, _, _ = app_moon.altaz()
            moon_alt = alt_moon.degrees

            # Moon phase angle
            # We'll approximate by difference in ecliptic longitudes
            sun_ecl = observer.at(t).observe(sun).apparent().ecliptic_latlon()
            moon_ecl = observer.at(t).observe(moon).apparent().ecliptic_latlon()
            sun_long = sun_ecl[1].degrees
            moon_long = moon_ecl[1].degrees
            phase_angle = (moon_long - sun_long) % 360

            sun_alt_list.append(sun_alt)
            moon_alt_list.append(moon_alt)
            moon_phase_list.append(phase_angle)

        # Summation approach for astro darkness
        astro_minutes = 0
        moonless_minutes = 0
        astro_dark_start_str = None
        astro_dark_end_str = None

        # We'll do a quick approach to find first/last chunk of sun < -18
        darkness_started = False
        day_start_local = datetime(current.year, current.month, current.day, 0, 0, 0)  # naive
        # We'll find times in naive UTC or local if we want, but let's keep it simple.

        for i in range(n_steps):
            sun_mid = (sun_alt_list[i] + sun_alt_list[i+1]) / 2.0
            moon_mid = (moon_alt_list[i] + moon_alt_list[i+1]) / 2.0

            if sun_mid < -18.0:
                astro_minutes += step_minutes
                if no_moon:
                    if moon_mid < 0.0:
                        moonless_minutes += step_minutes
                else:
                    moonless_minutes += step_minutes

                # Mark start if we haven't already
                if not darkness_started:
                    # We'll approximate the start to the i-th step
                    # For display, just say HH:MM
                    darkness_started = True
                    # approximate time in hours/min from midnight
                    start_hrs = (i * step_minutes) // 60
                    start_mins = (i * step_minutes) % 60
                    astro_dark_start_str = f"{start_hrs:02d}:{start_mins:02d}"
            else:
                if darkness_started:
                    # we ended darkness
                    end_hrs = (i * step_minutes) // 60
                    end_mins = (i * step_minutes) % 60
                    astro_dark_end_str = f"{end_hrs:02d}:{end_mins:02d}"
                    darkness_started = False

        # If darkness persisted til end of day
        if darkness_started and not astro_dark_end_str:
            astro_dark_end_str = "24:00"

        # Moon rise/set
        moon_rise_str = None
        moon_set_str = None
        prev_alt = moon_alt_list[0]
        for i in range(1, len(moon_alt_list)):
            curr_alt = moon_alt_list[i]
            if prev_alt < 0 and curr_alt >= 0 and not moon_rise_str:
                # Approx moonrise
                hrs = (i * step_minutes) // 60
                mins = (i * step_minutes) % 60
                moon_rise_str = f"{hrs:02d}:{mins:02d}"
            if prev_alt >= 0 and curr_alt < 0 and not moon_set_str:
                # Approx moonset
                hrs = (i * step_minutes) // 60
                mins = (i * step_minutes) % 60
                moon_set_str = f"{hrs:02d}:{mins:02d}"
            prev_alt = curr_alt

        # Approx moon phase in middle of the day (say step n_steps//2)
        mid_phase_angle = moon_phase_list[n_steps//2]
        icon = moon_phase_icon(mid_phase_angle)

        day_info = {
            "date": current.strftime("%Y-%m-%d"),
            "astro_dark_hours": round(astro_minutes / 60.0, 2),
            "moonless_hours": round(moonless_minutes / 60.0, 2),
            "dark_start": astro_dark_start_str if astro_dark_start_str else "-",
            "dark_end": astro_dark_end_str if astro_dark_end_str else "-",
            "moon_rise": moon_rise_str if moon_rise_str else "-",
            "moon_set": moon_set_str if moon_set_str else "-",
            "moon_phase": icon
        }

        day_results.append(day_info)
        current += timedelta(days=1)
        days_counted += 1

    return day_results


# ------------- MAIN APP -------------
def main():
    st.title("Astronomical Darkness Calculator")
    st.write("Find how many hours of true night you get, anywhere in the world.")
    
    # For a tidier layout, let's do columns
    left_col, right_col = st.columns([1.3, 1])

    with left_col:
        st.subheader("Location Input")
        if "lat" not in st.session_state:
            st.session_state["lat"] = 51.5074
        if "lon" not in st.session_state:
            st.session_state["lon"] = -0.1278
        if "city" not in st.session_state:
            st.session_state["city"] = "London"

        # More compact input boxes
        c1, c2 = st.columns(2)
        with c1:
            city_input = st.text_input("City", value=st.session_state["city"], help="Optional. If provided, lat/lon will update.")
        with c2:
            if st.button("📍 Use My Location"):
                ip_lat, ip_lon = get_ip_location()
                if ip_lat and ip_lon:
                    st.session_state["lat"] = ip_lat
                    st.session_state["lon"] = ip_lon
                    found_city = reverse_geocode(ip_lat, ip_lon)
                    if found_city: 
                        st.session_state["city"] = found_city
                    st.success(f"Location set: lat={ip_lat:.4f}, lon={ip_lon:.4f}, city={st.session_state['city']}")
                else:
                    st.warning("Could not get location from IP.")

        if city_input != st.session_state["city"]:
            st.session_state["city"] = city_input
            coords = geocode_place(city_input)
            if coords:
                st.session_state["lat"], st.session_state["lon"] = coords
            else:
                st.warning("City not found. Check spelling or use lat/lon.")

        c3, c4 = st.columns(2)
        with c3:
            lat_input = st.number_input("Latitude", value=st.session_state["lat"], format="%.6f")
        with c4:
            lon_input = st.number_input("Longitude", value=st.session_state["lon"], format="%.6f")

        if abs(lat_input - st.session_state["lat"]) > 1e-9 or abs(lon_input - st.session_state["lon"]) > 1e-9:
            st.session_state["lat"] = lat_input
            st.session_state["lon"] = lon_input
            found_city = reverse_geocode(lat_input, lon_input)
            if found_city:
                st.session_state["city"] = found_city

        st.markdown("**Pick on Map**:")
        default_loc = [st.session_state["lat"], st.session_state["lon"]]
        my_map = folium.Map(location=default_loc, zoom_start=4)
        folium.TileLayer("OpenStreetMap").add_to(my_map)
        my_map.add_child(folium.LatLngPopup())
        map_data = st_folium(my_map, width=600, height=350)
        if map_data and map_data['last_clicked'] is not None:
            clat = map_data['last_clicked']['lat']
            clng = map_data['last_clicked']['lng']
            st.session_state["lat"] = clat
            st.session_state["lon"] = clng
            found_city = reverse_geocode(clat, clng)
            if found_city:
                st.session_state["city"] = found_city
            st.info(f"Clicked lat={clat:.4f}, lon={clng:.4f}")

        st.write("---")

        st.subheader("Date Range")
        date_range = st.date_input("Select up to 14 days", [date(2025,1,1), date(2025,1,7)])
        if len(date_range) == 1:
            start_date = date_range[0]
            end_date = date_range[0]
        else:
            start_date, end_date = date_range[0], date_range[-1]

        no_moon = st.checkbox("No Moon", value=False, help="Excludes times when the Moon is above the horizon.")

    with right_col:
        st.subheader("Calculate Darkness")
        if st.button("Go!"):
            if start_date > end_date:
                st.error("Start date must be <= end date.")
            else:
                lat_fin = st.session_state["lat"]
                lon_fin = st.session_state["lon"]
                
                # 1) Day-by-day details
                daily_data = compute_daily_details(lat_fin, lon_fin, start_date, end_date, no_moon=no_moon)
                if not daily_data:
                    st.warning("No data computed. Possibly over 14 days or date range is invalid.")
                    return
                
                # Summaries
                total_astro = sum(d["astro_dark_hours"] for d in daily_data)
                total_moonless = sum(d["moonless_hours"] for d in daily_data)

                # 2) Show results side by side in separate boxes
                cA, cB = st.columns(2)
                with cA:
                    st.success(f"Total Astronomical Darkness: {total_astro:.2f} hours")
                with cB:
                    st.success(f"Moonless Darkness: {total_moonless:.2f} hours")

                # 3) SQM + Bortle from location
                sqm_val = approximate_sqm_from_location(lat_fin, lon_fin)
                bortle_val = sqm_to_bortle(sqm_val)

                # 4) Weather data
                climate_info = get_monthly_averages_for_range(start_date, end_date)

                # 5) Display them in neat "boxes"
                st.write("---")
                st.subheader("Site Conditions")

                cS, cW = st.columns(2)
                with cS:
st.markdown(f"**SQM**: {sqm_val:.2f} mag/arcsec²  \n"
            f"**Bortle**: {bortle_val}")

                
                with cW:
                    if climate_info:
                        st.markdown(f"**{climate_info['title']}**  \n"
                                    f"Day Cloud: {climate_info['day_cloud']:.1f}%  \n"
                                    f"Night Cloud: {climate_info['night_cloud']:.1f}%  \n"
                                    f"Day Temp: {climate_info['day_temp']:.1f} °C  \n"
                                    f"Night Temp: {climate_info['night_temp']:.1f} °C  \n"
                                    f"Day Humidity: {climate_info['day_humid']:.1f}%  \n"
                                    f"Night Humidity: {climate_info['night_humid']:.1f}%  \n"
                                    f"Day Dew Pt: {climate_info['day_dew']:.1f} °C  \n"
                                    f"Night Dew Pt: {climate_info['night_dew']:.1f} °C")
                    else:
                        st.write("No historical climate data found.")

                # 6) Display the day-by-day mini calendar
                st.write("---")
                st.subheader("Day-by-Day Breakdown")
                df = pd.DataFrame(daily_data)
                # Rename columns for clarity
                df = df.rename(columns={
                    "date": "Date",
                    "astro_dark_hours": "Astro Hrs",
                    "moonless_hours": "Moonless Hrs",
                    "dark_start": "Dark Start",
                    "dark_end": "Dark End",
                    "moon_rise": "Moonrise",
                    "moon_set": "Moonset",
                    "moon_phase": "Phase"
                })
                st.table(df)  # or st.dataframe(df)

# Run
if __name__ == "__main__":
    main()
