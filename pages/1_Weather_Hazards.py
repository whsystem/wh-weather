import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from scripts.utils import configure_sidebar, connect_to_weather_stations, calculate_indices

# Streamlit page configuration
st.set_page_config(page_title="Weather Hazards", page_icon="🌤️", layout="wide")

# Sidebar configuration
configure_sidebar()

# Title and subheader
st.title("Weather Hazards")

if not "station_status" in st.session_state:
    # Ensure data is available in session state
    connect_to_weather_stations()

# Fetch data from session state
if "station_status" in st.session_state:

    station_status = st.session_state["station_status"]

    station_count = st.session_state["station_count"]

    most_recent_date = pd.to_datetime(station_status['Last Communication Date']).max()

    st.success(f"Successfully connected to {station_count} stations. Last update **{most_recent_date}** local time.")

    st.header("Live Analysis")

    # Ensure required columns are in station_status
    required_columns = [
        'Air Temperature (°C)', 'Relative Humidity (%)', 'Wind Speed (m/s)',
        'Solar Radiation (W/m²)', 'Latitude', 'Longitude', 'Custom Name'
    ]

    if not all(col in station_status.columns for col in required_columns):
        st.error(f"Missing required columns in the data: {set(required_columns) - set(station_status.columns)}")
        st.stop()

    # Calculate indices for the stations
    results_df = station_status.apply(calculate_indices, axis=1)
    hazard_df = pd.concat([station_status[required_columns], results_df], axis=1)

    # Select the hazard type using radio buttons
    hazard_type = st.radio(
        "Select a weather hazard to display on the map:",
        ["Heat Index (HI)", "Universal Thermal Climate Index (UTCI)"]
    )

    # Determine the relevant columns for the selected hazard
    if hazard_type == "Heat Index (HI)":
        value_column = "Heat Index"
        stress_column = "Heat Index Stress"
    else:  # Universal Thermal Climate Index (UTCI)
        value_column = "UTCI"
        stress_column = "UTCI Stress"

    map_center_lat = station_status["Latitude"].mean()
    map_center_lon = station_status["Longitude"].mean()

    # Apply a downward offset to nudge the map down
    nudge = 0.05
    adjusted_map_center_lat = map_center_lat + nudge  # Subtract to nudge down

    # Create a map with the bounds set dynamically
    m = folium.Map(
        location=[adjusted_map_center_lat, map_center_lon], 
        zoom_start=9,
        tiles="CartoDB Voyager"  # Use CartoDB Positron tiles for English place names
    )

    # Add stations with hazard markers
    for _, station in station_status.iterrows():
        stress = hazard_df.at[station.name, stress_column]
        value = hazard_df.at[station.name, value_column]

        # Check if value is numeric before rounding
        if isinstance(value, (int, float)):
            display_value = int(round(value, 0))
        else:
            display_value = "N/A"

        # Tooltip for station info
        tooltip = f"""
        <strong>{station['Custom Name']}</strong><br>
        {value_column}: {display_value}<br>
        {stress_column}: {stress}
        """

        # Determine marker color based on stress category
        color = (
            "green" if stress in ["No heat stress", "No significant risk"] else
            "yellow" if stress in ["Moderate heat stress", "Caution"] else
            "orange" if stress in ["Strong heat stress", "Extreme Caution"] else
            "red" if stress in ["Very strong heat stress", "Danger"] else
            "darkred" if stress in ["Extreme heat stress", "Extreme Danger"] else
            "grey"
        )

        # Determine text color for readability
        text_color = "white" if color in ["darkred", "red", "orange"] else "black"

        # Add an SVG-based marker
        folium.Marker(
            location=[station['Latitude'], station['Longitude']],
            tooltip=tooltip,
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


    # Display the map above the table
    st_folium(m, width=1200, height=600)

    # Always display UTCI, HI, and related columns in the table
    display_columns = [
        'Custom Name',
        'UTCI',
        'Heat Index',
        'UTCI Stress',
        'Heat Index Stress',
        'Air Temperature (°C)',
        'Relative Humidity (%)',
        'Wind Speed (m/s)'
    ]
    # Reset the index and make it start at 1
    hazard_df_display = hazard_df[display_columns].reset_index(drop=True)
    hazard_df_display.index = hazard_df_display.index + 1

    # Display the DataFrame with the adjusted index
    st.dataframe(hazard_df_display)


else:
    st.warning("Station data not available. Redirecting to Live Weather page...")
    st.page_link("0_Live_Weather.py", label="Go to Live Weather Page")
    st.stop()


# TEMP CODE FOR EXTRACTING HOURLY DATA
# if "station_status" in st.session_state:
#     station_status = st.session_state["station_status"]
#     station_count = st.session_state["station_count"]
#     most_recent_date = pd.to_datetime(station_status['Last Communication Date']).max()
#     stations_hourly_latest, status_message = get_hourly_data()

#     if status_message == "":
#         st.success(f"Successfully downloaded hourly data for {station_count} stations. Last update **{most_recent_date}** local time.")
#     else:
#         st.warning(status_message)

#     st.header("Live Analysis")

#     # Identify the current month for historic averages
#     selected_month_name = most_recent_date.strftime("%B")
#     historic_averages = func_historic_averages()
#     month_avg_row = historic_averages.loc[historic_averages["Month"] == selected_month_name]

#     if not historic_averages_current_month.empty:
#         # Extract historic average temperature data
#         historic_temp_avg = historic_averages_current_month["Temp_Avg"].values[0]
#         historic_temp_max = historic_averages_current_month["Temp_Max"].values[0]
#         historic_temp_min = historic_averages_current_month["Temp_Min"].values[0]

#     temp_patterns = {
#     "min": ["Air Temperature (min)", "HC Air Temperature (min)"],
#     "avg": ["Air Temperature (avg)", "HC Air Temperature (avg)"],
#     "max": ["Air Temperature (max)", "HC Air Temperature (max)"]
# }

    # Display dataframes for each station
    for station_id, station_df in stations_hourly_latest.items():
        st.subheader(f"Station ID: {station_id}")
        st.dataframe(station_df)






st.markdown("---")  # Horizontal line for separation
st.markdown(
    """
    ### References
    
    1. **Tartarini, F., & Schiavon, S. (2020).** *pythermalcomfort: A Python package for thermal comfort research*. SoftwareX, 12, 100578. [https://doi.org/10.1016/j.softx.2020.100578](https://doi.org/10.1016/j.softx.2020.100578)
    2. **Copernicus Climate Change Service. (2024, May 22).** *Heat stress: what is it and how is it measured?* Retrieved December 6, 2024, from [https://climate.copernicus.eu/heat-stress-what-it-and-how-it-measured](https://climate.copernicus.eu/heat-stress-what-it-and-how-it-measured)
    3. **National Weather Service.** *What is the heat index?* Retrieved December 6, 2024, from [https://www.weather.gov/ama/heatindex](https://www.weather.gov/ama/heatindex)

    ---
    """,
    unsafe_allow_html=True
)
