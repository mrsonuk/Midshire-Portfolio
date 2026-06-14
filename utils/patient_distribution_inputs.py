# Imports
import random
import json


# Function to return t_nhpp: Determines rate at which patients arrive in ED. It differs depending on hour of day.
def get_nhpp(time, daily_num_patients):

    # Initial transformations
    hours = round(time // 60)
    hour_of_the_day = hours % 24

    # This reads in the average hourly arrivals from the config file
    with open("config.json") as file:
        config = json.load(file)

    # If data in config file
    if config["Hourly_Arrivals"][str(hour_of_the_day)]:
        avg_arrivals = config["Hourly_Arrivals"][str(hour_of_the_day)]

        # In case we don't have accurate numbers for avg arrivals we can use the profile of arrivals
        # (i.e. get the proportion of arrivals in that hour from PAH but not use the absolute numbers)
        proportion_arrivals = avg_arrivals / sum(config["Hourly_Arrivals"].values())

        expected_arrivals = proportion_arrivals * daily_num_patients

        # To get lambda for the expovariate distribution we get the expected arrivals by minute
        rate = 1 / (expected_arrivals / 60)

        # Return value
        return rate

    # Else throw error
    else:
        return 'Please introduce a valid value for the number of hourly arrivals'

# Function to get maximum waiting time of a patient, i.e. their patience.


def get_max_waiting_time():

    # Open config file
    with open("config.json") as file:
        config = json.load(file)

    # Get max waiting time data (patience)
    max_waiting_times = config["Max_Waiting_Times"]
    max_waiting_time = random.choices(list(max_waiting_times), weights=list(max_waiting_times.values()))[0]

    # Return value
    return int(max_waiting_time)
