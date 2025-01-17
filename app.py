############################
# app.py (Minimal Test)
############################

import streamlit as st
import datetime

def main():
    st.title("Date Range Single-Pop-Up Test")

    # Print the actual Streamlit version to confirm it's up-to-date
    st.write("**Running Streamlit version:**", st.__version__)

    # A note about how this test should behave
    st.write("""
    **Goal**: See if this `st.date_input` with a 2-element tuple keeps 
    the pop-up open until both dates are selected in one go.
    
    - If you only need **one** click total to pick both start and end,
      the environment is working as expected.
    - If it closes after you pick the first date, then the environment 
      or some other logic is forcing a re-render.
    """)

    # Minimal date range setup: from "today" to "today+7"
    today = datetime.date.today()
    default_range = (today, today + datetime.timedelta(days=7))

    # Here's the actual widget:
    picked_range = st.date_input(
        "Pick a 2-element date range",
        value=default_range,
        min_value=today,
        max_value=today + datetime.timedelta(days=365),
        format="MM.DD.YYYY",
        key="my_test_range"
    )

    # Show the result
    st.write("You picked:", picked_range)

if __name__ == "__main__":
    main()
