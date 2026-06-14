# Helper plotting functions

# Imports
import pandas as pd
import numpy as np

# Function for getting arrivals by hour


def get_arrivals_by_hour(arrival_time, time_category):
    non_day1 = [key for key, value in arrival_time.items() if value > 24 * 60 * 1]
    patients_graph_arrive = non_day1.copy()
    arrivals = pd.DataFrame()
    arrivals['PatientID'] = patients_graph_arrive
    arrival_times = [arrival_time[i] for i in arrivals.PatientID.values]
    arrivals['Arrival Time'] = [int((i % 1440) / 60) for i in arrival_times]
    arrivals['Arrival Days'] = [i // 1440 for i in arrival_times]
    acuities = []
    for key in arrivals.PatientID.values:
        acuities.append(time_category[key])
    arrivals['Acuity'] = acuities
    arrivals = pd.DataFrame(
        arrivals.groupby(['Arrival Time', 'Acuity', 'Arrival Days'])['PatientID'].count()).reset_index()

    all_df = pd.DataFrame()
    min_day = arrivals['Arrival Days'].min()
    max_day = arrivals['Arrival Days'].max()
    acuities = sorted(arrivals.Acuity.unique())

    times = []
    for i in range(int(max_day - min_day + 1) * len(acuities) * 24):
        times.append(int(i / (int(max_day - min_day + 1) * len(acuities))))

    acuity_list = []
    for i in range(len(times)):
        acuity_list.append('acuity ' + str(int((i / int(max_day - min_day + 1)) % 5) + 1))

    days = []
    for i in range(len(times) // int(max_day - min_day + 1)):
        days.extend(np.arange(min_day, max_day + 1))

    all_df['Arrival Time'] = times
    all_df['Acuity'] = acuity_list
    all_df['Arrival Days'] = days
    arrivals = pd.merge(all_df, arrivals, how='left', on=['Arrival Time', 'Acuity', 'Arrival Days'])
    arrivals.fillna(0, inplace=True)
    arrivals_df = pd.DataFrame(arrivals.groupby(['Arrival Time', 'Acuity'])['PatientID'].mean()).reset_index()
    arrivals_df.rename(columns={'PatientID': 'Count'}, inplace=True)
    bar_width = 0.7
    max_value = arrivals_df.groupby(['Arrival Time'])['Count'].sum().max()
    arrivals_df_1 = arrivals_df.loc[arrivals_df.Acuity == 'acuity 1']
    arrivals_df_2 = arrivals_df.loc[arrivals_df.Acuity == 'acuity 2']
    arrivals_df_3 = arrivals_df.loc[arrivals_df.Acuity == 'acuity 3']
    arrivals_df_4 = arrivals_df.loc[arrivals_df.Acuity == 'acuity 4']
    arrivals_df_5 = arrivals_df.loc[arrivals_df.Acuity == 'acuity 5']

    return arrivals_df, non_day1, arrivals_df_1, arrivals_df_2, arrivals_df_3, arrivals_df_4, arrivals_df_5, \
        bar_width, max_value

# Function for getting admissions and discharges by hour


def get_admissions_and_discharges_by_hour(time_until_admission, time_until_discharge, non_day1, arrival_time,
                                          time_category):

    time_until_a_or_d = pd.DataFrame()
    patients_a_or_d = set(time_until_admission.keys()).union(set(time_until_discharge.keys()))
    time_until_a_or_d['PatientID'] = [i for i in non_day1 if i in patients_a_or_d]
    time_until_a, time_until_d = [], []
    for patient in time_until_a_or_d['PatientID']:
        if patient in time_until_admission.keys():
            time_until_a.append(time_until_admission[patient])
        else:
            time_until_a.append(np.nan)
        if patient in time_until_discharge.keys():
            time_until_d.append(time_until_discharge[patient])
        else:
            time_until_d.append(np.nan)

    time_until_a_or_d['Time Until Admission (min)'] = np.array(time_until_a) - np.array(time_until_a) % 10
    time_until_a_or_d['Time Until Discharge (min)'] = np.array(time_until_d) - np.array(time_until_d) % 10

    arrival_times = [arrival_time[i] for i in time_until_a_or_d.PatientID.values]
    time_until_a_or_d['Arrival Time'] = [int((i % 1440) / 60) for i in arrival_times]
    acuities = []
    for key in time_until_a_or_d['PatientID']:
        acuities.append(time_category[key])
    time_until_a_or_d['Acuity'] = acuities

    time_until_a = time_until_a_or_d.loc[time_until_a_or_d['Time Until Admission (min)'].isnull() == False]

    time_until_a_copy = time_until_a.copy()

    time_until_a_copy['Time Until Admission (min)'] = [i if i < 12 * 60 else 12 * 60 for i in
                                                       time_until_a['Time Until Admission (min)']]
    admission_df = pd.DataFrame(
        time_until_a_copy.groupby(['Time Until Admission (min)', 'Acuity'])['PatientID'].count()).reset_index()
    admission_df['Time Until Admission (min)'] = [i if i < 12 * 60 else 12 * 60 for i in
                                                  admission_df['Time Until Admission (min)']]
    admission = pd.DataFrame()
    length = len(np.arange(0, 730, 10))
    time_until_ad = []
    for i in range(5):
        time_until_ad.extend(np.arange(0, 730, 10))
    admission['Time Until Admission (min)'] = time_until_ad
    acuity_list = []
    for i in range(5 * length):
        acuity_list.append('acuity ' + str(int((i / 73) % 5) + 1))
    admission['Acuity'] = acuity_list
    admission = pd.merge(admission, admission_df, how='left', on=['Time Until Admission (min)', 'Acuity'])
    admission.fillna(0, inplace=True)
    admission.rename(columns={'PatientID': 'Number Admitted'}, inplace=True)

    # Metrics by acuity
    admission_a1 = admission.copy()
    admission_a2 = admission.copy()
    admission_a3 = admission.copy()
    admission_a4 = admission.copy()
    admission_a5 = admission.copy()

    admission['Perc Admitted'] = admission['Number Admitted'] / time_until_a_or_d.shape[0] * 100
    max_value = max(admission.groupby('Time Until Admission (min)')['Perc Admitted'].sum())

    # Metrics by acuity
    admission_a1['Perc Admitted'] = admission_a1.loc[admission_a1['Acuity'] == 'acuity 1']['Number Admitted'] / \
        time_until_a_or_d.loc[time_until_a_or_d['Acuity'] == 'acuity 1'].shape[0] * 100
    admission_a2['Perc Admitted'] = admission_a2.loc[admission_a2['Acuity'] == 'acuity 2']['Number Admitted'] / \
        time_until_a_or_d.loc[time_until_a_or_d['Acuity'] == 'acuity 2'].shape[0] * 100
    admission_a3['Perc Admitted'] = admission_a3.loc[admission_a3['Acuity'] == 'acuity 3']['Number Admitted'] / \
        time_until_a_or_d.loc[time_until_a_or_d['Acuity'] == 'acuity 3'].shape[0] * 100
    admission_a4['Perc Admitted'] = admission_a4.loc[admission_a4['Acuity'] == 'acuity 4']['Number Admitted'] / \
        time_until_a_or_d.loc[time_until_a_or_d['Acuity'] == 'acuity 4'].shape[0] * 100
    admission_a5['Perc Admitted'] = admission_a5.loc[admission_a5['Acuity'] == 'acuity 5']['Number Admitted'] / \
        time_until_a_or_d.loc[time_until_a_or_d['Acuity'] == 'acuity 5'].shape[0] * 100

    adms_4hr = admission.loc[admission['Time Until Admission (min)'] <= 240]['Perc Admitted'].sum()
    adms_12hr = admission.loc[admission['Time Until Admission (min)'] == 720]['Perc Admitted'].sum()

    # Metrics by acuity
    adms_4hr_a1 = admission_a1.loc[admission_a1['Time Until Admission (min)'] <= 240]['Perc Admitted'].sum()
    adms_4hr_a2 = admission_a2.loc[admission_a2['Time Until Admission (min)'] <= 240]['Perc Admitted'].sum()
    adms_4hr_a3 = admission_a3.loc[admission_a3['Time Until Admission (min)'] <= 240]['Perc Admitted'].sum()
    adms_4hr_a4 = admission_a4.loc[admission_a4['Time Until Admission (min)'] <= 240]['Perc Admitted'].sum()
    adms_4hr_a5 = admission_a5.loc[admission_a5['Time Until Admission (min)'] <= 240]['Perc Admitted'].sum()
    adms_12hr_a1 = admission_a1.loc[admission_a1['Time Until Admission (min)'] == 720]['Perc Admitted'].sum()
    adms_12hr_a2 = admission_a2.loc[admission_a2['Time Until Admission (min)'] == 720]['Perc Admitted'].sum()
    adms_12hr_a3 = admission_a3.loc[admission_a3['Time Until Admission (min)'] == 720]['Perc Admitted'].sum()
    adms_12hr_a4 = admission_a4.loc[admission_a4['Time Until Admission (min)'] == 720]['Perc Admitted'].sum()
    adms_12hr_a5 = admission_a5.loc[admission_a5['Time Until Admission (min)'] == 720]['Perc Admitted'].sum()

    time_until_d = time_until_a_or_d.loc[time_until_a_or_d['Time Until Discharge (min)'].isnull() == False]

    time_until_d_copy = time_until_d.copy()

    time_until_d_copy['Time Until Discharge (min)'] = [i if i < 12 * 60 else 12 * 60 for i in
                                                       time_until_d['Time Until Discharge (min)']]
    discharge_df = pd.DataFrame(
        time_until_d_copy.groupby(['Time Until Discharge (min)', 'Acuity'])['PatientID'].count()).reset_index()
    discharge_df['Time Until Discharge (min)'] = [i if i < 12 * 60 else 12 * 60 for i in
                                                  discharge_df['Time Until Discharge (min)']]
    discharge = pd.DataFrame()
    length = len(np.arange(0, 730, 10))
    time_until_dis = []
    for i in range(5):
        time_until_dis.extend(np.arange(0, 730, 10))
    discharge['Time Until Discharge (min)'] = time_until_dis
    acuity_list = []
    for i in range(5 * length):
        acuity_list.append('acuity ' + str(int((i / 73) % 5) + 1))
    discharge['Acuity'] = acuity_list
    discharge = pd.merge(discharge, discharge_df, how='left', on=['Time Until Discharge (min)', 'Acuity'])

    discharge.fillna(0, inplace=True)
    discharge.rename(columns={'PatientID': 'Number Discharged'}, inplace=True)

    # Metrics by acuity
    discharge_a1 = discharge.copy()
    discharge_a2 = discharge.copy()
    discharge_a3 = discharge.copy()
    discharge_a4 = discharge.copy()
    discharge_a5 = discharge.copy()

    discharge['Perc Discharged'] = -discharge['Number Discharged'] / time_until_a_or_d.shape[0] * 100
    min_value = min(discharge.groupby('Time Until Discharge (min)')['Perc Discharged'].sum())

    # Metrics by acuity
    discharge_a1['Perc Discharged'] = -discharge_a1.loc[discharge_a1['Acuity'] == 'acuity 1']['Number Discharged'] / \
        time_until_a_or_d.loc[time_until_a_or_d['Acuity'] == 'acuity 1'].shape[0] * 100
    discharge_a2['Perc Discharged'] = -discharge_a2.loc[discharge_a2['Acuity'] == 'acuity 2']['Number Discharged'] / \
        time_until_a_or_d.loc[time_until_a_or_d['Acuity'] == 'acuity 2'].shape[0] * 100
    discharge_a3['Perc Discharged'] = -discharge_a3.loc[discharge_a3['Acuity'] == 'acuity 3']['Number Discharged'] / \
        time_until_a_or_d.loc[time_until_a_or_d['Acuity'] == 'acuity 3'].shape[0] * 100
    discharge_a4['Perc Discharged'] = -discharge_a4.loc[discharge_a4['Acuity'] == 'acuity 4']['Number Discharged'] / \
        time_until_a_or_d.loc[time_until_a_or_d['Acuity'] == 'acuity 4'].shape[0] * 100
    discharge_a5['Perc Discharged'] = -discharge_a5.loc[discharge_a5['Acuity'] == 'acuity 5']['Number Discharged'] / \
        time_until_a_or_d.loc[time_until_a_or_d['Acuity'] == 'acuity 5'].shape[0] * 100

    discharge_4hr = discharge.loc[discharge['Time Until Discharge (min)'] <= 240]['Perc Discharged'].sum()
    discharge_12hr = discharge.loc[discharge['Time Until Discharge (min)'] == 720]['Perc Discharged'].sum()

    # Metrics by acuity
    discharge_4hr_a1 = discharge_a1.loc[discharge_a1['Time Until Discharge (min)'] <= 240]['Perc Discharged'].sum()
    discharge_4hr_a2 = discharge_a2.loc[discharge_a2['Time Until Discharge (min)'] <= 240]['Perc Discharged'].sum()
    discharge_4hr_a3 = discharge_a3.loc[discharge_a3['Time Until Discharge (min)'] <= 240]['Perc Discharged'].sum()
    discharge_4hr_a4 = discharge_a4.loc[discharge_a4['Time Until Discharge (min)'] <= 240]['Perc Discharged'].sum()
    discharge_4hr_a5 = discharge_a5.loc[discharge_a5['Time Until Discharge (min)'] <= 240]['Perc Discharged'].sum()
    discharge_12hr_a1 = discharge_a1.loc[discharge_a1['Time Until Discharge (min)'] == 720]['Perc Discharged'].sum()
    discharge_12hr_a2 = discharge_a2.loc[discharge_a2['Time Until Discharge (min)'] == 720]['Perc Discharged'].sum()
    discharge_12hr_a3 = discharge_a3.loc[discharge_a3['Time Until Discharge (min)'] == 720]['Perc Discharged'].sum()
    discharge_12hr_a4 = discharge_a4.loc[discharge_a4['Time Until Discharge (min)'] == 720]['Perc Discharged'].sum()
    discharge_12hr_a5 = discharge_a5.loc[discharge_a5['Time Until Discharge (min)'] == 720]['Perc Discharged'].sum()

    adm_1 = admission.loc[admission.Acuity == 'acuity 1']
    adm_2 = admission.loc[admission.Acuity == 'acuity 2']
    adm_3 = admission.loc[admission.Acuity == 'acuity 3']
    adm_4 = admission.loc[admission.Acuity == 'acuity 4']
    adm_5 = admission.loc[admission.Acuity == 'acuity 5']
    disc_1 = discharge.loc[discharge.Acuity == 'acuity 1']
    disc_2 = discharge.loc[discharge.Acuity == 'acuity 2']
    disc_3 = discharge.loc[discharge.Acuity == 'acuity 3']
    disc_4 = discharge.loc[discharge.Acuity == 'acuity 4']
    disc_5 = discharge.loc[discharge.Acuity == 'acuity 5']
    return min_value, max_value, admission, discharge, min_value, time_until_a_or_d, time_until_a_copy, \
        time_until_d_copy, adms_4hr, discharge_4hr, adms_12hr, discharge_12hr, adm_1, adm_2, adm_3, adm_4, adm_5,\
        disc_1, disc_2, disc_3, disc_4, disc_5

# Function for getting time in department by hour


def get_time_in_department_by_hour(arrival_time, time_until_admission, time_until_discharge, time_until_a_or_d,
                                   waiting_time, time_category):
    non_day1 = [key for key, value in arrival_time.items() if value > 24 * 60 * 1]
    time_until_ad = pd.DataFrame()
    patients_a_or_d = set(time_until_admission.keys()).union(set(time_until_discharge.keys()))

    time_until_ad['PatientID'] = [i for i in non_day1 if i in patients_a_or_d]
    time_until_a_copy, time_until_d_copy = [], []
    for patient in time_until_a_or_d['PatientID']:
        if patient in time_until_admission.keys():
            time_until_a_copy.append(time_until_admission[patient])
        else:
            time_until_a_copy.append(np.nan)
        if patient in time_until_discharge.keys():
            time_until_d_copy.append(time_until_discharge[patient])
        else:
            time_until_d_copy.append(np.nan)

    time_until_ad['Time Until Admission (min)'] = np.array(time_until_a_copy)
    time_until_ad['Time Until Discharge (min)'] = np.array(time_until_d_copy)
    time_until_ad['Waiting Time (before A/D) (min)'] = [waiting_time[i] for i in time_until_ad['PatientID'].values]

    arrival_times = [arrival_time[i] for i in time_until_ad.PatientID.values]
    time_until_ad['Arrival Time'] = [int((i % 1440) / 60) for i in arrival_times]
    acuities = []
    for key in time_until_ad['PatientID']:
        acuities.append(time_category[key])
    time_until_ad['Acuity'] = acuities

    mean_time_overall, std_time_overall, longest_time = {}, {}, {}
    for acuity in ['acuity 1', 'acuity 2', 'acuity 3', 'acuity 4', 'acuity 5']:
        time_until_ad_ac = time_until_ad.loc[time_until_ad.Acuity == acuity]
        times_until_admission = list(
            time_until_ad_ac.loc[time_until_ad_ac['Time Until Admission (min)'].isnull() == False][
                'Time Until Admission (min)'].values)
        times_until_discharge = list(
            time_until_ad_ac.loc[time_until_ad_ac['Time Until Discharge (min)'].isnull() == False][
                'Time Until Discharge (min)'].values)
        times = times_until_admission + times_until_discharge

        mean_time_overall[acuity] = round(np.mean(times), 2)
        std_time_overall[acuity] = round(np.std(times), 2)
        longest_time[acuity] = round(np.max(times), 2)

    time_in_dept = time_until_ad.copy(deep=True)
    time_in_dept['Time in Dept (min)'] = [time_in_dept['Time Until Admission (min)'].values[i] if np.isnan(
        time_in_dept['Time Until Admission (min)'].values[i]) == False else
                                          time_in_dept['Time Until Discharge (min)'].values[i] for i in
                                          range(len(time_in_dept['Time Until Admission (min)'].values))]
    time_in_dept = pd.DataFrame(
        time_in_dept.groupby(['Arrival Time', 'Acuity'])['Time in Dept (min)'].mean()).reset_index()
    waiting_time_df = pd.DataFrame(
        time_until_ad.groupby(['Arrival Time', 'Acuity'])['Waiting Time (before A/D) (min)'].mean()).reset_index()
    time_in_dept = pd.merge(time_in_dept, waiting_time_df, how='left', on=['Arrival Time', 'Acuity'])
    wait_df = pd.DataFrame()
    length = len(np.arange(0, 24))
    arrival_hours = []
    for i in range(5):
        arrival_hours.extend(np.arange(0, 24))
    wait_df['Arrival Time'] = arrival_hours
    acuity_list = []
    for i in range(5 * length):
        acuity_list.append('acuity ' + str(int((i / length) % 5) + 1))
    wait_df['Acuity'] = acuity_list
    time_in_dept = pd.merge(time_in_dept, wait_df, how='right', on=['Arrival Time', 'Acuity'])
    time_in_dept.fillna(0, inplace=True)

    time_in_dept_1 = time_in_dept.loc[time_in_dept.Acuity == 'acuity 1']
    time_in_dept_2 = time_in_dept.loc[time_in_dept.Acuity == 'acuity 2']
    time_in_dept_3 = time_in_dept.loc[time_in_dept.Acuity == 'acuity 3']
    time_in_dept_4 = time_in_dept.loc[time_in_dept.Acuity == 'acuity 4']
    time_in_dept_5 = time_in_dept.loc[time_in_dept.Acuity == 'acuity 5']

    return time_in_dept, time_in_dept_1, time_in_dept_2, time_in_dept_3, time_in_dept_4, time_in_dept_5, \
        mean_time_overall, std_time_overall, longest_time

# Function to get time in department before and after crtp


def get_time_in_department_before_and_after_crtp(time_in_dept):
    time_in_dept_copy = time_in_dept.copy(deep=True)
    time_in_dept_copy['Time waiting for A/D (min)'] = time_in_dept_copy['Time in Dept (min)'] - time_in_dept_copy[
        'Waiting Time (before A/D) (min)']

    time_in_dept_1 = time_in_dept_copy.loc[time_in_dept_copy.Acuity == 'acuity 1']
    time_in_dept_2 = time_in_dept_copy.loc[time_in_dept_copy.Acuity == 'acuity 2']
    time_in_dept_3 = time_in_dept_copy.loc[time_in_dept_copy.Acuity == 'acuity 3']
    time_in_dept_4 = time_in_dept_copy.loc[time_in_dept_copy.Acuity == 'acuity 4']
    time_in_dept_5 = time_in_dept_copy.loc[time_in_dept_copy.Acuity == 'acuity 5']

    s1 = time_in_dept_1['Time in Dept (min)'].values
    s2 = time_in_dept_2['Time in Dept (min)'].values
    s3 = time_in_dept_3['Time in Dept (min)'].values
    s4 = time_in_dept_4['Time in Dept (min)'].values
    s5 = time_in_dept_5['Time in Dept (min)'].values
    max_value = max(max(s1), max(s2), max(s3), max(s4), max(s5))

    before_crtp = time_in_dept_1['Waiting Time (before A/D) (min)'].values
    after_crtp = time_in_dept_1['Time waiting for A/D (min)'].values

    return max_value, before_crtp, after_crtp, time_in_dept_1, time_in_dept_2, time_in_dept_3, time_in_dept_4, \
        time_in_dept_5

# Function for getting number of people who have left


def get_number_left(non_day1, left, time_category, arrival_time):
    no_left = {}
    no_left['acuity 1'] = 0
    no_left['acuity 2'] = 0
    no_left['acuity 3'] = 0
    no_left['acuity 4'] = 0
    no_left['acuity 5'] = 0
    for patient in non_day1:
        if left[patient] == True:
            acuity = time_category[patient]
            no_left[acuity] += 1 / int((max(arrival_time.values()) / 60) // 24)
    return no_left

# Function to get rooms list


def get_rooms_list(events):
    waiting_room_list, minors_list, majors_list, resus_list, sdec_list, department_list, \
        corridor_list, doctorslist, sdec_doctorslist, rat_doctorslist, nt_doctorslist =\
        [], [], [], [], [], [], [], [], [], [], []
    for key in events.keys():
        for event in events[key]:
            if event[0] == 'Got waiting room':
                waiting_room_list.append((key, 'spot occupied', event[1]))
            elif event[0] == 'Left waiting room':
                waiting_room_list.append((key, 'spot released', event[1]))
            elif event[0] == 'Got minors':
                minors_list.append((key, 'spot occupied', event[1]))
            elif event[0] == 'Left minors':
                minors_list.append((key, 'spot released', event[1]))
            elif event[0] == 'Got majors':
                majors_list.append((key, 'spot occupied', event[1]))
            elif event[0] == 'Left majors':
                majors_list.append((key, 'spot released', event[1]))
            elif event[0] == 'Got resus':
                resus_list.append((key, 'spot occupied', event[1]))
            elif event[0] == 'Left resus':
                resus_list.append((key, 'spot released', event[1]))
            elif event[0] == 'Got sdec':
                sdec_list.append((key, 'spot occupied', event[1]))
            elif event[0] == 'Left sdec':
                sdec_list.append((key, 'spot released', event[1]))
            elif (event[0] == 'Started discharge') or (event[0] == 'Started admission'):
                corridor_list.append((key, 'spot occupied', event[1]))
            elif (event[0] == 'Finished discharge') or (event[0] == 'Finished admission'):
                corridor_list.append((key, 'spot released', event[1]))
            elif event[0] == 'Requested doctor':
                doctorslist.append((key, 'requested', event[1]))
            elif event[0] == 'Released doctor':
                doctorslist.append((key, 'released', event[1]))
            elif event[0] == 'Requested sdec_doctor':
                sdec_doctorslist.append((key, 'requested', event[1]))
            elif event[0] == 'Released sdec_doctor':
                sdec_doctorslist.append((key, 'released', event[1]))
            elif event[0] == 'Requested rat_doctor':
                rat_doctorslist.append((key, 'requested', event[1]))
            elif event[0] == 'Released rat_doctor':
                rat_doctorslist.append((key, 'released', event[1]))
            elif event[0] == 'Requested nt_doctor':
                nt_doctorslist.append((key, 'requested', event[1]))
            elif event[0] == 'Released nt_doctor':
                nt_doctorslist.append((key, 'released', event[1]))
            elif event[0] == 'Interrupted at':
                doctorslist.append((key, 'interrupted at', event[1], event[2]))
            elif event[0] == 'sdec_Interrupted at':
                sdec_doctorslist.append((key, 'interrupted at', event[1], event[2]))
            elif event[0] == 'rat_Interrupted at':
                rat_doctorslist.append((key, 'interrupted at', event[1], event[2]))
            elif event[0] == 'nt_Interrupted at':
                nt_doctorslist.append((key, 'interrupted at', event[1], event[2]))
    return waiting_room_list, minors_list, majors_list, resus_list, sdec_list, department_list, \
        corridor_list, doctorslist, sdec_doctorslist, rat_doctorslist, nt_doctorslist

# Function to get mean occupancy of room also by acuity


def get_mean_occupancy2(patients_in_room, no_room, acu1, acu2, acu3, acu4, acu5):
    no_acu1_room, no_acu2_room, no_acu3_room, no_acu4_room, no_acu5_room = [0], [0], [0], [0], [0]
    for key, value in patients_in_room.items():
        no_acu1_room.append(len(set(value).intersection(set(acu1))))
        no_acu2_room.append(len(set(value).intersection(set(acu2))))
        no_acu3_room.append(len(set(value).intersection(set(acu3))))
        no_acu4_room.append(len(set(value).intersection(set(acu4))))
        no_acu5_room.append(len(set(value).intersection(set(acu5))))

    number, hours_day, day = [], [], []
    for key, value in no_room.items():
        hour_day = key / 60 % 24
        hours_day.append(int(hour_day))
        day.append(int(key / 60 / 24))
        number.append(value)
    no_in_room = pd.DataFrame()
    final_room = pd.DataFrame()
    no_in_room['Hour of Day'] = hours_day
    no_in_room['Day'] = day
    no_in_room['Minutes Passed'] = no_room.keys()
    no_in_room['Occupancy'] = no_room.values()
    no_in_room['Min minutes'] = no_in_room['Day'] * 60 * 24 + (no_in_room['Hour of Day']) * 60
    no_in_room['Max minutes'] = no_in_room['Day'] * 60 * 24 + (no_in_room['Hour of Day'] + 1) * 60
    data = []
    data.insert(0, {'Hour of Day': 0,
                    'Minutes Passed': 0,
                    'Occupancy': 0,
                    'Day': 0,
                    'Min minutes': 0,
                    'Max minutes': 0,
                    'Occupancy_Acuity1': 0,
                    'Occupancy_Acuity2': 0,
                    'Occupancy_Acuity3': 0,
                    'Occupancy_Acuity4': 0,
                    'Occupancy_Acuity5': 0})

    no_in_room = pd.concat([pd.DataFrame(data), no_in_room], ignore_index=True)

    no_rooms = [no_acu1_room, no_acu2_room, no_acu3_room, no_acu4_room, no_acu5_room]
    for i in range(1, 6):
        no_in_room['Occupancy_Acuity' + str(i)] = no_rooms[i - 1]

    no_in_room['Minutes Passed Diff'] = no_in_room['Minutes Passed'].diff().shift(-1)
    for day in sorted(no_in_room['Day'].unique()):
        no_in_room_subset = no_in_room.loc[no_in_room['Day'] == day]
        for hour in list(range(0, 24)):
            no_in_room_day = no_in_room_subset.loc[no_in_room_subset['Hour of Day'] == hour]
            if no_in_room_day.shape[0] != 0:
                min_idx = min(no_in_room_day.index)
                max_idx = max(no_in_room_day.index)
                data_begin = []
                data_begin.insert(0, {'Hour of Day': hour,
                                      'Minutes Passed': no_in_room_day.iloc[0]['Min minutes'],
                                      'Occupancy': no_in_room.iloc[min_idx - 1]['Occupancy'],
                                      'Day': day,
                                      'Min minutes': no_in_room_day.iloc[0]['Min minutes'],
                                      'Max minutes': no_in_room_day.iloc[0]['Max minutes'],
                                      'Occupancy_Acuity1': no_in_room.iloc[min_idx - 1]['Occupancy_Acuity1'],
                                      'Occupancy_Acuity2': no_in_room.iloc[min_idx - 1]['Occupancy_Acuity2'],
                                      'Occupancy_Acuity3': no_in_room.iloc[min_idx - 1]['Occupancy_Acuity3'],
                                      'Occupancy_Acuity4': no_in_room.iloc[min_idx - 1]['Occupancy_Acuity4'],
                                      'Occupancy_Acuity5': no_in_room.iloc[min_idx - 1]['Occupancy_Acuity5'],
                                      'Minutes Passed Diff': no_in_room_day.iloc[0]['Minutes Passed'] -
                                      no_in_room_day.iloc[0]['Min minutes']})
                no_in_room_day.at[max_idx, 'Minutes Passed Diff'] = \
                    no_in_room_day.iloc[no_in_room_day.shape[0] - 1]['Max minutes'] - \
                    no_in_room_day.iloc[no_in_room_day.shape[0] - 1]['Minutes Passed']
                no_in_room_day = pd.concat([pd.DataFrame(data_begin), no_in_room_day], ignore_index=True)
                if final_room.shape[0] == 0:
                    final_room = no_in_room_day
                else:
                    final_room = pd.concat([final_room, no_in_room_day])
            else:
                data_begin = []
                data_begin.insert(0, {'Hour of Day': hour,
                                      'Minutes Passed': day * 60 * 24 + hour * 60,
                                      'Occupancy': no_in_room.iloc[max_idx]['Occupancy'],
                                      'Day': day,
                                      'Min minutes': day * 60 * 24 + hour * 60,
                                      'Max minutes': day * 60 * 24 + (hour + 1) * 60,
                                      'Occupancy_Acuity1': no_in_room.iloc[max_idx]['Occupancy_Acuity1'],
                                      'Occupancy_Acuity2': no_in_room.iloc[max_idx]['Occupancy_Acuity2'],
                                      'Occupancy_Acuity3': no_in_room.iloc[max_idx]['Occupancy_Acuity3'],
                                      'Occupancy_Acuity4': no_in_room.iloc[max_idx]['Occupancy_Acuity4'],
                                      'Occupancy_Acuity5': no_in_room.iloc[max_idx]['Occupancy_Acuity5'],
                                      'Minutes Passed Diff': 60})
                if final_room.shape[0] == 0:
                    final_room = pd.DataFrame(data_begin)
                else:
                    final_room = pd.concat([final_room, pd.DataFrame(data_begin)])
    final_room = final_room.loc[final_room.Day != 0]
    mean_occupancy, mean_occupancy_ac1, mean_occupancy_ac2, mean_occupancy_ac3, mean_occupancy_ac4, \
        mean_occupancy_ac5 = {}, {}, {}, {}, {}, {}
    for hour in final_room['Hour of Day'].unique():
        final_room_hour = final_room.loc[final_room['Hour of Day'] == hour]

        final_room_hour_copy = final_room_hour.copy()
        final_room_hour_copy['Mean Occupancy'] = \
            final_room_hour['Occupancy'] * final_room_hour['Minutes Passed Diff']
        mean_occupancy[hour] = final_room_hour_copy['Mean Occupancy'].sum() / final_room_hour[
            'Minutes Passed Diff'].sum()
        mean_occupancy_ac1[hour] = (final_room_hour['Occupancy_Acuity1'] * final_room_hour[
            'Minutes Passed Diff']).sum() / final_room_hour['Minutes Passed Diff'].sum()
        mean_occupancy_ac2[hour] = (final_room_hour['Occupancy_Acuity2'] * final_room_hour[
            'Minutes Passed Diff']).sum() / final_room_hour['Minutes Passed Diff'].sum()
        mean_occupancy_ac3[hour] = (final_room_hour['Occupancy_Acuity3'] * final_room_hour[
            'Minutes Passed Diff']).sum() / final_room_hour['Minutes Passed Diff'].sum()
        mean_occupancy_ac4[hour] = (final_room_hour['Occupancy_Acuity4'] * final_room_hour[
            'Minutes Passed Diff']).sum() / final_room_hour['Minutes Passed Diff'].sum()
        mean_occupancy_ac5[hour] = (final_room_hour['Occupancy_Acuity5'] * final_room_hour[
            'Minutes Passed Diff']).sum() / final_room_hour['Minutes Passed Diff'].sum()
        
    #this checks that there are not empty mean_occupancy dictionaries
    #if there are (e.g. because there is no sdec) it returns a dictionary with all 0s and keys 0-23
    for dict in [mean_occupancy, mean_occupancy_ac1, mean_occupancy_ac2, mean_occupancy_ac3, mean_occupancy_ac4, mean_occupancy_ac5]:
        if not dict:
            dict.update({key: 0 for key in range(24)})
            
    return final_room, mean_occupancy, mean_occupancy_ac1, mean_occupancy_ac2, mean_occupancy_ac3,\
        mean_occupancy_ac4, mean_occupancy_ac5

# Function  to return those patients with doctors


def get_patients_with_doctors(num_doctors, doctorslist):
    patients_with_doctors = {}
    for i in sorted(doctorslist, key=lambda x: x[2]):
        if len(patients_with_doctors.keys()) == 0:
            if i[1] == 'requested':
                patients_with_doctors[i[2]] = [i[0]]
        else:
            if i[1] == 'requested':
                patients_with_doctors[i[2]] = list(patients_with_doctors.values())[-1].copy()
                patients_with_doctors[i[2]].append(i[0])
            elif i[1] == 'released' or i[1] == 'interrupted at':
                patients_with_doctors[i[2]] = list(patients_with_doctors.values())[-1].copy()
                try:
                    patients_with_doctors[i[2]].remove(i[0])
                except:
                    if i[1] == 'interrupted at':
                        if i[2] == 0:
                            continue
    # Check that there isn't any point in time in which we have more than 3 doctors being used
    for key, value in patients_with_doctors.items():
        if len(value) > num_doctors:
            print('Take care, at ', key, 'there are more than ', num_doctors, 'doctors')
    return patients_with_doctors

# Function to get interruptions information


def get_interruptions_df(events, num_doctors, doctorslist, time_until_a_or_d, arrival_time,
                         time_category, doctor_name):

    patients_with_doctors = get_patients_with_doctors(num_doctors, doctorslist)
    time_until_doc = {}
    for patient in time_until_a_or_d['PatientID']:
        time_doc = []
        for key, value in patients_with_doctors.items():
            if patient in value:
                time_doc.append(key)
        if len(time_doc) > 0:
            time_until_doc[patient] = time_doc[0] - arrival_time[patient]
    time_until_first_doc = pd.DataFrame()
    time_until_first_doc['PatientID'] = time_until_doc.keys()
    time_until_first_doc['Time (min)'] = time_until_doc.values()
    acuities = []
    for patient in time_until_doc.keys():
        acuities.append(time_category[patient])
    time_until_first_doc['Acuity'] = acuities
    time_until_first_doc_mean = pd.DataFrame(
        time_until_first_doc.groupby('Acuity')['Time (min)'].mean()).reset_index()
    time_until_first_doc_mean['Std'] = pd.DataFrame(time_until_first_doc.groupby('Acuity')['Time (min)'].std())[
        'Time (min)'].values

    # No of interruptions
    no_interruptions = {}
    for patient in time_until_a_or_d['PatientID']:
        events_patient = events[patient]
        day = arrival_time[patient] / 60 // 24
        acuity = time_category[patient]
        for event in events_patient:
            interruption_string = doctor_name + 'Interrupted at'
            if (event[0] == interruption_string) and event[2] != 0:
                if (acuity, day) in no_interruptions.keys():
                    no_interruptions[acuity, day] += 1
                else:
                    no_interruptions[acuity, day] = 1
    no_interruptions_df = pd.DataFrame()
    no_interruptions_df['Acuity'] = [key[0] for key in list(no_interruptions.keys())]
    no_interruptions_df['Day'] = [key[1] for key in list(no_interruptions.keys())]
    no_interruptions_df['Interruptions'] = no_interruptions.values()
    no_interruptions_df = pd.DataFrame(no_interruptions_df.groupby('Acuity')['Interruptions'].mean()).reset_index()

    return no_interruptions_df, time_until_first_doc_mean
