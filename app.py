if "progress_console" not in st.session_state:
st.session_state["progress_console"] = ""

    # Row for city + date
    row1_col1, row1_col2 = st.columns([2,1])
    with row1_col1:
        st.markdown("#### City Input")
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
                # user typed a new city
                # User typed a new city
coords = geocode_city(cval)
if coords:
st.session_state["lat"], st.session_state["lon"] = coords
st.session_state["city"] = cval
else:
st.warning("City not found or blocked. Check spelling or usage limits.")
            # else no changes
else:
st.write("City search is OFF")

    with row1_col2:
        st.markdown("#### Date Range")
        # === Modified Date Selector Starts Here ===
    with input_cols[1]:
        # Date Range Selector
dvals = st.date_input(
f"Pick up to {MAX_DAYS} days",
[st.session_state["start_date"], st.session_state["end_date"]],
@@ -354,12 +352,33 @@ def main():
st.session_state["start_date"], st.session_state["end_date"] = start, end
else:
st.warning("Please select either a single date or a valid date range.")
        # === Modified Date Selector Ends Here ===

    # Row for lat/lon
    st.markdown("#### Lat/Lon")
    row2_col1, row2_col2 = st.columns(2)
    with row2_col1:
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
            help="Select how precise the calculation should be. Higher minutes reduce calculation time but are less accurate."
        )
        # Tooltip explanation
        st.markdown(f"""
        <span title="Higher values like 5 or 15 minutes make the calculations faster but less precise, helping to save on computational resources. Lower values like 1 minute are more accurate but take longer, especially over many days.">
        &#9432;
        </span>
        """, unsafe_allow_html=True)

    # Row for Latitude and Longitude
    st.markdown("#### Coordinates")
    coord_cols = st.columns(2)
    with coord_cols[0]:
lat_in = st.number_input(
"Latitude",
value=st.session_state["lat"],
@@ -369,7 +388,7 @@ def main():
if abs(lat_in - st.session_state["lat"]) > 1e-8:
st.session_state["lat"] = lat_in

    with row2_col2:
    with coord_cols[1]:
lon_in = st.number_input(
"Longitude",
value=st.session_state["lon"],
@@ -379,7 +398,7 @@ def main():
if abs(lon_in - st.session_state["lon"]) > 1e-8:
st.session_state["lon"] = lon_in

    # No Moon
    # No Moon Checkbox
st.markdown("####")
no_moon = st.checkbox(
"No Moon",
@@ -411,44 +430,19 @@ def main():
else:
st.warning("City not found from reverse geocode.")

    # Selection for allowed deviation minutes and Progress Console in line
    st.markdown("####")
    row4_col1, row4_col2 = st.columns([1,2])
    with row4_col1:
        step_options = {
            "1 Minute": 1,
            "2 Minutes": 2,
            "5 Minutes": 5,
            "15 Minutes": 15,
            "30 Minutes": 30
        }
        step_minutes = st.selectbox(
            "Allowed Deviation Minutes",
            options=list(step_options.keys()),
            index=0,
            help="Select how precise the calculation should be. Higher minutes reduce calculation time but are less accurate."
        )
        # Add a tooltip explanation
        st.markdown(f"""
        <span title="Higher values like 5 or 15 minutes make the calculations faster but less precise, helping to save on computational resources. Lower values like 1 minute are more accurate but take longer, especially over many days.">
        &#9432;
        </span>
        """, unsafe_allow_html=True)

    with row4_col2:
        st.markdown("#### Progress Console")
        # Initialize the console display once with a unique key
        console_placeholder = st.empty()
        console_placeholder.text_area(
            "",
            value=st.session_state["progress_console"],
            height=100,
            max_chars=None,
            key="progress_console_display",
            disabled=True,
            help="Progress Console displaying calculation steps.",
            label_visibility="collapsed"
        )
    # Progress Console (Full Width)
    st.markdown("#### Progress Console")
    console_placeholder = st.empty()
    console_placeholder.text_area(
        "",
        value=st.session_state["progress_console"],
        height=150,
        max_chars=None,
        key="progress_console_display",
        disabled=True,
        help="Progress Console displaying calculation steps.",
        label_visibility="collapsed"
    )

# Calculate Button
st.markdown("####")
@@ -504,13 +498,13 @@ def main():
total_moonless = sum(d["moonless_hours"] for d in daily_data)

st.markdown("#### Results")
        cA, cB = st.columns(2)
        with cA:
        result_cols = st.columns(2)
        with result_cols[0]:
st.markdown(
f"<h3 style='text-align: center; color: green;'><b>Total Astronomical Darkness:</b> {total_astro:.2f} hrs</h3>",
unsafe_allow_html=True
)
        with cB:
        with result_cols[1]:
st.markdown(
f"<h3 style='text-align: center; color: green;'><b>Moonless Darkness:</b> {total_moonless:.2f} hrs</h3>",
unsafe_allow_html=True
@@ -533,11 +527,14 @@ def main():
st.dataframe(df)

# Update the console box with the latest debug messages
    if "progress_console_display_update" not in st.session_state:
        st.session_state["progress_console_display_update"] = ""

with console_placeholder.container():
console_placeholder.text_area(
"",
value=st.session_state["progress_console"],
            height=100,
            height=150,
max_chars=None,
key="progress_console_display_update",  # Ensure this key is unique and not reused elsewhere
disabled=True,
