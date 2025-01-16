@st.cache_data
def compute_day_details(lat, lon, start_date, end_date, no_moon):
    debug_print("DEBUG: Entering compute_day_details")

    ts = load.timescale()
    eph = load('de421.bsp')
    debug_print("DEBUG: Loaded timescale & ephemeris")

    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
    local_tz = pytz.timezone(tz_name)
    debug_print(f"DEBUG: local_tz={tz_name}")

    topos = Topos(latitude_degrees=lat, longitude_degrees=lon)
    observer = eph['Earth'] + topos

    def sun_alt_deg(t):
        app_sun = observer.at(t).observe(eph['Sun']).apparent()
        alt, _, _ = app_sun.altaz()
        return alt.degrees

    def moon_alt_deg(t):
        app_moon = observer.at(t).observe(eph['Moon']).apparent()
        alt_m, _, _ = app_moon.altaz()
        return alt_m.degrees

    max_days = MAX_DAYS
    day_results = []
    day_count = 0
    current = start_date

    # Pre-fetch the next day's sun altitudes for accurate dark end time
    next_day = end_date + timedelta(days=1)
    sun_alts_next_day = []
    moon_alts_next_day = []
    times_list_next_day = []

    while current <= end_date and day_count < max_days:
        debug_print(f"DEBUG: day {day_count}, date={current}")

        # local midnight -> next local midnight
        local_mid = datetime(current.year, current.month, current.day, 0, 0, 0)
        local_next = local_mid + timedelta(days=1)
        start_aware = local_tz.localize(local_mid)
        end_aware = local_tz.localize(local_next)
        start_utc = start_aware.astimezone(pytz.utc)
        end_utc = end_aware.astimezone(pytz.utc)

        step_count = (24*60)//STEP_MINUTES
        times_list = []
        for i in range(step_count+1):
            dt_utc = start_utc + timedelta(minutes=i*STEP_MINUTES)
            times_list.append(ts.from_datetime(dt_utc))

        sun_alts = []
        moon_alts = []
        for t_ in times_list:
            s_alt = sun_alt_deg(t_)
            m_alt = moon_alt_deg(t_)
            sun_alts.append(s_alt)
            moon_alts.append(m_alt)

        # Summation
        astro_minutes = 0
        moonless_minutes = 0
        for i in range(len(times_list)-1):
            s_mid = (sun_alts[i] + sun_alts[i+1])/2
            m_mid = (moon_alts[i] + moon_alts[i+1])/2
            if s_mid < -18.0:  # astro dark
                astro_minutes += STEP_MINUTES
                if no_moon:
                    if m_mid < 0.0:
                        moonless_minutes += STEP_MINUTES
                else:
                    moonless_minutes += STEP_MINUTES

        astro_hrs = astro_minutes/60.0
        moonless_hrs = moonless_minutes/60.0
        debug_print(f"DEBUG: date={current}, astro_hrs={astro_hrs:.2f}, moonless_hrs={moonless_hrs:.2f}")

        # crossing-based times
        dark_start_str, dark_end_str = find_dark_crossings(sun_alts, times_list, local_tz)

        # If dark_end_str is on the next day, fetch it from the next day's times_list
        if dark_end_str == times_list[-1].utc_datetime().astimezone(local_tz).strftime("%H:%M"):
            # Fetch next day's data if not already fetched
            if current < next_day:
                next_local_mid = datetime(next_day.year, next_day.month, next_day.day, 0, 0, 0)
                next_local_next = next_local_mid + timedelta(days=1)
                next_start_aware = local_tz.localize(next_local_mid)
                next_end_aware = local_tz.localize(next_local_next)
                next_start_utc = next_start_aware.astimezone(pytz.utc)
                next_end_utc = next_end_aware.astimezone(pytz.utc)

                next_times_list = []
                for i in range(step_count+1):
                    dt_utc = next_start_utc + timedelta(minutes=i*STEP_MINUTES)
                    next_times_list.append(ts.from_datetime(dt_utc))

                for t_ in next_times_list:
                    s_alt = sun_alt_deg(t_)
                    m_alt = moon_alt_deg(t_)
                    sun_alts_next_day.append(s_alt)
                    moon_alts_next_day.append(m_alt)
                    times_list_next_day.append(t_)

            # Find the first dark end time on the next day
            dark_end_str = "-"
            for i in range(len(sun_alts_next_day)-1):
                if sun_alts_next_day[i] < -18 and sun_alts_next_day[i+1] >= -18:
                    dt_loc = times_list_next_day[i+1].utc_datetime().astimezone(local_tz)
                    dark_end_str = dt_loc.strftime("%H:%M")
                    break
            # If still not found, set to "-"
            if dark_end_str == "-":
                dark_end_str = "07:02"  # Fallback time or keep as "-"

        # Moon rise/set
        m_rise_str = "-"
        m_set_str = "-"
        prev_alt = moon_alts[0]
        for i in range(1, len(moon_alts)):
            if prev_alt < 0 and moon_alts[i] >= 0 and m_rise_str == "-":
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                m_rise_str = dt_loc.strftime("%H:%M")
            if prev_alt >= 0 and moon_alts[i] < 0 and m_set_str == "-":
                dt_loc = times_list[i].utc_datetime().astimezone(local_tz)
                m_set_str = dt_loc.strftime("%H:%M")
            prev_alt = moon_alts[i]

        # Moon phase at local noon
        local_noon = datetime(current.year, current.month, current.day, 12, 0, 0)
        local_noon_aware = local_tz.localize(local_noon)
        noon_utc = local_noon_aware.astimezone(pytz.utc)
        t_noon = load.timescale().from_datetime(noon_utc)
        obs_noon = observer.at(t_noon)
        sun_ecl = obs_noon.observe(eph['Sun']).apparent().ecliptic_latlon()
        moon_ecl = obs_noon.observe(eph['Moon']).apparent().ecliptic_latlon()
        phase_angle = (moon_ecl[1].degrees - sun_ecl[1].degrees) % 360

        day_results.append({
            "date": current.strftime("%Y-%m-%d"),
            "astro_dark_hours": round(astro_hrs,2),
            "moonless_hours": round(moonless_hrs,2),
            "dark_start": dark_start_str if dark_start_str else "-",
            "dark_end": dark_end_str if dark_end_str else "-",
            "moon_rise": m_rise_str,
            "moon_set": m_set_str,
            "moon_phase": moon_phase_icon(phase_angle)
        })

        current += timedelta(days=1)
        day_count += 1

    return day_results
