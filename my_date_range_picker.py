# my_date_range_picker.py
import streamlit as st
from datetime import date

def my_date_range_picker(
    label: str = "Select Date Range",
    default_start: date = date.today(),
    default_end: date = date.today(),
    max_days: int = 30,
    key: str = None
):
    """
    A minimal function that displays two st.date_input calls side by side
    so it appears like a single "range" widget. Returns (start_date, end_date).
    """
    # We can put them on one row by using st.columns(2)
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"**{label}**")
        start_val = st.date_input(
            "Start date",
            value=default_start,
            key=f"{key}-start" if key else None
        )

    with col2:
        st.write(" ")  # just for spacing
        end_val = st.date_input(
            "End date",
            value=default_end,
            key=f"{key}-end" if key else None
        )

    # Optional: enforce a max range
    delta_days = (end_val - start_val).days + 1
    if delta_days > max_days:
        st.warning(f"Please select a range of up to {max_days} days.")
    return (start_val, end_val)
