import streamlit as st
from datetime import date, datetime, timedelta
from skyfield.api import Topos, load

# ------------------------------------------------------
# Set page config (title and favicon)
# ------------------------------------------------------
st.set_page_config(
    page_title="Astronomical Darkness Calculator",
    page_icon="🌑",  # or a path to a favicon file
    layout="centered",  # or "wide"
)

# A little CSS to style things if desired.
# Example: make the main title bigger, adjust spacing, etc.
st.markdown("""
    <style>
    .main-title {
        font-family: 'Helvetica Neue', sans-serif;
        color: #2D2D2D;
        font-weight: 600;
        margin-bottom: 0.4em;
    }
    .sub-title {
        color: #4B8BBE;
        font-size: 1.1rem;
        margin-top: 0;
        margin-bottom: 1em;
    }
    .stApp {
        background-color: #F5F5F5;  /* matches our theme background */
    }
    .info-box {
        background-color: #FFFFFF;
        padding: 1rem;
        margin-bottom: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.15);
    }
    .info-box h2 {
        margin-top: 0;
    }
    </style>
""", unsafe_allow_html=True)


# ------------------------------------------------------
# Computation: Astronomical Darkness
# ------------------------------------------------------
def get_astronomical_darkness_hours(lat, lon, start_date, end_date, no_moon=False):
    """
    Calculate hours of astronomical darkness (Sun < -18 deg)
    for a location between start_date and end_date.
    If no_moon=True, subtract any time the moon is above horizon.
    """
    ts = load.timescale()
    eph = load('de421.bsp')
    location = Topos(latitude_degrees=lat, longitude_degrees=lon)

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
            midpoint_sun_alt = (sun_altitudes[i] + sun_altitudes[i+1]) / 2.0
            midpoint_moon_alt = (moon_altitudes[i] + moon_altitudes[i+1]) / 2.0

            if midpoint_sun_alt < -18.0:
                darkness_minutes += step_minutes
                if no_moon:
                    if midpoint_moon_alt < 0.0:
                        darkness_no_moon_minutes += step_minutes
                else:
                    darkness_no_moon_minutes += step_minutes

        total_darkness_hours += (darkness_minutes / 60.0)
        total_darkness_with_no_moon_hours += (darkness_no_moon_minutes / 60.0)

        current_date += timedelta(days=1)
        days_counted += 1

    if no_moon:
        return total_darkness_with_no_moon_hours
    else:
        return total_darkness_hours


# ------------------------------------------------------
# Streamlit App Layout
# ------------------------------------------------------
def main():
    # Main Title
    st.markdown("<h1 class='main-title'>Astronomical Darkness Calculator</h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-title'>Find how many hours of true night you get, anywhere in the world.</p>", unsafe_allow_html=True)

    # We can group instructions/info in a "box":
    with st.container():
        st.markdown("<div class='info-box'>", unsafe_allow_html=True)
        st.markdown("""
        <h2>How to Use</h2>
        <ol>
          <li>Enter your latitude and longitude.</li>
          <li>Select a date range (up to 14 days).</li>
          <li>Check "No Moon" if you want to exclude times when the Moon is above the horizon.</li>
          <li>Click "Calculate" to see how many hours of darkness you get!</li>
        </ol>
        """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # Layout: let's place lat/lon in columns
    col1, col2 = st.columns(2)
    with col1:
        lat = st.number_input("Latitude", value=51.5074, format="%.4f")
    with col2:
        lon = st.number_input("Longitude", value=-0.1278, format="%.4f")

    # Another section for date range + "No Moon"
    st.markdown("<div class='info-box'>", unsafe_allow_html=True)
    st.subheader("Date Range Selection")
    date_range = st.date_input("Select a date range", [date(2025, 1, 1), date(2025, 1, 7)])
    no_moon = st.checkbox("No Moon", value=False)
    st.markdown("</div>", unsafe_allow_html=True)

    # Parse the date range
    if len(date_range) == 1:
        start_date = date_range[0]
        end_date = date_range[0]
    elif len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = min(date_range)
        end_date = max(date_range)

    # Calculate button
    if st.button("Calculate"):
        if start_date > end_date:
            st.error("Start date must be before end date.")
        else:
            start_dt = datetime(start_date.year, start_date.month, start_date.day)
            end_dt   = datetime(end_date.year, end_date.month, end_date.day)

            # Core calculation
            total_darkness = get_astronomical_darkness_hours(lat, lon, start_dt, end_dt, no_moon=False)

            if no_moon:
                total_no_moon = get_astronomical_darkness_hours(lat, lon, start_dt, end_dt, no_moon=True)
                st.success(
                    f"**Total astronomical darkness** (Sun < -18°): **{total_darkness:.2f} hours**\n\n"
                    f"**Moonless darkness**: **{total_no_moon:.2f} hours**"
                )
            else:
                st.success(
                    f"**Total astronomical darkness** (Sun < -18°): **{total_darkness:.2f} hours**"
                )

# Run the app
if __name__ == "__main__":
    main()
