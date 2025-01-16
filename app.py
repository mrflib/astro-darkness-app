import streamlit as st
import requests
import pandas as pd
from datetime import date, datetime, timedelta
from skyfield.api import Topos, load
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium

# -------------------------------------------------------------------
# PAGE CONFIG: Single-column, mobile-friendly
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",
    layout="centered"  # single column, more phone-friendly
)

# -------------------------------------------------------------------
# LOCATION & WEATHER HELPERS
# -------------------------------------------------------------------
def get_ip_location():
    """
    Approx. user location from IP (ipapi.co).
    Returns (lat, lon) or (None, None).
    """
    try:
        r = requests.get("https://ipapi.co/json/")
        if r.status_code == 200:
            data = r.json()
            return (data.get("latitude"), data.get("longitude"))
    except:
        pass
    return (None, None)

def geocode_place(place_name):
    geolocator = Nominatim(user_agent="astro_app")
    try:
        loc = geolocator.geocode(place_name)
        if loc:
            return (loc.latitude, loc.longitude)
    except:
        pass
    return None

def reverse_geocode(lat, lon):
    geolocator = Nominatim(user_agent="astro_app")
    try:
        loc = geolocator.reverse((lat, lon), language='en')
        if loc and loc.address:
            addr = loc.raw.get('address', {})
            city_guess = addr.get('city') or addr.get('town') or addr.get('village') or loc.address
            return city_guess
    except:
        pass
    return ""

# -------------------------------------------------------------------
# HISTORICAL MONTHLY WEATHER (LAST 3 YEARS)
# We call the Open-Meteo "archive" for each of the last 3 years,
# restricting the query to the user-chosen month.
# We'll compute average day/night temp, humidity, cloudcover, dew, wind speed.
# -------------------------------------------------------------------
def get_monthly_weather_3year_avg(lat, lon, month):
    """
    For the chosen 'month' (1..12), get data from the last 3 years.
    We'll do year = current_year-1, year = current_year-2, year = current_year-3 
    (or pick whichever 3 you want).
    Then average them.

    We return a dict with:
      'day_temp', 'night_temp', 'day_cloud', 'night_cloud',
      'day_humidity', 'night_humidity', 'day_dew', 'night_dew',
      'day_wind', 'night_wind',
      'title' => e.g. "Historical Weather for January"
    or None if no data available.
    """
    # We'll pick: last 3 complete years from now
    # E.g. if today is 2025 => we fetch 2022, 2023, 2024 data. 
    # But that might be future if user is in 2023. Let's keep it simpler:
    # We'll just do the last 3 known full years (like 2020, 2021, 2022).
    # You can tweak if you want a different approach.

    # Hardcode a small range for demonstration
    years_to_fetch = [2020, 2021, 2022]

    # We'll store day vs night arrays across all 3 years
    day_temp_vals, night_temp_vals = [], []
    day_cloud_vals, night_cloud_vals = [], []
    day_hum_vals, night_hum_vals = [], []
    day_dew_vals, night_dew_vals = [], []
    day_wind_vals, night_wind_vals = [], []

    for y in years_to_fetch:
        # Construct start/end for that month
        start_d = date(y, month, 1)
        # end of that month
        if month == 12:
            end_d = date(y, 12, 31)
        else:
            end_d = date(y, month+1, 1) - timedelta(days=1)

        # Query Open-Meteo archive
        url = (
            "https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={lat}&longitude={lon}"
            f"&start_date={start_d}&end_date={end_d}"
            "&hourly=temperature_2m,relativehumidity_2m,dewpoint_2m,cloudcover,windspeed_10m"
            "&timezone=auto"
        )
        resp = requests.get(url)
        if resp.status_code != 200:
            continue
        data = resp.json()
        if "hourly" not in data or "time" not in data["hourly"]:
            continue

        times = data["hourly"]["time"]
        temps = data["hourly"]["temperature_2m"]
        hums = data["hourly"]["relativehumidity_2m"]
        clouds = data["hourly"]["cloudcover"]
        dewps = data["hourly"]["dewpoint_2m"]
        winds = data["hourly"]["windspeed_10m"]

        # separate day vs night (6..18 local = day)
        for i, t_str in enumerate(times):
            try:
                t_dt = datetime.fromisoformat(t_str)
                hr = t_dt.hour
            except:
                continue
            temperature = temps[i]
            humidity = hums[i]
            cloud = clouds[i]
            dewpt = dewps[i]
            windspd = winds[i]

            if 6 <= hr < 18:
                day_temp_vals.append(temperature)
                day_cloud_vals.append(cloud)
                day_hum_vals.append(humidity)
                day_dew_vals.append(dewpt)
                day_wind_vals.append(windspd)
            else:
                night_temp_vals.append(temperature)
                night_cloud_vals.append(cloud)
                night_hum_vals.append(humidity)
                night_dew_vals.append(dewpt)
                night_wind_vals.append(windspd)

    def avg(arr):
        return (sum(arr)/len(arr)) if arr else None

    # If we have zero data across all 3 years => None
    if not day_temp_vals and not night_temp_vals:
        return None

    return {
        "title": f"Historical Weather for {start_d.strftime('%B')}",
        "day_temp": avg(day_temp_vals),
        "night_temp": avg(night_temp_vals),
        "day_cloud": avg(day_cloud_vals),
        "night_cloud": avg(night_cloud_vals),
        "day_humidity": avg(day_hum_vals),
        "night_humidity": avg(night_hum_vals),
        "day_dew": avg(day_dew_vals),
        "night_dew": avg(night_dew_vals),
        "day_wind": avg(day_wind_vals),
        "night_wind": avg(night_wind_vals)
    }

# -------------------------------------------------------------------
# ASTRONOMY: Day-by-day astro darkness with Skyfield
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

def compute_daily_details(lat, lon, start_date, end_date, no_moon=False):
    """
    Returns a list of daily dicts with astro darkness & moon times.
    Limit to 14 days. 10-min increments for sun/moon altitude checks.
    """
    ts = load.timescale()
    eph = load('de421.bsp')
    location = Topos(lat, lon)
    sun = eph['Sun']
    moon = eph['Moon']
    observer = eph['Earth'] + location

    max_days = 14
    day_count = 0
    results = []
    current = start_date

    while current <= end_date and day_count < max_days:
        step_minutes = 10
        n_steps = (24*60)//step_minutes
        day_start = ts.utc(current.year, current.month, current.day, 0, 0, 0)
        
        sun_alts, moon_alts, phases = [], [], []
        times_list = [day_start.tt + (i*step_minutes)/(24*60) for i in range(n_steps+1)]

        for t_tt in times_list:
            t = ts.tt_jd(t_tt)
            app_sun = observer.at(t).observe(sun).apparent()
            alt_sun, _, _ = app_sun.altaz()
            sun_deg = alt_sun.degrees

            app_moon = observer.at(t).observe(moon).apparent()
            alt_moon, _, _ = app_moon.altaz()
            moon_deg = alt_moon.degrees

            # Phase angle
            sun_ecl = observer.at(t).observe(sun).apparent().ecliptic_latlon()
            moon_ecl = observer.at(t).observe(moon).apparent().ecliptic_latlon()
            ang = (moon_ecl[1].degrees - sun_ecl[1].degrees)%360

            sun_alts.append(sun_deg)
            moon_alts.append(moon_deg)
            phases.append(ang)

        # Summation approach
        astro_minutes, moonless_minutes = 0, 0
        dark_start_str, dark_end_str = None, None
        darkness_started = False
        for i in range(n_steps):
            s_mid = (sun_alts[i] + sun_alts[i+1])/2
            m_mid = (moon_alts[i] + moon_alts[i+1])/2
            if s_mid < -18.0:
                astro_minutes += step_minutes
                if no_moon:
                    if m_mid < 0.0:
                        moonless_minutes += step_minutes
                else:
                    moonless_minutes += step_minutes
                
                if not darkness_started:
                    darkness_started = True
                    hh = (i*step_minutes)//60
                    mm = (i*step_minutes)%60
                    dark_start_str = f"{hh:02d}:{mm:02d}"
            else:
                if darkness_started:
                    hh = (i*step_minutes)//60
                    mm = (i*step_minutes)%60
                    dark_end_str = f"{hh:02d}:{mm:02d}"
                    darkness_started = False
        if darkness_started and not dark_end_str:
            dark_end_str = "24:00"

        # Moon rise/set
        moon_rise_str, moon_set_str = None, None
        prev_alt = moon_alts[0]
        for i in range(1, len(moon_alts)):
            curr_alt = moon_alts[i]
            if prev_alt<0 and curr_alt>=0 and not moon_rise_str:
                hh = (i*step_minutes)//60
                mm = (i*step_minutes)%60
                moon_rise_str = f"{hh:02d}:{mm:02d}"
            if prev_alt>=0 and curr_alt<0 and not moon_set_str:
                hh = (i*step_minutes)//60
                mm = (i*step_minutes)%60
                moon_set_str = f"{hh:02d}:{mm:02d}"
            prev_alt = curr_alt

        # Middle of day for phase
        mid_phase = phases[n_steps//2]
        icon = moon_phase_icon(mid_phase)

        results.append({
            "date": current.strftime("%Y-%m-%d"),
            "astro_dark_hours": round(astro_minutes/60,2),
            "moonless_hours": round(moonless_minutes/60,2),
            "dark_start": dark_start_str if dark_start_str else "-",
            "dark_end": dark_end_str if dark_end_str else "-",
            "moon_rise": moon_rise_str if moon_rise_str else "-",
            "moon_set": moon_set_str if moon_set_str else "-",
            "moon_phase": icon
        })

        current += timedelta(days=1)
        day_count+=1

    return results


# -------------------------------------------------------------------
# MAIN APP
# -------------------------------------------------------------------
def main():
    st.title("Astronomical Darkness Calculator")
    st.write("Find how many hours of true night you get, anywhere in the world.")

    # Session defaults
    if "lat" not in st.session_state:
        st.session_state["lat"] = 51.5074
    if "lon" not in st.session_state:
        st.session_state["lon"] = -0.1278
    if "city" not in st.session_state:
        st.session_state["city"] = "London"

    # ---- LOCATION + DATE RANGE in single column, minimal scrolling ----
    st.subheader("Setup")

    # Row 1: City, IP, lat/lon
    row1_col1, row1_col2, row1_col3 = st.columns([1.5, 1, 1])
    with row1_col1:
        city_input = st.text_input("City (optional)", value=st.session_state["city"], help="If used, lat/lon will update.")
    with row1_col2:
        if st.button("Use My IP"):
            ip_lat, ip_lon = get_ip_location()
            if ip_lat and ip_lon:
                st.session_state["lat"] = ip_lat
                st.session_state["lon"] = ip_lon
                # reverse geocode if possible
                guessed = reverse_geocode(ip_lat, ip_lon)
                if guessed:
                    st.session_state["city"] = guessed
                st.success(f"Set lat={ip_lat:.4f}, lon={ip_lon:.4f}")
            else:
                st.warning("Could not get location from IP.")
    with row1_col3:
        st.write(" ")  # empty placeholder

    # If city changed
    if city_input != st.session_state["city"]:
        st.session_state["city"] = city_input
        coords = geocode_place(city_input)
        if coords:
            st.session_state["lat"], st.session_state["lon"] = coords
        else:
            st.warning("City not found. Check spelling or specify lat/lon manually.")

    # Row 2: lat, lon
    row2_col1, row2_col2 = st.columns(2)
    with row2_col1:
        new_lat = st.number_input("Latitude", value=st.session_state["lat"], format="%.6f")
    with row2_col2:
        new_lon = st.number_input("Longitude", value=st.session_state["lon"], format="%.6f")

    if abs(new_lat - st.session_state["lat"])>1e-9 or abs(new_lon - st.session_state["lon"])>1e-9:
        st.session_state["lat"] = new_lat
        st.session_state["lon"] = new_lon
        # Optionally, reverse geocode to city
        city_guess = reverse_geocode(new_lat, new_lon)
        if city_guess:
            st.session_state["city"] = city_guess

    # Row 3: Date range, No Moon
    row3_col1, row3_col2 = st.columns([1.5, 1])
    with row3_col1:
        d_range = st.date_input("Date Range (Max 14 days)", [date(2023,1,1), date(2023,1,7)])
        if len(d_range)==1:
            start_d = d_range[0]
            end_d = d_range[0]
        else:
            start_d, end_d = d_range[0], d_range[-1]
    with row3_col2:
        no_moon = st.checkbox("No Moon", value=False, help="Exclude times when the Moon is above the horizon.")

    # Optional Expander: Map
    with st.expander("Pick on Map (optional)"):
        st.write("Click on the map to choose location:")
        default_loc = [st.session_state["lat"], st.session_state["lon"]]
        my_map = folium.Map(location=default_loc, zoom_start=4)
        folium.TileLayer("OpenStreetMap").add_to(my_map)
        my_map.add_child(folium.LatLngPopup())
        map_data = st_folium(my_map, width=600, height=400)
        if map_data and map_data['last_clicked'] is not None:
            clat = map_data['last_clicked']['lat']
            clng = map_data['last_clicked']['lng']
            st.session_state["lat"] = clat
            st.session_state["lon"] = clng
            city_guess = reverse_geocode(clat, clng)
            if city_guess:
                st.session_state["city"] = city_guess
            st.info(f"Clicked lat={clat:.4f}, lon={clng:.4f}")

    # Calculate button
    if st.button("Calculate"):
        if start_d> end_d:
            st.error("Start date must be <= end date.")
            return
        
        # 1) Astronomy
        daily_data = compute_daily_details(st.session_state["lat"], st.session_state["lon"], start_d, end_d, no_moon=no_moon)
        if not daily_data:
            st.warning("No data. Possibly date range > 14 days.")
            return

        total_astro = sum(d["astro_dark_hours"] for d in daily_data)
        total_moonless = sum(d["moonless_hours"] for d in daily_data)

        # Show results
        st.write("---")
        st.subheader("Results")

        # Darkness boxes
        colA, colB = st.columns(2)
        with colA:
            st.success(f"Total Astronomical Darkness: {total_astro:.2f} hrs")
        with colB:
            st.success(f"Moonless Darkness: {total_moonless:.2f} hrs")

        # 2) Historical weather for month (last 3 yrs)
        # We'll just take the start_d month as the "month of interest."
        # If user picks a range that spans multiple months, this is simplified.
        selected_month = start_d.month
        weather_3yr = get_monthly_weather_3year_avg(st.session_state["lat"], st.session_state["lon"], selected_month)

        # Display day-by-day table
        st.subheader("Day-by-Day Breakdown")
        df = pd.DataFrame(daily_data)
        df = df.rename(columns={
            "date": "Date",
            "astro_dark_hours": "Astro (hrs)",
            "moonless_hours": "Moonless (hrs)",
            "dark_start": "Dark Start",
            "dark_end": "Dark End",
            "moon_rise": "Moonrise",
            "moon_set": "Moonset",
            "moon_phase": "Phase"
        })
        st.table(df)

        # Weather box
        if weather_3yr:
            st.write("---")
            st.subheader(weather_3yr['title'])  # e.g. "Historical Weather for January"
            day_temp = weather_3yr['day_temp']
            night_temp = weather_3yr['night_temp']
            day_cld = weather_3yr['day_cloud']
            night_cld = weather_3yr['night_cloud']
            day_hum = weather_3yr['day_humidity']
            night_hum = weather_3yr['night_humidity']
            day_dew = weather_3yr['day_dew']
            night_dew = weather_3yr['night_dew']
            day_wind = weather_3yr['day_wind']
            night_wind = weather_3yr['night_wind']

            # Using two columns for day vs night
            wcol1, wcol2 = st.columns(2)
            with wcol1:
                st.markdown(f"**Day Temp**: {day_temp:.1f} °C" if day_temp else "Day Temp: N/A")
                st.markdown(f"**Day Cloud**: {day_cld:.1f}%" if day_cld else "Day Cloud: N/A")
                st.markdown(f"**Day Humidity**: {day_hum:.1f}%" if day_hum else "Day Humidity: N/A")
                st.markdown(f"**Day Dew Pt**: {day_dew:.1f} °C" if day_dew else "Day Dew Pt: N/A")
                st.markdown(f"**Day Wind**: {day_wind:.1f} m/s" if day_wind else "Day Wind: N/A")

            with wcol2:
                st.markdown(f"**Night Temp**: {night_temp:.1f} °C" if night_temp else "Night Temp: N/A")
                st.markdown(f"**Night Cloud**: {night_cld:.1f}%" if night_cld else "Night Cloud: N/A")
                st.markdown(f"**Night Humidity**: {night_hum:.1f}%" if night_hum else "Night Humidity: N/A")
                st.markdown(f"**Night Dew Pt**: {night_dew:.1f} °C" if night_dew else "Night Dew Pt: N/A")
                st.markdown(f"**Night Wind**: {night_wind:.1f} m/s" if night_wind else "Night Wind: N/A")

        else:
            st.write("---")
            st.subheader("Historical Weather for this Month")
            st.write("No data found for the last 3 years (maybe location out of coverage?).")


if __name__ == "__main__":
    main()
