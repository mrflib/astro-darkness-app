# Row for City Input, Date Range, and Deviation (Mins)
st.markdown("#### Inputs")
input_cols = st.columns(3)
with input_cols[0]:
    if USE_CITY_SEARCH:
        cval = st.text_input(
            "City (optional)",
            value=st.session_state["city"],
            help="Enter a city name to look up lat/lon from LocationIQ (e.g. 'London')."
        )
        if cval != st.session_state["city"]:
            # User typed a new city
            coords = geocode_city(cval)
            if coords:
                st.session_state["lat"], st.session_state["lon"] = coords
                st.session_state["city"] = cval
            else:
                st.warning("City not found or blocked. Check spelling or usage limits.")
    else:
        st.write("City search is OFF")

with input_cols[1]:
    # Date Range Selector
    dvals = st.date_input(
        f"Pick up to {MAX_DAYS} days",
        [st.session_state["start_date"], st.session_state["end_date"]],
        help=f"Select a date range of up to {MAX_DAYS} days."
    )
    if len(dvals) == 1:
        st.session_state["start_date"] = dvals[0]
        st.session_state["end_date"] = dvals[0]
    elif len(dvals) == 2:
        start, end = dvals
        delta_days = (end - start).days + 1
        if delta_days > MAX_DAYS:
            adjusted_end = start + timedelta(days=MAX_DAYS -1)
            st.warning(f"Selected range exceeds {MAX_DAYS} days. Adjusting the end date to {adjusted_end}.")
            st.session_state["start_date"] = start
            st.session_state["end_date"] = adjusted_end
        else:
            st.session_state["start_date"], st.session_state["end_date"] = start, end
    else:
        st.warning("Please select either a single date or a valid date range.")

with input_cols[2]:
    # Allowed Deviation Minutes Selector
    step_options = {
        "1 Minute": 1,
        "2 Minutes": 2,
        "5 Minutes": 5,
        "15 Minutes": 15,
        "30 Minutes": 30
    }
    step_minutes = st.selectbox(
        "Deviation (Mins)",
        options=list(step_options.keys()),
        index=0,
        help="This setting determines how precise the calculation times are, measured in minutes. Higher values (like 5 or 15 minutes) make calculations faster but less exact, saving processing time. Lower values** (like 1 minute) make calculations more accurate but take longer, especially for longer date ranges."
    )
    # Tooltip explanation
    st.markdown(f"""
    <span title="Higher values like 5 or 15 minutes make the calculations faster but less precise, helping to save on computational resources. Lower values like 1 minute are more accurate but take longer, especially over many days.">
    &#9432;
    </span>
    """, unsafe_allow_html=True)
