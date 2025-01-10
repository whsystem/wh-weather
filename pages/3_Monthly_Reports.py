import streamlit as st
import pandas as pd
from datetime import datetime
import calendar
import plotly.graph_objects as go
from scripts.utils import connect_to_weather_stations, fetch_historic_data, configure_sidebar, func_historic_averages, get_color_scheme, generate_chart_prompt
import folium
from streamlit_folium import st_folium

# Page configuration
st.set_page_config(page_title="Monthly Reports", page_icon="🌤️", layout="wide")

# Sidebar configuration
configure_sidebar()


# Title and instructions
st.title("Monthly Weather Reports")

# Ensure station data is available in session state
if not "station_status" in st.session_state:
    connect_to_weather_stations()

# Fetch station data
if "station_status" in st.session_state:
    station_status = st.session_state["station_status"]

    # Check if historic data is already stored in session state
    if "historic_dataframes" not in st.session_state:
        historic_dataframes = fetch_historic_data(station_status)
        st.session_state["historic_dataframes"] = historic_dataframes
    else:
        historic_dataframes = st.session_state["historic_dataframes"]

    most_recent_date = max(pd.to_datetime(df['Date/Time']).max() for df in historic_dataframes.values()).date()
    station_count = len(historic_dataframes)

    st.success(f"Successfully downloaded data for {station_count} stations. Last update **{most_recent_date}**.")

    # Generate the last 12 full months
    today = datetime.today()
    earliest_date = datetime(2024, 4, 1)  # Set the earliest date to April 2024

    # Generate months going back 12 months from today
    previous_months = [
        (today.replace(day=1) - pd.DateOffset(months=i)).strftime("%B %Y")
        for i in range(60)
    ]

    # Filter out months earlier than the earliest_date
    previous_months = [
        month for month in previous_months
        if datetime.strptime(month, "%B %Y") >= earliest_date
    ]

    # Dropdown to select the month
    selected_month = st.selectbox("Select a month to generate a report:", previous_months)

    # Store the previously selected month in session state
    if "previous_month" not in st.session_state:
        st.session_state["previous_month"] = ""

    # Check if the selected month has changed
    if selected_month != st.session_state["previous_month"]:
        # Clear relevant session state keys
        keys_to_clear = [
            "combined_temp_analysis_prompt",
            "precipitation_analysis_prompt",
            "wind_analysis_prompt"
        ]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]

        # Update the previously selected month
        st.session_state["previous_month"] = selected_month


    # Parse the selected month and calculate the date range
    selected_month_name, selected_year = selected_month.split()
    selected_year = int(selected_year)
    selected_month_number = list(calendar.month_name).index(selected_month_name)

    start_date = datetime(selected_year, selected_month_number, 1)
    end_date = datetime(selected_year, selected_month_number, calendar.monthrange(selected_year, selected_month_number)[1])


    st.title(f"Monthly Weather Report: {selected_month}")

    # Filter data for the selected month
    filtered_dataframes = {}
    for station_name, df in historic_dataframes.items():
        if "Date/Time" in df.columns:
            df["Date/Time"] = pd.to_datetime(df["Date/Time"], errors="coerce")
            filtered_df = df[(df["Date/Time"] >= start_date) & (df["Date/Time"] <= end_date)]
            filtered_dataframes[station_name] = filtered_df
        else:
            st.warning(f"Station {station_name} does not have a 'Date/Time' column. Skipping.")

    # Get historic averages for the selected month
    historic_averages = func_historic_averages()
    month_avg_row = historic_averages.loc[historic_averages["Month"] == selected_month_name]


    st.header("Section 1: Temperature Analysis")


    # Ensure the session state key for combined temperature analysis prompt exists
    if "combined_temp_analysis_prompt" not in st.session_state:
        st.session_state["combined_temp_analysis_prompt"] = ""

    # Button to generate the combined ChatGPT prompt
    if st.button("Generate a ChatGPT Prompt", key="combined_temp_analysis_button"):
        # Prepare combined data for the prompt
        combined_data = []
        
        # Fetch the historical temperature data for the selected month
        historic_averages = func_historic_averages()
        month_avg_row = historic_averages.loc[historic_averages["Month"] == selected_month_name]
        
        historic_temp_avg = month_avg_row["Temp_Avg"].values[0] if not month_avg_row.empty else None
        historic_temp_max = month_avg_row["Temp_Max"].values[0] if not month_avg_row.empty else None
        historic_temp_min = month_avg_row["Temp_Min"].values[0] if not month_avg_row.empty else None

        for station_name, df in filtered_dataframes.items():
            # Skip empty dataframes
            if df.empty:
                continue

            # Check necessary columns
            max_temp_col = next((col for col in df.columns if "Air temperature (max)" in col), None)
            min_temp_col = next((col for col in df.columns if "Air temperature (min)" in col), None)

            if not max_temp_col or not min_temp_col:
                continue

            # Calculate metrics
            max_temp = int(round(df[max_temp_col].max(), 0)) if not df[max_temp_col].isna().all() else None
            min_temp = int(round(df[min_temp_col].min(), 0)) if not df[min_temp_col].isna().all() else None
            days_above_30 = int((df[max_temp_col] > 30).sum())
            days_above_35 = int((df[max_temp_col] > 35).sum())
            days_above_40 = int((df[max_temp_col] > 40).sum())
            days_below_10 = int((df[min_temp_col] < 10).sum())
            days_below_5 = int((df[min_temp_col] < 5).sum())
            days_below_0 = int((df[min_temp_col] < 0).sum())

            # Append combined data
            combined_data.append({
                "Station": station_name,
                "Max Temperature (°C)": max_temp,
                "Min Temperature (°C)": min_temp,
                "Days > 30°C": days_above_30,
                "Days > 35°C": days_above_35,
                "Days > 40°C": days_above_40,
                "Days < 10°C": days_below_10,
                "Days < 5°C": days_below_5,
                "Days < 0°C": days_below_0,
            })

        # Convert to a DataFrame for the prompt
        combined_temp_df = pd.DataFrame(combined_data)

        # Generate and store the prompt in session state
        st.session_state["combined_temp_analysis_prompt"] = generate_chart_prompt(
            data=combined_temp_df,
            selected_month=selected_month,
            chart_title="temperature",
            instructions=(
                f"Strictly ensure that the report mentions both (1) the maximum and minimum temperatures and (2) the frequency of hot and cold days across locations. "
                f"If temperatures drop below zero, specifically highlight this and discuss the implications. "
                f"Highlight significant trends or deviations from the country-wide historical norms: "
                f"the historical average temperature is {historic_temp_avg}°C, the historical maximum is {historic_temp_max}°C, and the historical minimum is {historic_temp_min}°C. "
                f"Discuss the implications of these deviations for vulnerable populations."
            )
        )

    # Display the generated prompt for temperature analysis, if available
    if "combined_temp_analysis_prompt" in st.session_state and st.session_state["combined_temp_analysis_prompt"]:
        st.markdown("Copy this prompt into [ChatGPT](https://chatgpt.com/) to generate a report:")
        st.text_area(
            "Click in the text box and press Ctrl+A then Ctrl+C.",
            value=st.session_state["combined_temp_analysis_prompt"],
            height=100
        )


    ### PLOT MAP ###

    st.subheader(f"1.1 Maximum and Minimum Temperature by Location")

    # Filter stations with temperature data available for the selected month
    stations_with_data = []
    for station_name, df in historic_dataframes.items():
        if not df.empty:
            # Ensure "Date/Time" exists and is datetime
            if "Date/Time" in df.columns:
                df["Date/Time"] = pd.to_datetime(df["Date/Time"], errors="coerce")
                # Filter data for the selected date range
                filtered_df = df[(df["Date/Time"] >= start_date) & (df["Date/Time"] <= end_date)]
                # Check if temperature data exists
                if any(col for col in df.columns if "Air temperature" in col) and not filtered_df.empty:
                    stations_with_data.append(station_name)

    # Get the corresponding rows from station_status
    stations_with_data_status = station_status.loc[
        station_status["Custom Name"].isin(stations_with_data)
    ]

    # Ensure there are valid stations; fallback if none are found
    if not stations_with_data_status.empty:
        # Calculate average latitude and longitude for better centering
        map_center_lat = stations_with_data_status["Latitude"].mean()
        map_center_lon = stations_with_data_status["Longitude"].mean()
    else:
        # Fallback to the full station list if no data is available
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


    # Loop through each station to plot max and min temperatures
    for station_name, df in filtered_dataframes.items():
        # Get station coordinates
        station_row = station_status[station_status["Custom Name"] == station_name]
        if station_row.empty:
            continue  # Skip if no matching station in station_status

        lat = station_row["Latitude"].values[0]
        lon = station_row["Longitude"].values[0]

        # Calculate max and min temperatures
        max_temp_col = next((col for col in df.columns if "Air temperature (max)" in col), None)
        min_temp_col = next((col for col in df.columns if "Air temperature (min)" in col), None)

        max_temp = int(round(df[max_temp_col].max(), 0)) if max_temp_col and not df[max_temp_col].isna().all() else None
        min_temp = int(round(df[min_temp_col].min(), 0)) if min_temp_col and not df[min_temp_col].isna().all() else None

        # Skip markers if data is unavailable
        if max_temp is None and min_temp is None:
            continue

        # Get colors for the markers
        max_color = get_color_scheme(max_temp, "Air Temperature (°C)") if max_temp is not None else "grey"
        min_color = get_color_scheme(min_temp, "Air Temperature (°C)") if min_temp is not None else "grey"

        # Determine text color based on background color
        max_text_color = "white" if max_color in ["blue", "darkblue", "darkred"] else "black"
        min_text_color = "white" if min_color in ["blue", "darkblue", "darkred"] else "black"

        # Add upward triangle for max temperature if available
        if max_temp is not None:
            max_marker = folium.Marker(
                location=[lat, lon],  # Station's exact coordinates
                icon=folium.DivIcon(
                    html=f"""
                    <div style="position: relative; transform: translate(0, -20px);">
                        <svg xmlns="http://www.w3.org/2000/svg" height="40" width="40" viewBox="0 0 40 40">
                            <polygon points="20,0 40,40 0,40" style="fill:{max_color};stroke:black;stroke-width:1;fill-opacity:0.8;" />
                            <text x="50%" y="70%" dominant-baseline="middle" text-anchor="middle" fill="{max_text_color}" font-size="12" font-weight="bold">{max_temp}</text>
                        </svg>
                    </div>
                    """,
                ),
                tooltip=f"{station_name}<br>Max Temp: {max_temp}°C",
            )
            max_marker.add_to(m)

        # Add downward triangle for min temperature if available
        if min_temp is not None:
            min_marker = folium.Marker(
                location=[lat, lon],  # Station's exact coordinates
                icon=folium.DivIcon(
                    html=f"""
                    <div style="position: relative; transform: translate(0, 20px);">
                        <svg xmlns="http://www.w3.org/2000/svg" height="40" width="40" viewBox="0 0 40 40">
                            <polygon points="20,40 40,0 0,0" style="fill:{min_color};stroke:black;stroke-width:1;fill-opacity:0.8;" />
                            <text x="50%" y="30%" dominant-baseline="middle" text-anchor="middle" fill="{min_text_color}" font-size="12" font-weight="bold">{min_temp}</text>
                        </svg>
                    </div>
                    """,
                ),
                tooltip=f"{station_name}<br>Min Temp: {min_temp}°C",
            )
            min_marker.add_to(m)

    # Display the map in Streamlit
    st_folium(m, width=1200, height=600)

    ### PLOT CHART ###

    if not month_avg_row.empty:

        st.subheader("1.2 Daily Temperatre Range Across Locations vs. Country-Wide Historic Average (1991-2020)")
        
        # Create Plotly figure
        fig = go.Figure()

        # Prepare historic average lines
        temp_avg = month_avg_row["Temp_Avg"].values[0]
        temp_max = month_avg_row["Temp_Max"].values[0]
        temp_min = month_avg_row["Temp_Min"].values[0]

        # Add dotted lines for historic average, max, and min with transparency
        fig.add_trace(go.Scatter(
            x=[start_date, end_date],
            y=[temp_avg, temp_avg],
            mode="lines",
            line=dict(color="rgba(0, 0, 0, 0.7)", width=2, dash="dot"),  # Semi-transparent black for Avg
            name="Historic Avg Temp"
        ))

        fig.add_trace(go.Scatter(
            x=[start_date, end_date],
            y=[temp_max, temp_max],
            mode="lines",
            line=dict(color="rgba(255, 0, 0, 0.7)", width=2, dash="dot"),  # Semi-transparent red for Max
            name="Historic Max Temp"
        ))

        fig.add_trace(go.Scatter(
            x=[start_date, end_date],
            y=[temp_min, temp_min],
            mode="lines",
            line=dict(color="rgba(0, 0, 255, 0.7)", width=2, dash="dot"),  # Semi-transparent blue for Min
            name="Historic Min Temp"
        ))


        # Calculate daily bounds dynamically
        daily_aggregates = []

        for day in pd.date_range(start_date, end_date):
            daily_temps = {
                "min": [],
                "avg": [],
                "max": []
            }
            for df in filtered_dataframes.values():
                df_day = df[df["Date/Time"].dt.date == day.date()]
                for temp_col_partial, key in [
                    ("Air temperature (min)", "min"),
                    ("Air temperature (avg)", "avg"),
                    ("Air temperature (max)", "max"),
                ]:
                    matching_col = next((col for col in df.columns if temp_col_partial in col), None)
                    if matching_col:
                        daily_temps[key].extend(df_day[matching_col].dropna().tolist())
            
            # Calculate aggregates if data exists
            if daily_temps["min"] and daily_temps["avg"] and daily_temps["max"]:
                daily_aggregates.append({
                    "Date": day,
                    "Min_Low": min(daily_temps["min"]),
                    "Min_High": max(daily_temps["min"]),
                    "Min_Avg": pd.Series(daily_temps["min"]).mean(),
                    "Avg_Low": min(daily_temps["avg"]),
                    "Avg_High": max(daily_temps["avg"]),
                    "Avg_Avg": pd.Series(daily_temps["avg"]).mean(),
                    "Max_Low": min(daily_temps["max"]),
                    "Max_High": max(daily_temps["max"]),
                    "Max_Avg": pd.Series(daily_temps["max"]).mean(),
                })

        daily_aggregates_df = pd.DataFrame(daily_aggregates)

        # Add dynamic bands
        for col_low, col_high, fillcolor, label in [
            ("Min_Low", "Min_High", "rgba(0, 0, 255, 0.3)", "Daily Min Range"),
            ("Avg_Low", "Avg_High", "rgba(0, 0, 0, 0.3)", "Daily Avg Range"),
            ("Max_Low", "Max_High", "rgba(255, 0, 0, 0.3)", "Daily Max Range"),
        ]:
            fig.add_trace(go.Scatter(
                x=daily_aggregates_df["Date"].tolist() + daily_aggregates_df["Date"].tolist()[::-1],
                y=daily_aggregates_df[col_low].tolist() + daily_aggregates_df[col_high].tolist()[::-1],
                fill="toself",
                fillcolor=fillcolor,
                line=dict(width=0),
                mode="none",
                name=label
            ))

        # Add daily average lines using daily_aggregates_df
        # Add daily average lines
        for key, color, label in [
            ("Min_Avg", "blue", "Daily Min Avg"),
            ("Avg_Avg", "black", "Daily Avg Temp"),
            ("Max_Avg", "red", "Daily Max Avg"),
        ]:
            fig.add_trace(go.Scatter(
                x=daily_aggregates_df["Date"],
                y=daily_aggregates_df[key],
                mode="lines",
                line=dict(color=color, width=2),
                name=label
            ))



        # Add a checkbox for toggling individual station lines
        show_station_lines = st.checkbox("Show individual weather station data", value=False)
        # Add weather station lines if the checkbox is checked
        if show_station_lines:
            for station_name, filtered_df in filtered_dataframes.items():
                for temp_col_partial in ["Air temperature (max)", "Air temperature (avg)", "Air temperature (min)"]:
                    matching_col = next((col for col in filtered_df.columns if temp_col_partial in col), None)
                    if matching_col:
                        fig.add_trace(go.Scatter(
                            x=filtered_df["Date/Time"],
                            y=filtered_df[matching_col],
                            mode="lines",
                            line=dict(color="rgba(128, 128, 128, 0.4)", width=1),
                            name=f"{station_name} (Station Line)",
                            hoverinfo="text",
                            text=station_name
                        ))

        # Update layout
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Temperature (°C)",
            legend_title="Legend",
            hovermode="x unified",
        )

        # Display plot
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.warning(f"No historic average data available for {selected_month_name}.")


 ### PLOT HOT/COLD DAYS (BAR CHART) ###


    st.subheader("1.3 Hot and Cold Days: Graphical Analysis")

    # Extracting the count of hot and cold days for each weather station
    hot_cold_data = []

    for station_name, df in filtered_dataframes.items():
        # Ensure necessary columns exist
        max_temp_col = next((col for col in df.columns if "Air temperature (max)" in col), None)
        min_temp_col = next((col for col in df.columns if "Air temperature (min)" in col), None)

        if not max_temp_col or not min_temp_col:
            continue  # Skip stations with missing temperature columns

        # Count the number of hot and cold days
        days_above_30 = int((df[max_temp_col] > 30).sum())
        days_above_35 = int((df[max_temp_col] > 35).sum())
        days_above_40 = int((df[max_temp_col] > 40).sum())

        days_below_10 = int((df[min_temp_col] < 10).sum())
        days_below_5 = int((df[min_temp_col] < 5).sum())
        days_below_0 = int((df[min_temp_col] < 0).sum())

        # Only add data if at least one of the counts is greater than 0
        if any([days_above_30, days_above_35, days_above_40, days_below_10, days_below_5, days_below_0]):
            hot_cold_data.append({
                'Station': station_name,
                'Days > 30°C': days_above_30,
                'Days > 35°C': days_above_35,
                'Days > 40°C': days_above_40,
                'Days < 10°C': days_below_10,
                'Days < 5°C': days_below_5,
                'Days < 0°C': days_below_0
            })

    # Convert the data to a DataFrame
    hot_cold_df = pd.DataFrame(hot_cold_data)

    if not hot_cold_df.empty:
        # Create the plot
        fig_hot_cold_days = go.Figure()

        # Adding Hot Day Bars (positive direction)
        fig_hot_cold_days.add_trace(go.Bar(
            y=hot_cold_df['Station'],
            x=hot_cold_df['Days > 30°C'],
            name='Days > 30°C',
            orientation='h',
            marker=dict(color='#FFD700'),
            opacity=0.6
        ))

        fig_hot_cold_days.add_trace(go.Bar(
            y=hot_cold_df['Station'],
            x=hot_cold_df['Days > 35°C'],
            name='Days > 35°C',
            orientation='h',
            marker=dict(color='orange'),
            opacity=0.6
        ))

        fig_hot_cold_days.add_trace(go.Bar(
            y=hot_cold_df['Station'],
            x=hot_cold_df['Days > 40°C'],
            name='Days > 40°C',
            orientation='h',
            marker=dict(color='red'),
            opacity=0.6
        ))

        # Adding Cold Day Bars (negative direction)
        fig_hot_cold_days.add_trace(go.Bar(
            y=hot_cold_df['Station'],
            x=-hot_cold_df['Days < 10°C'],
            name='Days < 10°C',
            orientation='h',
            marker=dict(color='lightblue'),
            opacity=0.6
        ))

        fig_hot_cold_days.add_trace(go.Bar(
            y=hot_cold_df['Station'],
            x=-hot_cold_df['Days < 5°C'],
            name='Days < 5°C',
            orientation='h',
            marker=dict(color='blue'),
            opacity=0.6
        ))

        fig_hot_cold_days.add_trace(go.Bar(
            y=hot_cold_df['Station'],
            x=-hot_cold_df['Days < 0°C'],
            name='Days < 0°C',
            orientation='h',
            marker=dict(color='darkblue'),
            opacity=0.6
        ))

        # Updating layout to align both axes symmetrically around zero
        max_value = max(hot_cold_df.max(numeric_only=True).max(), abs(hot_cold_df.min(numeric_only=True).min()))
        fig_hot_cold_days.update_layout(
            xaxis=dict(
                title='Days',
                showline=True,
                zeroline=True,
                zerolinewidth=2,
                zerolinecolor='black',
                range=[-max_value, max_value],
                tickvals=list(range(-max_value, max_value + 1, 1)),
                ticktext=[f"{abs(v)}" for v in range(-max_value, max_value + 1, 1)],
                showgrid=True, gridcolor="lightgrey", gridwidth=0.5
            ),
            yaxis_title='Weather Stations',
            barmode='overlay',  # Use overlay to make bars overlap
            width=1000,
            height=600,
            legend_title='Legend'
        )

        # Display the plot
        st.plotly_chart(fig_hot_cold_days, use_container_width=True)
    else:
        st.warning("No data available to generate the bar plot for hot and cold days.")




    ##### Plot Hot / Cold Days (GEOSPATIAL) ##########

    st.subheader("1.4 Hot and Cold Days: Geospatial Analysis")

    # Radio button for user selection
    selected_option = st.radio(
        "Select temperature analysis type:",
        options=["Hot Days", "Cold Days"],
        index=0,  # Default to "Hot Days"
        help="Choose whether to analyse hot or cold days for the selected month.",
    )

    # Initialize the map
    m_temperature_days = folium.Map(
        location=[adjusted_map_center_lat, map_center_lon], 
        zoom_start=9,
        tiles="CartoDB Voyager"  # Use CartoDB Positron tiles for English place names
    )

    # Define the scaling factor for radius size
    radius_factor = 400  # Adjust this factor for appropriate circle sizes

    # Iterate through the weather stations to calculate and plot based on the selected option
    for station_name, df in filtered_dataframes.items():
        # Ensure data exists for the selected month
        if df.empty:
            continue

        # Get station coordinates
        station_row = station_status[station_status["Custom Name"] == station_name]
        if station_row.empty:
            continue  # Skip if no matching station in station_status

        lat = station_row["Latitude"].values[0]
        lon = station_row["Longitude"].values[0]

        # Determine the temperature column
        if selected_option == "Hot Days":
            temp_col = next((col for col in df.columns if "Air temperature (max)" in col), None)
        else:  # Cold Days
            temp_col = next((col for col in df.columns if "Air temperature (min)" in col), None)

        if not temp_col:
            continue  # Skip if the relevant temperature column does not exist

        # Calculate hot or cold days
        if selected_option == "Hot Days":
            days_above_30 = int((df[temp_col] > 30).sum())
            days_above_35 = int((df[temp_col] > 35).sum())
            days_above_40 = int((df[temp_col] > 40).sum())
        else:  # Cold Days
            days_below_10 = int((df[temp_col] < 10).sum())
            days_below_5 = int((df[temp_col] < 5).sum())
            days_below_0 = int((df[temp_col] < 0).sum())

        # Add circles based on the selected option
        if selected_option == "Hot Days":
            if days_above_30 > 0:
                folium.Circle(
                    location=[lat, lon],
                    radius=days_above_30 * radius_factor,
                    color="yellow",
                    weight=0,
                    fill=True,
                    fill_color="yellow",
                    fill_opacity=0.6,
                    tooltip=f"{days_above_30} Days > 30°C",
                ).add_to(m_temperature_days)

            if days_above_35 > 0:
                folium.Circle(
                    location=[lat, lon],
                    radius=days_above_35 * radius_factor,
                    color="orange",
                    weight=0,
                    fill=True,
                    fill_color="orange",
                    fill_opacity=0.6,
                    tooltip=f"{days_above_35} Days > 35°C",
                ).add_to(m_temperature_days)

            if days_above_40 > 0:
                folium.Circle(
                    location=[lat, lon],
                    radius=days_above_40 * radius_factor,
                    color="red",
                    weight=0,
                    fill=True,
                    fill_color="red",
                    fill_opacity=0.6,
                    tooltip=f"{days_above_40} Days > 40°C",
                ).add_to(m_temperature_days)
        else:  # Cold Days
            if days_below_10 > 0:
                folium.Circle(
                    location=[lat, lon],
                    radius=days_below_10 * radius_factor,
                    color="lightblue",
                    weight=0,
                    fill=True,
                    fill_color="lightblue",
                    fill_opacity=0.6,
                    tooltip=f"{days_below_10} Days < 10°C",
                ).add_to(m_temperature_days)

            if days_below_5 > 0:
                folium.Circle(
                    location=[lat, lon],
                    radius=days_below_5 * radius_factor,
                    color="blue",
                    weight=0,
                    fill=True,
                    fill_color="blue",
                    fill_opacity=0.6,
                    tooltip=f"{days_below_5} Days < 5°C",
                ).add_to(m_temperature_days)

            if days_below_0 > 0:
                folium.Circle(
                    location=[lat, lon],
                    radius=days_below_0 * radius_factor,
                    color="darkblue",
                    weight=0,
                    fill=True,
                    fill_color="darkblue",
                    fill_opacity=0.6,
                    tooltip=f"{days_below_0} Days < 0°C",
                ).add_to(m_temperature_days)

        # Add a base black marker for the weather station with a tooltip
        folium.CircleMarker(
            location=[lat, lon],
            radius=3,
            color="black",
            fill=True,
            fill_color="black",
            fill_opacity=1.0,
            tooltip=station_name,
        ).add_to(m_temperature_days)

    # Display the map
    st_folium(m_temperature_days, width=1200, height=600)

    # Add the legend below the map
    if selected_option == "Hot Days":
        st.markdown(
            """
            <div style="
                width: 250px;
                background-color: white; 
                border:2px solid grey; 
                padding: 10px; 
                opacity: 0.85; 
                font-size: 14px;">
                <b>Legend</b><br>
                <i style="background: yellow; width: 10px; height: 10px; display: inline-block; margin-right: 5px; opacity: 0.6"></i>
                Number of Days > 30°C<br>
                <i style="background: orange; width: 10px; height: 10px; display: inline-block; margin-right: 5px; opacity: 0.6"></i>
                Number of Days > 35°C<br>
                <i style="background: red; width: 10px; height: 10px; display: inline-block; margin-right: 5px; opacity: 0.6"></i>
                Number of Days > 40°C
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:  # Cold Days
        st.markdown(
            """
            <div style="
                width: 250px;
                background-color: white; 
                border:2px solid grey; 
                padding: 10px; 
                opacity: 0.85; 
                font-size: 14px;">
                <b>Legend</b><br>
                <i style="background: lightblue; width: 10px; height: 10px; display: inline-block; margin-right: 5px; opacity: 0.6"></i>
                Number of Days < 10°C<br>
                <i style="background: blue; width: 10px; height: 10px; display: inline-block; margin-right: 5px; opacity: 0.6"></i>
                Number of Days < 5°C<br>
                <i style="background: darkblue; width: 10px; height: 10px; display: inline-block; margin-right: 5px; opacity: 0.6"></i>
                Number of Days < 0°C
            </div>
            """,
            unsafe_allow_html=True,
        )




    # Section for Precipitation Analysis
    st.header("Section 2: Precipitation Analysis")

    # Ensure the session state key for precipitation analysis prompt exists
    if "precipitation_analysis_prompt" not in st.session_state:
        st.session_state["precipitation_analysis_prompt"] = ""

    # Button to generate the precipitation analysis ChatGPT prompt
    if st.button("Generate a ChatGPT Prompt", key="precipitation_analysis_button"):
        # Prepare combined data for the prompt
        precipitation_data = []
        
        # Fetch the historical precipitation data
        historic_averages = func_historic_averages()
        month_avg_row = historic_averages.loc[historic_averages["Month"] == selected_month_name]
        historic_precip_total = month_avg_row["Precipitation_Total"].values[0] if not month_avg_row.empty else None

        for station_name, df in filtered_dataframes.items():
            if "Precipitation (sum)" not in df.columns:
                continue  # Skip if precipitation data is unavailable

            # Calculate total precipitation
            total_precip = df["Precipitation (sum)"].sum()
            daily_precip = df["Precipitation (sum)"].tolist()
            dates = df["Date/Time"].dt.strftime("%Y-%m-%d").tolist()

            # Calculate 5-day cumulative precipitation
            df["5-Day Cumulative Rainfall"] = df["Precipitation (sum)"].rolling(window=5, min_periods=1).sum()
            max_cumulative_precip = df["5-Day Cumulative Rainfall"].max()

            # Append precipitation data
            precipitation_data.append({
                "Station": station_name,
                "Total Precipitation (mm)": total_precip,
                "Max 5-Day Cumulative Precipitation (mm)": max_cumulative_precip,
                "Daily Precipitation (mm)": daily_precip,
                "Dates": dates
            })

        # Convert to a DataFrame for the prompt
        precip_analysis_df = pd.DataFrame(precipitation_data)

        # Generate and store the prompt in session state
        st.session_state["precipitation_analysis_prompt"] = generate_chart_prompt(
            data=precip_analysis_df,
            selected_month=selected_month,
            chart_title="precipitation",
            instructions=(
                f"Analyse precipitation patterns across locations for the selected month. "
                f"Compare observed data, such as total and 5-day cumulative precipitation, "
                f"with the country-wide historic average precipitation value of {historic_precip_total} mm for {selected_month}. "
                f"Highlight stations with significant deviations and discuss the implications for flood risk, water resource availability, "
                f"and vulnerable populations. In avoiding non-technical language, refer to precipitation as rain."
            )
        )

    # Display the generated prompt, if available
    if "precipitation_analysis_prompt" in st.session_state and st.session_state["precipitation_analysis_prompt"]:
        st.markdown(
            f"Copy this prompt into [ChatGPT](https://chatgpt.com/) to generate a report:",
            unsafe_allow_html=True
        )
        st.text_area("Click in the text box and press Ctrl+A then Ctrl+C.", value=st.session_state["precipitation_analysis_prompt"], height=100)



    ##### Plot Daily Precipitation ##########

    st.subheader("2.1 Daily Precipitation")

    # Add radio button to toggle bar mode
    bar_mode = st.radio(
        "Select bar display mode:",
        options=["Stacked", "Grouped"],
        index=0,  # Default to "Stacked"
        help="Choose whether to stack bars or show them side by side for each station."
    )

    # Set the barmode based on the user selection
    barmode = "stack" if bar_mode == "Stacked" else "group"

    # Daily Total Precipitation
    fig_daily_precip = go.Figure()

    for station_name, df in filtered_dataframes.items():
        if "Precipitation (sum)" in df.columns:
            fig_daily_precip.add_trace(go.Bar(
                x=df["Date/Time"],
                y=df["Precipitation (sum)"],
                name=station_name,
                marker=dict(opacity=0.7),
                showlegend=True
            ))

    fig_daily_precip.update_layout(
        xaxis_title="Date",
        yaxis_title="Precipitation (mm)",
        legend_title="Weather Stations",
        barmode=barmode,  # Dynamic based on user selection
        width=1000,
        height=600,
        hovermode="x unified"
    )

    # Display chart
    st.plotly_chart(fig_daily_precip, use_container_width=True)


    ##### Plot Daily Precipitation ##########

    st.subheader("2.2 Daily 5-Day Cumulative Precipitation vs Historic Average (1991-2020) and Flood Warning Threshold")

    st.text("A tempoary flood warning threshold of 50 mm cumulative precipitation over 5 days has been set. This requries on-the-ground verification.")

    # 5-Day Cumulative Rainfall
    fig_cumulative_precip = go.Figure()

    for station_name, df in filtered_dataframes.items():
        if "Precipitation (sum)" in df.columns:
            df["5-Day Cumulative Rainfall"] = df["Precipitation (sum)"].rolling(window=5, min_periods=1).sum()
            fig_cumulative_precip.add_trace(go.Scatter(
                x=df["Date/Time"],
                y=df["5-Day Cumulative Rainfall"],
                mode="lines",
                name=station_name,
                line=dict(width=2),
                showlegend=True
            ))

    # Add flood warning threshold line
    fig_cumulative_precip.add_trace(go.Scatter(
        x=[start_date, end_date],
        y=[50, 50],
        mode="lines",
        name="Flood Warning Threshold (50 mm)",
        line=dict(color="red", width=2, dash="dash"),
        showlegend=True
    ))

    # Calculate historic 5-day average
    if not month_avg_row.empty:
        total_monthly_precip = month_avg_row["Precipitation_Total"].values[0]
        days_in_month = (end_date - start_date).days + 1
        historic_5_day_avg = (total_monthly_precip / days_in_month) * 5

        # Add historic 5-day average line
        fig_cumulative_precip.add_trace(go.Scatter(
            x=[start_date, end_date],
            y=[historic_5_day_avg, historic_5_day_avg],
            mode="lines",
            name=f"Historic 5-Day Avg ({historic_5_day_avg:.1f} mm)",
            line=dict(color="blue", width=2, dash="dot"),
            showlegend=True
        ))


    fig_cumulative_precip.update_layout(
        xaxis_title="Date",
        yaxis_title="Cumulative Rainfall (mm)",
        legend_title="Weather Stations",
        width=1000,
        height=600,
        hovermode="x unified"
    )

    # Display chart
    st.plotly_chart(fig_cumulative_precip, use_container_width=True)


    ##### Plot Daily Precipitation ##########

    st.subheader("2.3 Total Monthly Precipitation by Location")

    # Monthly Total Precipitation Map
    m_precip = folium.Map(
        location=[adjusted_map_center_lat, map_center_lon], 
        zoom_start=9,
        tiles="CartoDB Voyager"  # Use CartoDB Positron tiles for English place names
    )

    # Loop through each station
    for station_name, df in filtered_dataframes.items():
        station_row = station_status[station_status["Custom Name"] == station_name]
        if station_row.empty or "Precipitation (sum)" not in df.columns:
            continue

        # Calculate total monthly precipitation
        total_precip = df["Precipitation (sum)"].sum()
        display_precip = int(round(total_precip, 0))  # Round to nearest integer

        lat = station_row["Latitude"].values[0]
        lon = station_row["Longitude"].values[0]

        if total_precip == 0:
            # Add a small dot for stations with 0 precipitation
            folium.Marker(
                location=[lat, lon],
                tooltip=f"{station_name}<br>Total Monthly Precipitation: {display_precip} mm",
                icon=folium.DivIcon(
                    html=f"""
                    <div style="position: relative; transform: translate(-50%, -50%);">
                        <svg xmlns="http://www.w3.org/2000/svg" height="20" width="20" viewBox="0 0 20 20">
                            <circle cx="10" cy="10" r="10" style="fill:black;stroke:grey;stroke-width:1;fill-opacity:1.0;" />
                            <text x="10" y="13" text-anchor="middle" fill="white" font-size="10" font-weight="bold">0</text>
                        </svg>
                    </div>
                    """
                ),
            ).add_to(m_precip)
        else:
            # Get circle color
            precip_color = get_color_scheme(total_precip, "Rain Last (mm)")
            text_color = "white" if precip_color in ["blue", "darkblue", "darkred"] else "black"


            # Add circle for stations with precipitation
            folium.Marker(
                location=[lat, lon],
                tooltip=f"{station_name}<br>Total Monthly Precipitation: {display_precip} mm",
                icon=folium.DivIcon(
                    html=f"""
                    <div style="position: relative; transform: translate(-50%, -50%);">
                        <svg xmlns="http://www.w3.org/2000/svg" height="40" width="40" viewBox="0 0 40 40">
                            <circle cx="20" cy="20" r="15" style="fill:{precip_color};stroke:black;stroke-width:1;fill-opacity:0.6;" />
                            <text x="20" y="25" text-anchor="middle" fill="{text_color}" font-size="14" font-weight="bold">{display_precip}</text>
                        </svg>
                    </div>
                    """
                ),
            ).add_to(m_precip)

    # Display the map in Streamlit
    st_folium(m_precip, width=1200, height=600)

    ##### Plot WIND SPEED Precipitation ##########
    st.header("Section 3: Wind Analysis")


    # Ensure the session state key for wind analysis prompt exists
    if "wind_analysis_prompt" not in st.session_state:
        st.session_state["wind_analysis_prompt"] = ""

    # Button to generate the wind analysis ChatGPT prompt
    if st.button("Generate a ChatGPT Prompt", key="wind_analysis_button"):
        # Prepare combined data for the prompt
        wind_data = []

        for station_name, df in filtered_dataframes.items():
            if df.empty:
                continue  # Skip empty dataframes

            # Extract wind speed statistics
            stats = {}
            for key, column_variants in {
                "avg": ["U-sonic wind speed (avg)", "Wind speed (avg)"],
                "max": ["U-sonic wind speed (max)", "Wind speed (max)"],
                "gust": ["Wind gust (max)"],
            }.items():
                matching_col = next((col for col in column_variants if col in df.columns), None)
                if matching_col:
                    df[matching_col] = pd.to_numeric(df[matching_col], errors="coerce")
                    # For each metric, we compute the average of averages and maximum of maximums
                    stats[key] = {
                        "avg_of_avg": df[matching_col].mean(),  # Average of daily averages
                        "max_of_max": df[matching_col].max(),  # Maximum of daily maximums
                    }
            
            # Convert wind speeds to km/h for all 6 metrics
            avg_of_avg_speed_kmh = round(stats["avg"]["avg_of_avg"] * 3.6, 1) if "avg" in stats else None
            max_of_avg_speed_kmh = round(stats["avg"]["max_of_max"] * 3.6, 1) if "avg" in stats else None
            avg_of_max_speed_kmh = round(stats["max"]["avg_of_avg"] * 3.6, 1) if "max" in stats else None
            max_of_max_speed_kmh = round(stats["max"]["max_of_max"] * 3.6, 1) if "max" in stats else None
            avg_of_gust_kmh = round(stats["gust"]["avg_of_avg"] * 3.6, 1) if "gust" in stats else None
            max_of_gust_kmh = round(stats["gust"]["max_of_max"] * 3.6, 1) if "gust" in stats else None

            # Append wind data
            wind_data.append({
                "Station": station_name,
                "Average of Average Wind Speed (km/h)": avg_of_avg_speed_kmh,
                "Maximum of Average Wind Speed (km/h)": max_of_avg_speed_kmh,
                "Average of Maximum Sustained Wind Speed (km/h)": avg_of_max_speed_kmh,
                "Maximum of Maximum Sustained Wind Speed (km/h)": max_of_max_speed_kmh,
                "Average of Maximum Gust (km/h)": avg_of_gust_kmh,
                "Maximum of Maximum Gust (km/h)": max_of_gust_kmh,
            })

        # Convert to a DataFrame for the prompt
        wind_analysis_df = pd.DataFrame(wind_data)

        # Generate and store the prompt in session state
        st.session_state["wind_analysis_prompt"] = generate_chart_prompt(
            data=wind_analysis_df,
            selected_month=selected_month,
            chart_title="Wind Speed Analysis",
            instructions=(
                "Review the wind speed statistics for each location for the selected month. The data includes six key values for wind speed at each location:\n"
                "- The average of the daily average wind speeds\n"
                "- The highest daily average wind speed recorded\n"
                "- The average of the daily maximum sustained wind speeds\n"
                "- The highest daily maximum sustained wind speed recorded\n"
                "- The average of the daily maximum gusts\n"
                "- The highest daily maximum gust recorded\n\n"
                "Please explain these statistics in a simple and easy-to-understand way for a general audience. "
                "Describe how these wind conditions might impact everyday life, including infrastructure, the likelihood of dust storms, "
                "and how they might affect vulnerable populations like internally displaced persons (IDPs). "
                "Avoid using technical terms and focus on providing clear, practical explanations of what the data means."
            )
        )


    # Display the generated prompt, if available
    if "wind_analysis_prompt" in st.session_state and st.session_state["wind_analysis_prompt"]:
        st.markdown(
            f"Copy this prompt into [ChatGPT](https://chatgpt.com/) to generate a report:",
            unsafe_allow_html=True
        )
        st.text_area("Click in the text box and press Ctrl+A then Ctrl+C.", value=st.session_state["wind_analysis_prompt"], height=100)


    st.subheader("3.1 Average Daily Wind Speeds by Location")

    # Define the wind speed column variations
    wind_columns = {
        "avg": ["U-sonic wind speed (avg)", "Wind speed (avg)"],
        "max": ["U-sonic wind speed (max)", "Wind speed (max)"],
        "gust": ["Wind gust (max)"],
    }

    # Compute average monthly wind speed statistics
    wind_speed_stats = {}
    for station_name, df in filtered_dataframes.items():
        stats = {}
        for key, column_variants in wind_columns.items():
            # Find the appropriate column in the dataframe
            matching_col = next((col for col in column_variants if col in df.columns), None)
            if matching_col:
                df[matching_col] = pd.to_numeric(df[matching_col], errors="coerce")
                # Calculate the average over the month
                stats[key] = df[matching_col].mean()
        wind_speed_stats[station_name] = stats

    # Convert wind speed stats to a DataFrame for easier processing
    wind_speed_df = pd.DataFrame.from_dict(wind_speed_stats, orient="index")
    wind_speed_df.reset_index(inplace=True)
    wind_speed_df.rename(columns={"index": "Station"}, inplace=True)

    # Radio buttons for statistic selection
    stats_mapping = {
        "Average Daily Average Wind Speed (km/h)": "avg",
        "Average Daily Sustained Maximum Wind Speed (km/h)": "max",
        "Average Daily Maximum Gust (km/h)": "gust",
    }

    statistic = st.radio(
        "Select the wind speed statistic to display on the map:",
        options=list(stats_mapping.keys()),
        index=0,
        horizontal=True
    )

    # Get the selected column
    selected_stat_col = stats_mapping[statistic]

    m = folium.Map(
        location=[adjusted_map_center_lat, map_center_lon], 
        zoom_start=9,
        tiles="CartoDB Voyager"  # Use CartoDB Positron tiles for English place names
    )

    # Add wind speed markers to the map
    for station_name, stats in wind_speed_stats.items():
        # Get station info
        station_row = station_status[station_status["Custom Name"] == station_name]
        if station_row.empty or selected_stat_col not in stats:
            continue  # Skip if no data for the selected stat

        lat = station_row["Latitude"].values[0]
        lon = station_row["Longitude"].values[0]
        wind_value = stats[selected_stat_col]
        if pd.isna(wind_value):
            continue  # Skip if wind value is NaN

        # Get color for the wind value in m/s
        color = get_color_scheme(wind_value, "Wind Speed (m/s)")

        # Convert wind speed to km/h for display
        wind_value_kmh = round(wind_value * 3.6, 0)  # 1 m/s = 3.6 km/h

        # Determine text color
        text_color = "white" if color in ["blue", "darkblue", "darkred"] else "black"

        # Add a CircleMarker with SVG icon for the station
        folium.Marker(
            location=[lat, lon],
            tooltip=f"{station_name}<br>{statistic}: {wind_value_kmh:.0f} km/h",
            icon=folium.DivIcon(
                html=f"""
                <div style="position: relative; transform: translate(-50%, -50%);">
                    <svg xmlns="http://www.w3.org/2000/svg" height="40" width="40" viewBox="0 0 40 40">
                        <circle cx="20" cy="20" r="15" style="fill:{color};stroke:black;stroke-width:1;fill-opacity:0.6;" />
                        <text x="20" y="25" text-anchor="middle" fill="{text_color}" font-size="14" font-weight="bold">{int(wind_value_kmh)}</text>
                    </svg>
                </div>
                """
            ),
        ).add_to(m)

    # Display the map
    st_folium(m, width=1200, height=600)

    #### WIND SPEED - MAXIMUMS #####

    st.subheader("3.2 Maximum Daily Wind Speeds by Location")

    # Define the wind speed column variations
    wind_columns = {
        "avg": ["U-sonic wind speed (avg)", "Wind speed (avg)"],
        "max": ["U-sonic wind speed (max)", "Wind speed (max)"],
        "gust": ["Wind gust (max)"],
    }

    # Compute wind speed statistics
    wind_speed_stats = {}
    for station_name, df in filtered_dataframes.items():
        stats = {}
        for key, column_variants in wind_columns.items():
            # Find the appropriate column in the dataframe
            matching_col = next((col for col in column_variants if col in df.columns), None)
            if matching_col:
                df[matching_col] = pd.to_numeric(df[matching_col], errors="coerce")
                # Calculate 1-day max
                stats[key] = df[matching_col].max()
        wind_speed_stats[station_name] = stats

    # Convert wind speed stats to a DataFrame for easier processing
    wind_speed_df = pd.DataFrame.from_dict(wind_speed_stats, orient="index")
    wind_speed_df.reset_index(inplace=True)
    wind_speed_df.rename(columns={"index": "Station"}, inplace=True)

    # Radio buttons for statistic selection
    stats_mapping = {
        "Maximum Daily Average Wind Speed (km/h)": "avg",
        "Maximum Daily Sustained Maximum Wind Speed (km/h)": "max",
        "Maximum Daily Maximum Gust (km/h)": "gust",
    }

    statistic = st.radio(
        "Select the wind speed statistic to display on the map:",
        options=list(stats_mapping.keys()),
        index=0,
        horizontal=True
    )

    # Get the selected column
    selected_stat_col = stats_mapping[statistic]

    m = folium.Map(
        location=[adjusted_map_center_lat, map_center_lon], 
        zoom_start=9,
        tiles="CartoDB Voyager"  # Use CartoDB Positron tiles for English place names
    )

    # Add wind speed markers to the map
    for station_name, stats in wind_speed_stats.items():
        # Get station info
        station_row = station_status[station_status["Custom Name"] == station_name]
        if station_row.empty or selected_stat_col not in stats:
            continue  # Skip if no data for the selected stat

        lat = station_row["Latitude"].values[0]
        lon = station_row["Longitude"].values[0]
        wind_value = stats[selected_stat_col]
        if pd.isna(wind_value):
            continue  # Skip if wind value is NaN

        # Get color for the wind value in m/s
        color = get_color_scheme(wind_value, "Wind Speed (m/s)")

        # Convert wind speed to km/h for display
        wind_value_kmh = round(wind_value * 3.6, 0)  # 1 m/s = 3.6 km/h

        # Determine text color
        text_color = "white" if color in ["blue", "darkblue", "darkred"] else "black"

        # Add a CircleMarker with SVG icon for the station
        folium.Marker(
            location=[lat, lon],
            tooltip=f"{station_name}<br>{statistic}: {wind_value_kmh:.0f} km/h",
            icon=folium.DivIcon(
                html=f"""
                <div style="position: relative; transform: translate(-50%, -50%);">
                    <svg xmlns="http://www.w3.org/2000/svg" height="40" width="40" viewBox="0 0 40 40">
                        <circle cx="20" cy="20" r="15" style="fill:{color};stroke:black;stroke-width:1;fill-opacity:0.7;" />
                        <text x="20" y="25" text-anchor="middle" fill="{text_color}" font-size="14" font-weight="bold">{int(wind_value_kmh)}</text>
                    </svg>
                </div>
                """
            ),
        ).add_to(m)

    # Display the map
    st_folium(m, width=1200, height=600)



else:
    st.error("Station data is not available. Please check the Live Weather page.")


st.markdown("---")  # Horizontal line for separation
st.markdown(
    """
    ### References
    
    1. **World Bank Group. (n.d.).** *Syrian Arab Republic - Climatology*. Climate Change Knowledge Portal. Retrieved December 8, 2024, from [https://climateknowledgeportal.worldbank.org/country/syrian-arab-republic/climate-data-historical](https://climateknowledgeportal.worldbank.org/country/syrian-arab-republic/climate-data-historical)

    ---
    """,
    unsafe_allow_html=True
)
