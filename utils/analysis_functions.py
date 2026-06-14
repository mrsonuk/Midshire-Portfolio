# Imports
import pandas as pd

# Function to get room list


def get_room_list(events, room):
    room_list = []
    # This lists the treatment rooms
    treatment_rooms = ['waiting room', 'minors', 'majors', 'resus', 'sdec']
    
    # Create list of possible events depending on room
    if room in treatment_rooms:
        possible_events = ['Got ' + room, 'Left ' + room]
    elif room == 'department':
        possible_events = ['Arrived', 'Finished discharge', 'Finished admission']
    elif room == 'corridor':
        possible_events = ['Started discharge', 'Started admission', 'Finished discharge', 'Finished admission']
    else:
        return 'Not a valid room'

    # Looping through the events to append to room_list, append spot occupied or released depending on event
    for key in events.keys():
        for event in events[key]:
            if event[0] in possible_events:
                if event[0] in ['Got ' + room, 'Arrived', 'Started discharge', 'Started admission']:
                    room_list.append((key, 'spot occupied', event[1]))
                elif event[0] in ['Left ' + room, 'Finished discharge', 'Finished admission']:
                    room_list.append((key, 'spot released', event[1]))

    return room_list
    

# Function to get patients in room


def get_patients_in_room(room_list):
    patients_in_room = {}
    for i in sorted(room_list, key=lambda x: x[2]):
        if len(patients_in_room.keys()) == 0:
            if i[1] == 'spot occupied':
                patients_in_room[i[2]] = [i[0]]
        else:
            if i[1] == 'spot occupied':
                patients_in_room[i[2]] = list(patients_in_room.values())[-1].copy()
                patients_in_room[i[2]].append(i[0])
            elif i[1] == 'spot released':
                patients_in_room[i[2]] = list(patients_in_room.values())[-1].copy()
                patients_in_room[i[2]].remove(i[0])
    return patients_in_room

# Function to get number of people in room


def get_no_room(patients_in_room):
    no_room = {}
    for key in patients_in_room.keys():
        no_room[key] = len(patients_in_room[key])
    return no_room

# Function to get plot values


def get_plot_values(no_room, time_step):
    data = pd.DataFrame()
    key = list(no_room.keys())[0]
    days = int(key / 60 / 24)
    hours = int(key / 60 % 24)
    minutes = int(key % 60)
    date = pd.to_datetime('2023-10-01 00:00:00') + pd.Timedelta(pd.offsets.Day(days)) + pd.Timedelta(
        pd.offsets.Hour(hours)) + pd.Timedelta(pd.offsets.Minute(minutes))
    plot_keys = [date]
    plot_values = [list(no_room.values())[0]]
    all_keys = list(no_room.keys())
    initial = all_keys[0]
    for i, key in enumerate(all_keys[1:]):
        if key - initial >= time_step:
            days = int(key / 60 / 24)
            hours = int(key / 60 % 24)
            minutes = int(key % 60)
            date = pd.to_datetime('2023-10-01 00:00:00') + pd.Timedelta(pd.offsets.Day(days)) + pd.Timedelta(
                pd.offsets.Hour(hours)) + pd.Timedelta(pd.offsets.Minute(minutes))
            plot_keys.append(date)
            plot_values.append(no_room[key])
            initial = key

    data['Time'] = plot_keys
    data['Occupied Seats'] = plot_values
    return data

# Function to get room data


def get_room_data(events, room, time_step=15):
    room_list = get_room_list(events, room=room)
    patients_in_room = get_patients_in_room(room_list)
    no_room = get_no_room(patients_in_room)
    data = get_plot_values(no_room, time_step)
    return patients_in_room, no_room, data

# Function to create a data frame for no_in_room


def create_initial_df(no_room):
    number, hours_day, day = [], [], []
    for key, value in no_room.items():
        hour_day = key/60 % 24
        hours_day.append(int(hour_day))
        day.append(int(key/60/24))
        number.append(value)
    no_in_room = pd.DataFrame()
    no_in_room['Hour of Day'] = hours_day
    no_in_room['Day'] = day
    no_in_room['Minutes Passed'] = no_room.keys()
    no_in_room['Occupancy'] = no_room.values()
    no_in_room['Min minutes'] = no_in_room['Day']*60*24 + (no_in_room['Hour of Day'])*60
    no_in_room['Max minutes'] = no_in_room['Day']*60*24 + (no_in_room['Hour of Day']+1)*60
    data = []
    data.insert(0, {'Hour of Day': 0, 'Minutes Passed': 0, 'Occupancy': 0, 'Day': 0, 'Min minutes': 0,
                    'Max minutes': 0})
    no_in_room = pd.concat([pd.DataFrame(data), no_in_room], ignore_index=True)
    return no_in_room

# Function to get minutes passed differences by room


def update_minutes_passed_diff(no_in_room):
    no_in_room['Minutes Passed Diff'] = no_in_room['Minutes Passed'].diff().shift(-1)
    return no_in_room

# Function to process by day and hour by room


def process_by_day_and_hour(no_in_room):
    final_room = pd.DataFrame()
    for day in sorted(no_in_room['Day'].unique()):
        no_in_room_subset = no_in_room.loc[no_in_room['Day'] == day]

        # Force data to be generated for all hours of the day
        for hour in list(range(0, 24)):
            # The logic inside this nested loop can potentially be another function
            no_in_room_day = no_in_room_subset.loc[no_in_room_subset['Hour of Day'] == hour]
            if no_in_room_day.shape[0] != 0:
                min_idx = min(no_in_room_day.index)
                max_idx = max(no_in_room_day.index)
                data_begin = []
                data_begin.insert(0, {'Hour of Day': hour, 'Minutes Passed': no_in_room_day.iloc[0]['Min minutes'],
                                      'Occupancy': no_in_room.iloc[min_idx-1]['Occupancy'], 'Day': day,
                                      'Min minutes': no_in_room_day.iloc[0]['Min minutes'],
                                      'Max minutes': no_in_room_day.iloc[0]['Max minutes'],
                                      'Minutes Passed Diff':
                                          no_in_room_day.iloc[0]['Minutes Passed'] -
                                          no_in_room_day.iloc[0]['Min minutes']})
                no_in_room_day.at[max_idx, 'Minutes Passed Diff'] =\
                    no_in_room_day.iloc[no_in_room_day.shape[0]-1]['Max minutes'] -\
                    no_in_room_day.iloc[no_in_room_day.shape[0]-1]['Minutes Passed']
                no_in_room_day = pd.concat([pd.DataFrame(data_begin), no_in_room_day], ignore_index=True)
                if final_room.empty:
                    final_room = no_in_room_day
                else:
                    final_room = pd.concat([final_room, no_in_room_day])
            else:
                data_begin = []
                data_begin.insert(0, {'Hour of Day': hour, 'Minutes Passed': day*60*24 + hour*60,
                                      'Occupancy': no_in_room.iloc[max_idx]['Occupancy'], 'Day': day,
                                      'Min minutes': day*60*24 + hour*60, 'Max minutes': day*60*24 + (hour+1)*60,
                                      'Minutes Passed Diff': 60})
                if final_room.empty:
                    final_room = pd.DataFrame(data_begin)
                else:
                    final_room = pd.concat([final_room, pd.DataFrame(data_begin)])
    return final_room

# Function to calculate mean occupancy by room


def calculate_mean_occupancy(final_room):
    final_room = final_room.loc[final_room.Day != 0]
    mean_occupancy = {}
    for hour in final_room['Hour of Day'].unique():
        final_room_hour = final_room.loc[final_room['Hour of Day'] == hour]
        final_room_hourcopy = final_room_hour.copy()
        final_room_hourcopy['Mean Occupancy'] = final_room_hour['Occupancy'] * final_room_hour['Minutes Passed Diff']
        mean_occupancy[hour] = final_room_hourcopy['Mean Occupancy'].sum()/final_room_hour['Minutes Passed Diff'].sum()
    return mean_occupancy


# Function to get mean occupancy by room

def get_mean_occupancy(no_room):
    no_in_room = create_initial_df(no_room)
    no_in_room = update_minutes_passed_diff(no_in_room)
    final_room = process_by_day_and_hour(no_in_room)
    mean_occupancy = calculate_mean_occupancy(final_room)
    return final_room, mean_occupancy
