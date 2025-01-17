# my_date_picker_component.py

import streamlit.components.v1 as components
import os
from datetime import datetime
from enum import Enum

# We embed a tiny “frontend” that you can build or customize if needed.
# For now, let's assume we have a minimal static build that renders a date-range UI.
# We'll declare a component that expects certain JSON props and returns a JSON
# with the chosen start/end as strings.

# 1) Possibly create a build folder with your own React/HTML code,
#    or embed a minimal HTML if you want to do it purely inline.

# For demonstration, let's keep the "release" approach:
_RELEASE = True

class PickerType(Enum):
    DATE = "date"
    # You could add TIME, WEEK, MONTH, etc. if you want more modes.

if not _RELEASE:
    # Dev mode: run a local server for the JS/React, etc.
    _component_func = components.declare_component(
        "my_date_range_picker",
        url="http://localhost:3001",
    )
else:
    # Build folder approach
    _build_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend_build")
    _component_func = components.declare_component(
        "my_date_range_picker",
        path=_build_dir
    )

def my_date_range_picker(
    label: str = "Select a date range",
    start_date: datetime = None,
    end_date: datetime = None,
    key: str = None,
):
    """
    Minimal function to call our custom date-range widget.
    Returns (start_str, end_str) or None if no input yet.

    In your app, you'll parse the returned strings to datetime objects.
    """
    if start_date is None:
        start_date = datetime.now()
    if end_date is None:
        end_date = datetime.now()

    # Convert to strings (e.g. ISO8601) so the front-end can parse
    start_iso = start_date.isoformat()
    end_iso   = end_date.isoformat()

    result = _component_func(
        label=label,
        start=start_iso,
        end=end_iso,
        key=key
    )
    # `result` is typically either None or a dict with 'start'/'end' keys
    if not result:
        return None
    return (result.get("start"), result.get("end"))
