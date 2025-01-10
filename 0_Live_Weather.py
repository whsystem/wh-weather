import streamlit as st
from streamlit_folium import st_folium
import folium
import pandas as pd
from scripts.utils import connect_to_weather_stations, get_color_scheme, configure_sidebar

st.set_page_config(page_title="Live Weather", page_icon="🌤️", layout="wide")

# Sidebar configuration
configure_sidebar()

# Initialize session state for station data
if "station_status" not in st.session_state:
    connect_to_weather_stations()

# Check if data is available in session state
if "station_status" in st.session_state:
    station_status = st.session_state["station_status"]
    station_count = st.session_state["station_count"]

    # Ensure Wind Speed (m/s) column contains numeric data before conversion
    if "Wind Speed (m/s)" in station_status.columns:
        station_status["Wind Speed (m/s)"] = pd.to_numeric(station_status["Wind Speed (m/s)"], errors="coerce")  # Convert to numeric, set invalid values to NaN
        station_status["Wind Speed (km/h)"] = station_status["Wind Speed (m/s)"] * 3.6  # Convert to km/h


    st.title(f"Live Weather")

    most_recent_date = pd.to_datetime(station_status['Last Communication Date']).max()

    st.success(f"Successfully connected to {station_count} stations. Last update **{most_recent_date}** local time.")
       
    st.subheader("Weather Map")

    # Select the indicator to display
    indicator_field = st.radio(
        "Select an indicator to display:",
        [
            "Air Temperature (°C)", 
            "Relative Humidity (%)", 
            "Rain in Last Hour (mm)",  # Updated label for the button
            "Wind Speed (km/h)"
        ]
    )

    # Map the button label back to the original field name for logic
    indicator_mapping = {
        "Air Temperature (°C)": "Air Temperature (°C)",
        "Relative Humidity (%)": "Relative Humidity (%)",
        "Rain in Last Hour (mm)": "Rain Last (mm)",  # Logic uses the original field name
        "Wind Speed (km/h)": "Wind Speed (km/h)"
    }

    # Use the mapped field name for the logic
    indicator = indicator_mapping[indicator_field]

    
    map_center_lat = station_status["Latitude"].mean()
    map_center_lon = station_status["Longitude"].mean()

    # Apply a downward offset to nudge the map down
    nudge = 0.05
    adjusted_map_center_lat = map_center_lat + nudge  # Subtract to nudge down

    # Create a map with the bounds set dynamically and using a tileset with English place names
    m = folium.Map(
        location=[adjusted_map_center_lat, map_center_lon], 
        zoom_start=9,
        tiles="CartoDB Voyager"  # Use CartoDB Positron tiles for English place names
    )

    # Add markers for each station
    for _, station in station_status.iterrows():
        value = station[indicator] if indicator != "Wind Speed (km/h)" else station["Wind Speed (m/s)"]

        # Ensure value is numeric; set to NaN if not
        try:
            value = float(value)  # Convert value to float
        except (ValueError, TypeError):
            value = float("nan")  # Set value to NaN if conversion fails

        if pd.isna(value):  # Check for NaN values
            display_value = "-"  # Use "-" for invalid or missing values
        else:
            display_value = (
                int(round(value * 3.6, 0)) if indicator == "Wind Speed (km/h)" else int(round(value, 0))
            )

        color = get_color_scheme(value, indicator.replace(" (km/h)", " (m/s)")) if not pd.isna(value) else "grey"

        # Determine text color based on circle color
        text_color = "white" if color in ["blue", "darkblue", "darkred"] else "black"

        # Add a CircleMarker with SVG icon for the station
        folium.Marker(
            location=[station['Latitude'], station['Longitude']],
            tooltip=f"{station['Custom Name']}<br>{indicator}: {display_value}",
            icon=folium.DivIcon(
                html=f"""
                <div style="position: relative; transform: translate(-50%, -50%);">
                    <svg xmlns="http://www.w3.org/2000/svg" height="40" width="40" viewBox="0 0 40 40">
                        <circle cx="20" cy="20" r="15" style="fill:{color};stroke:black;stroke-width:1;fill-opacity:0.7;" />
                        <text x="20" y="25" text-anchor="middle" fill="{text_color}" font-size="14" font-weight="bold">{display_value}</text>
                    </svg>
                </div>
                """
            ),
        ).add_to(m)



    # Display the map
    st_folium(m, width=1200, height=600)

    st.subheader("Detailed Weather Station Status")

    # Allow user to select columns for display
    all_columns = station_status.columns.tolist()
    default_columns = [
        'Custom Name', 'Coordinates (Latitude, Longitude)',
        'Air Temperature (°C)', 'Relative Humidity (%)', 'Wind Speed (km/h)',  # Updated to km/h
        'Last Communication Date'
    ]

    # Ensure Wind Speed (km/h) is in all_columns
    if "Wind Speed (km/h)" not in all_columns:
        all_columns.append("Wind Speed (km/h)")

    selected_columns = st.multiselect(
        "Select columns to display:",
        options=all_columns,
        default=[col for col in default_columns if col in all_columns],
    )

    # Display DataFrame with selected columns
    if selected_columns:
        # Convert Wind Speed (m/s) to km/h for DataFrame display
        df_to_display = station_status[selected_columns].copy()
        if "Wind Speed (km/h)" in selected_columns:
            df_to_display["Wind Speed (km/h)"] = station_status["Wind Speed (m/s)"] * 3.6

        # Reset the index and adjust it to start from 1
        df_to_display.index = df_to_display.index + 1
        st.dataframe(df_to_display)
    else:
        st.warning("Please select at least one column to display.")
