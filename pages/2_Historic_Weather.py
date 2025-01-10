import streamlit as st
import pandas as pd
from datetime import datetime
import calendar
import plotly.graph_objects as go
from scripts.utils import connect_to_weather_stations, fetch_historic_data, configure_sidebar

# Page configuration
st.set_page_config(page_title="Historic Data", page_icon="🌤️", layout="wide")

# Sidebar configuration
configure_sidebar()

# Ensure station data is available in session state
if not "station_status" in st.session_state:
    connect_to_weather_stations()

# Title and instructions
st.title("Historic Weather Station Data")

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
    st.write("View and analyse historical weather data for selected stations.")

    # Generate the last 12 full months for selection
    today = datetime.today()
    earliest_date = datetime(2024, 4, 1)

    previous_months = [
        (today.replace(day=1) - pd.DateOffset(months=i)).strftime("%B %Y")
        for i in range(60)
    ]
    previous_months = [
        month for month in previous_months
        if datetime.strptime(month, "%B %Y") >= earliest_date
    ]

    # Toggle between date range and month selection
    toggle_view = st.radio(
        "Select date input method:",
        ("Entire Month", "Custom Date Range"),
        help="Choose to select a custom date range or an entire month for analysis."
    )

    if toggle_view == "Entire Month":
        # Month selection dropdown
        selected_month = st.selectbox("Select a month to analyse:", previous_months)
        selected_month_name, selected_year = selected_month.split()
        selected_year = int(selected_year)
        selected_month_number = list(calendar.month_name).index(selected_month_name)

        start_date = datetime(selected_year, selected_month_number, 1)
        end_date = datetime(
            selected_year,
            selected_month_number,
            calendar.monthrange(selected_year, selected_month_number)[1],
        )
    else:
        # Custom date range input
        def get_date_range(dataframes):
            combined_dates = pd.concat(
                [pd.to_datetime(df["Date/Time"], errors="coerce") for df in dataframes.values() if "Date/Time" in df.columns]
            ).dropna()
            return combined_dates.min().date(), combined_dates.max().date()

        min_date, max_date = get_date_range(historic_dataframes)
        date_range = st.date_input(
            "Select date range for the plot:",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        if len(date_range) == 2:
            start_date, end_date = date_range
        else:
            st.warning("Please select a valid date range.")
            st.stop()

    # Get available variable names across all stations
    all_columns = set()
    for df in historic_dataframes.values():
        all_columns.update(df.columns)
    all_columns = sorted(all_columns)

    # Dropdown for variable selection
    variable = st.selectbox(
        "Select a variable to plot:",
        options=all_columns,
        help="Choose the variable you want to visualize across stations.",
    )


    # Format the start_date and end_date dynamically
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    st.subheader(f"{variable} Across All Locations ({start_date_str} to {end_date_str})")

    # Prepare data for plotting
    warning_messages = []
    plot_data = []

    for station_name, df in historic_dataframes.items():
        if "Date/Time" not in df.columns:
            warning_messages.append(f"The 'Date/Time' column is missing for station {station_name}.")
            continue

        matching_column = next((col for col in df.columns if variable in col), None)
        if not matching_column:
            warning_messages.append(f"The variable '{variable}' is missing for station {station_name}.")
            continue

        # Filter data for the selected range
        df["Date/Time"] = pd.to_datetime(df["Date/Time"])
        filtered_df = df[(df["Date/Time"] >= pd.Timestamp(start_date)) & (df["Date/Time"] <= pd.Timestamp(end_date))]

        if not filtered_df.empty:
            plot_data.append(
                pd.DataFrame({
                    "Date/Time": filtered_df["Date/Time"],
                    "Value": filtered_df[matching_column],
                    "Station": station_name
                })
            )

    if plot_data:
        combined_df = pd.concat(plot_data)
        combined_df = combined_df.pivot(index="Date/Time", columns="Station", values="Value")

        combined_df = combined_df.reindex(
            pd.date_range(start_date, end_date, freq="D"), fill_value=None
        )

        fig = go.Figure()
        for station in combined_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=combined_df.index,
                    y=combined_df[station],
                    mode="lines",
                    name=station,
                )
            )

        fig.update_layout(
            xaxis_title="Date",
            yaxis_title=variable,
            legend_title="Weather Stations",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        if warning_messages:
            st.warning("The following issues were encountered:\n- " + "\n- ".join(warning_messages))

    # View detailed station data
    selected_station = st.selectbox(
        "**Select a weather station to view more details:**",
        station_status["Custom Name"].unique(),
        help="Choose a station to view its data.",
    )




    if selected_station in historic_dataframes:
        station_data = historic_dataframes[selected_station]

        if "Date/Time" in station_data.columns:
            station_data["Date/Time"] = pd.to_datetime(station_data["Date/Time"])
            filtered_data = station_data[
                (station_data["Date/Time"] >= pd.Timestamp(start_date))
                & (station_data["Date/Time"] <= pd.Timestamp(end_date))
            ]


            # Use formatted dates in the table header
            st.subheader(f"Data for {selected_station} ({start_date_str} to {end_date_str})")
            st.dataframe(filtered_data.reset_index(drop=True))
        else:
            st.error("The selected station's data does not contain a 'Date/Time' column.")
    else:
        st.error("No data available for the selected station.")
else:
    st.error("Station data is not available. Please check the Live Weather page.")
