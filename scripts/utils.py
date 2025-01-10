import streamlit as st
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
import datetime

def connect_to_weather_stations():
    """
    Connects to weather stations and fetches data, persisting the session state.
    """
    # Check if session state already has data
    if "access_token" in st.session_state and "station_status" in st.session_state:
        return

    try:
        # Step 1: Retrieve access token
        access_token = get_access_token()
        st.session_state["access_token"] = access_token

        # Step 2: Fetch weather station data
        stations_data = get_weather_stations(access_token)
        station_status = process_station_data(stations_data)
        
        # Parse coordinates into separate columns
        station_status[["Latitude", "Longitude"]] = station_status["Coordinates (Latitude, Longitude)"].str.extract(
            r"\(([^,]+), ([^)]+)\)"
        ).astype(float)

        # Step 3: Store in session state
        st.session_state["station_status"] = station_status
        st.session_state["station_count"] = len(stations_data)

    except Exception as e:
        st.error(str(e))
        st.stop()

def get_access_token():
    """
    Retrieves an access token and saves it to session state if not already available.
    """
    if "access_token" in st.session_state:
        return st.session_state["access_token"]

    try:
        client_id = st.secrets["client_id"]
        client_secret = st.secrets["client_secret"]
        token_url = st.secrets["token_url"]

        payload = {'grant_type': 'client_credentials'}
        response = requests.post(
            token_url,
            data=payload,
            auth=HTTPBasicAuth(client_id, client_secret)
        )
        response.raise_for_status()
        access_token = response.json().get("access_token")
        st.session_state["access_token"] = access_token
        return access_token
    except requests.RequestException as e:
        raise Exception(f"Failed to obtain access token: {e}")


def get_weather_stations(access_token):
    """
    Fetches weather station data using the access token.
    """
    try:
        stations_url = st.secrets["stations_url"]
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json'
        }
        response = requests.get(stations_url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise Exception(f"Failed to retrieve weather station data: {e}")


# Helper function for column matching
def match_columns(columns, patterns):
    for pattern in patterns:
        for col in columns:
            if pattern.lower() in col.lower():
                return col
    return None

def get_hourly_data():
    """
    Fetch hourly weather data for the last 5 days, process it, and return a dictionary of DataFrames for each station.
    """
    # Constants
    data_group = 'hourly'
    time_period = '5d'

    # Ensure session state has the required data
    if not ("access_token" in st.session_state and "station_status" in st.session_state):
        connect_to_weather_stations()

    access_token = st.session_state["access_token"]
    station_status = st.session_state["station_status"]
    station_count = st.session_state["station_count"]

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }

    stations_hourly_latest = {}
    status_message = ""

    required_columns = {
        'Air Temperature': ['Air temperature (avg)', 'HC Air temperature (avg)'],
        'Relative Humidity': ['Relative humidity (avg)', 'HC Relative humidity (avg)'],
        'Wind Speed': ['Wind speed (avg)', 'U-sonic wind speed (avg)'],
        'Solar Radiation': ['Solar radiation (avg)']
    }

    # Iterate over stations to fetch and process data
    for i, station_id in enumerate(station_status["Station ID (original)"].tolist()):
        data_url = f"https://api.fieldclimate.com/v2/data/{station_id}/{data_group}/last/{time_period}"
        response = requests.get(data_url, headers=headers)

        if response.status_code == 200:
            station_info = response.json()
            dates = station_info.get('dates', [])
            station_dict = {'dates': dates}

            # Process sensor data
            for sensor in station_info.get('data', []):
                sensor_name = sensor.get('name', 'Unknown Sensor')
                for agg_type, values in sensor.get('values', {}).items():
                    column_name = f"{sensor_name} ({agg_type})"
                    station_dict[column_name] = values

            station_df = pd.DataFrame(station_dict)

            if 'dates' in station_df:
                station_df['dates'] = pd.to_datetime(station_df['dates'])

            # Match and standardise columns
            air_temp_col = match_columns(station_df.columns, required_columns['Air Temperature'])
            humidity_col = match_columns(station_df.columns, required_columns['Relative Humidity'])
            wind_speed_col = match_columns(station_df.columns, required_columns['Wind Speed'])
            solar_radiation_col = match_columns(station_df.columns, required_columns['Solar Radiation'])

            station_df['Air Temperature (°C)'] = station_df[air_temp_col] if air_temp_col else None
            station_df['Relative Humidity (%)'] = station_df[humidity_col] if humidity_col else None
            station_df['Wind Speed (m/s)'] = station_df[wind_speed_col] if wind_speed_col else None
            station_df['Solar Radiation (W/m²)'] = station_df[solar_radiation_col] if solar_radiation_col else 0

            # Calculate indices and add columns
            indices = station_df.apply(calculate_indices, axis=1)
            station_df['UTCI'] = indices['UTCI']
            station_df['Heat Index'] = indices['Heat Index']
            station_df['UTCI Stress'] = indices['UTCI Stress']
            station_df['Heat Index Stress'] = indices['Heat Index Stress']

            stations_hourly_latest[station_id] = station_df

        elif response.status_code == 404:
            status_message += f"Station {i+1}/{station_count}: Error 404: Station ID {station_id} not found. Skipping.\n"
        else:
            status_message += (
                f"Station {i+1}/{station_count}: Failed to retrieve data for station {station_id}. "
                f"Status Code: {response.status_code}\nResponse: {response.text}\n"
            )

    # Store processed data in session state
    st.session_state["stations_hourly_latest"] = stations_hourly_latest

    return stations_hourly_latest, status_message


def process_station_data(stations_data):
    """
    Processes raw weather station data into a structured Pandas DataFrame.
    Args:
        stations_data (list): Raw data from the weather station API.
    Returns:
        pd.DataFrame: Processed data in tabular format.
    """
    stations_list = []
    for station in stations_data:
        position = station.get('position', {}) or {}
        coordinates = position.get('geo', {}).get('coordinates', ['N/A', 'N/A'])
        altitude = position.get('altitude', 'N/A')
        dates = station.get('dates', {}) or {}
        meta = station.get('meta', {}) or {}
        networking = station.get('networking', {}) or {}
        info = station.get('info', {}) or {}
        name = station.get('name', {}) or {}

        station_info = {
            'Station ID (original)': name.get('original', 'N/A'),
            'Custom Name': name.get('custom', 'N/A'),
            'Device Name': info.get('device_name', 'N/A'),
            'UID': info.get('uid', 'N/A'),
            'Firmware Version': info.get('firmware', 'N/A'),
            'Hardware Version': info.get('hardware', 'N/A'),
            'Rights (rw)': station.get('rights', 'N/A'),
            'Starred': station.get('starred', 'N/A'),
            'Programmed Date': info.get('programmed', 'N/A'),
            'Created Date': dates.get('created_at', 'N/A'),
            'Country': position.get('country', 'N/A'),
            'Coordinates (Latitude, Longitude)': f"({coordinates[1]}, {coordinates[0]})",
            'Altitude (m)': altitude,
            'Air Temperature (°C)': meta.get('airTemp', 'N/A'),
            'Relative Humidity (%)': meta.get('rh', 'N/A'),
            'Soil Temperature (°C)': meta.get('soilTemp', 'N/A'),
            'Solar Radiation (W/m²)': meta.get('solarRadiation', 'N/A'),
            'Rain Last (mm)': meta.get('rain_last', 'N/A'),
            'Wind Speed (m/s)': meta.get('windSpeed', 'N/A'),
            'Volumetric Water Content (Average) (%)': meta.get('volumetricAverage', 'N/A'),
            'Battery Voltage (mV)': meta.get('battery', 'N/A'),
            'Solar Panel Voltage (mV)': meta.get('solarPanel', 'N/A'),
            'Networking Type': networking.get('type', 'N/A'),
            'Roaming Status': networking.get('roaming', 'N/A'),
            'Last Communication Date': dates.get('last_communication', 'N/A'),
        }
        stations_list.append(station_info)

    return pd.DataFrame(stations_list)

def get_color_scheme(value, indicator):
    """
    Determines the color scheme for a given indicator value.

    Args:
        value (float or str): The value of the indicator. Can be a float or "N/A".
        indicator (str): The name of the indicator (e.g., "Air Temperature (°C)", "Relative Humidity (%)").

    Returns:
        str: The color corresponding to the value and indicator.
    """
    # Handle N/A values
    if value == "N/A":
        return "grey"  # Grey color for N/A values

    # Color scheme based on the indicator type
    if indicator == "Air Temperature (°C)":
        if value <= 0:
            return "darkblue"
        elif value <= 10:
            return "blue"
        elif value <= 20:
            return "lightgreen"
        elif value <= 30:
            return "yellow"
        elif value <= 35:
            return "orange"
        elif value <= 40:
            return "red"
        else:
            return "darkred"

    elif indicator == "Relative Humidity (%)":
        if value <= 40:
            return "lightyellow"
        elif value <= 60:
            return "lightgreen"
        else:
            return "lightblue"

    elif indicator == "Rain Last (mm)":
        if value == 0:
            return "white"
        elif value <= 5:
            return "lightblue"
        elif value <= 10:
            return "blue"
        else:
            return "darkblue"

    elif indicator == "Wind Speed (m/s)":
        if value <= 3:
            return "lightgreen"
        elif value <= 7:
            return "yellow"
        else:
            return "red"

    # Default case if indicator doesn't match
    return "grey"

import streamlit as st

def configure_sidebar(logo_path="./assets/logo_square.png", sidebar_width=200):
    """
    Configures the Streamlit sidebar with custom CSS, a logo, and a description.

    Args:
        logo_path (str): Path to the logo image file.
        sidebar_width (int): Fixed width for the sidebar in pixels.
    """
    # Inject custom CSS to control the sidebar's width
    # - `width`: Sets the fixed width of the sidebar.
    # - `min-width`: Ensures the sidebar cannot shrink below the specified width.
    # - `max-width`: Ensures the sidebar cannot grow beyond the specified width.
    
    st.markdown(
        f"""
        <style>
        /* Fix the sidebar width */
        [data-testid="stSidebar"] {{
            width: {sidebar_width}px !important; /* Set the width */
            min-width: {sidebar_width}px !important; /* Prevent resizing below this width */
            max-width: {sidebar_width}px !important; /* Prevent resizing above this width */
        }}
        </style>
        """,
        unsafe_allow_html=True  # Allow rendering of custom HTML and CSS
    )

    # Add a logo to the sidebar
    # - `logo_path`: Path to the image file (supports local paths or URLs).
    # - `use_container_width`: Adjusts the logo size to fit the sidebar width.
    # - `output_format`: Ensures the logo retains transparency by using PNG format.
    st.sidebar.image(
        logo_path,  # Path to your transparent PNG logo
        use_container_width=True,  # Make it responsive to the sidebar's width
        output_format="PNG"  # Ensure transparency for PNG images
    )

    # Add a description below the logo in the sidebar
    # - Markdown allows for hyperlinks and rich text formatting.
    # - The hyperlink directs users to the White Helmets website.
    st.sidebar.markdown(
       """
       This weather station data portal is operated by 
       [The White Helmets](https://www.whitehelmets.org/).
       """
    )



import pandas as pd
from pythermalcomfort.models import utci, heat_index

# Function to categorize UTCI stress
def categorize_utci(utci_value):
    """
    Categorize UTCI stress levels based on UTCI value.

    Args:
        utci_value (float): The UTCI value.

    Returns:
        str: Stress category based on UTCI value.
    """
    if utci_value < 26:
        return "No heat stress"
    elif 26 <= utci_value < 32:
        return "Moderate heat stress"
    elif 32 <= utci_value < 38:
        return "Strong heat stress"
    elif 38 <= utci_value < 46:
        return "Very strong heat stress"
    elif utci_value >= 46:
        return "Extreme heat stress"
    else:
        return "N/A"

# Function to categorize Heat Index stress
def categorize_heat_index(hi_value):
    """
    Categorize Heat Index stress levels based on Heat Index value.

    Args:
        hi_value (float): The Heat Index value in Celsius.

    Returns:
        str: Stress category based on Heat Index value.
    """
    if hi_value < 26.7:
        return "No heat stress"
    elif 26.7 <= hi_value < 32.2:
        return "Caution"
    elif 32.2 <= hi_value < 39.4:
        return "Extreme Caution"
    elif 39.4 <= hi_value < 51.1:
        return "Danger"
    elif hi_value >= 51.1:
        return "Extreme Danger"
    else:
        return "N/A"

def calculate_indices(row):
    """
    Calculate UTCI and Heat Index for a given station, handling missing data gracefully.

    Args:
        row (pd.Series): A row from the DataFrame containing station data.

    Returns:
        pd.Series: A series with calculated indices and stress categories or N/A for missing data.
    """
    try:
        # Extract values and handle missing data
        tdb = row.get('Air Temperature (°C)', None)
        rh = row.get('Relative Humidity (%)', None)
        v_2m = row.get('Wind Speed (m/s)', None)
        if v_2m is not None and v_2m < 0.4: # edit because package doesn't work with speeds below 0.4m/s
            v_2m = 0.4
        solar_radiation = row.get('Solar Radiation (W/m²)', None)

        # Check for missing essential data
        if pd.isna(tdb) or pd.isna(rh) or pd.isna(v_2m):
            return pd.Series({
                'UTCI': 'N/A',
                'Heat Index': 'N/A',
                'UTCI Stress': 'N/A',
                'Heat Index Stress': 'N/A'
            })

        # Convert relative humidity to a fraction
        rh /= 100

        # Adjust wind speed to 10m
        z_measured = 2
        z_target = 10
        alpha = 0.14
        v_10m = v_2m * (z_target / z_measured) ** alpha

        # Calculate mean radiant temperature (handle missing solar radiation)
        if pd.isna(solar_radiation):
            solar_radiation = 0  # Assume no solar radiation if missing
        sigma = 5.67e-8  # Stefan-Boltzmann constant
        a = 0.7  # Absorptivity for skin
        f = 0.5  # View factor for outdoor exposure
        tdb_k = tdb + 273.15
        tr_k = ((tdb_k ** 4) + (solar_radiation * a * f / sigma)) ** 0.25
        tr = tr_k - 273.15

        # Calculate UTCI and Heat Index
        utci_value = utci(tdb=tdb, tr=tr, v=v_10m, rh=rh)
        hi_value = heat_index(tdb=tdb, rh=rh)

        # Determine stress categories
        utci_category = categorize_utci(utci_value)
        hi_category = categorize_heat_index(hi_value)

        return pd.Series({
            'UTCI': utci_value,
            'Heat Index': hi_value,
            'UTCI Stress': utci_category,
            'Heat Index Stress': hi_category
        })
    except Exception as e:
        # Handle unexpected errors gracefully
        return pd.Series({
            'UTCI': 'N/A',
            'Heat Index': 'N/A',
            'UTCI Stress': 'N/A',
            'Heat Index Stress': 'N/A'
        })


import streamlit as st
import pandas as pd
import urllib.parse

def fetch_historic_data(station_status):
    """
    Fetch historic weather data for all weather stations and save it in session state.

    Args:
        station_status (pd.DataFrame): DataFrame containing station information with "Custom Name".

    Returns:
        dict: Dictionary containing historic data as DataFrames for each station.
    """
    if not isinstance(station_status, pd.DataFrame):
        st.error("Invalid station_status provided. Expected a Pandas DataFrame.")
        return {}

    # Placeholder for the loading message
    loading_message = st.empty()

    # Display the loading message
    loading_message.write("Fetching historic weather data...")

    # Base URL for Google Sheets public CSV export
    sheet_url = st.secrets["historic_data_url"]
    doc_id = sheet_url.split("/")[5]
    base_url = f"https://docs.google.com/spreadsheets/d/{doc_id}/gviz/tq?tqx=out:csv&sheet="

    # Extract sheet names from station_status["Custom Name"]
    if "Custom Name" not in station_status.columns:
        st.error("Missing 'Custom Name' in station_status DataFrame.")
        return {}

    station_names = station_status["Custom Name"].unique()

    # Dictionary to hold DataFrames for each station
    historic_dataframes = {}

    # Fetch and store data for each station
    for station in station_names:
        try:
            sanitized_name = urllib.parse.quote(station.strip())
            url = base_url + sanitized_name
            df = pd.read_csv(url)
            historic_dataframes[station] = df
        except Exception as e:
            # Clear the loading message
            loading_message.empty()
            st.warning(f"Could not load data for {station}: {e}")

    # Save the fetched data to session state
    st.session_state["historic_dataframes"] = historic_dataframes

    # Clear the loading message
    loading_message.empty()

    return historic_dataframes


def func_historic_averages():

    # Create the dataframe with the given data
    data = pd.DataFrame({
        "Month": [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ],
        "Temp_Avg": [7.24, 9.00, 12.70, 17.56, 22.60, 27.29, 30.04, 29.94, 26.59, 21.25, 14.25, 8.98],
        "Temp_Max": [11.65, 13.86, 18.18, 23.80, 29.39, 34.39, 37.16, 36.94, 33.50, 27.58, 19.72, 13.52],
        "Temp_Min": [2.8, 4.2, 7.2, 11.3, 15.8, 20.2, 23.0, 22.9, 19.7, 14.9, 8.7, 4.4],
        "Precipitation_Total": [41.49, 36.92, 33.48, 21.75, 13.39, 1.64, 0.51, 0.55, 2.30, 15.85, 26.51, 35.92]
    })

    return data

def generate_chart_prompt(data: pd.DataFrame, selected_month, chart_title: str, instructions: str):
    """
    Generate a ChatGPT prompt for a given chart.
    
    :param data: DataFrame containing the chart data.
    :param chart_title: Title of the chart to include in the prompt.
    :param instructions: Specific instructions for ChatGPT.
    :return: Formatted prompt string.
    """
    return f"""You are a weather analyst preparing a weather report for a local audience in Northern Syria. Below is {chart_title} data for the month of {selected_month} at various locations (as indicated by "Custom Name"). Write a concise, engaging weather report summarising the weather conditions based on the provided data. Please follow these instructions:

1. The audience of the report is the general public and humanitarian organisations operating in Syria.
2. Use non-technical language. For example, do not write about "data" and refer to locations (e.g., town names) rather than "weather stations".
3. Structure the report in two concise paragraphs. The first should analyse the data in 100 words. The second should discuss how the weather data might affect vulnerable populations, such as internally displaced persons (IDPs) or people living in poverty in 50 words.
4. Strictly avoid making unwarranted inferences or assumptions and ensure observations are strictly based on the data. Maintain a professional tone and, avoid generic phrases, repetition or alarmist statements.
5. {instructions}

{data.to_string(index=False)}"""
