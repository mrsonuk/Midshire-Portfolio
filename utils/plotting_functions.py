# Imports
import seaborn as sns
import numpy as np
import matplotlib.pyplot as plt
import matplotlib

# Main function to create plots


def plotting_functions(arrival_time, left, time_category, time_until_admission, time_until_discharge,
                       waiting_time, events, num_doctors, num_sdec_doctors, num_rat_doctors, num_nt_doctors):

    # Imports
    from utils.plotting_helper_functions import get_arrivals_by_hour, get_admissions_and_discharges_by_hour, \
        get_time_in_department_by_hour, get_time_in_department_before_and_after_crtp, get_number_left, \
        get_rooms_list, get_mean_occupancy2, get_interruptions_df
    from utils.analysis_functions import get_no_room, get_patients_in_room, get_mean_occupancy

    # Figure colours
    colors = sns.color_palette('Paired')
    light_red = colors[4]
    dark_red = colors[5]
    light_orange = colors[6]
    dark_orange = colors[7]
    light_green = colors[2]
    dark_green = colors[3]
    light_blue = colors[0]
    dark_blue = colors[1]
    light_yellow = colors[10]
    dark_yellow = sns.dark_palette("Yellow")[4]

    # Get set of patients with different acuities
    acu1 = [patient for patient in left.keys() if time_category[patient] == 'acuity 1']
    acu2 = [patient for patient in left.keys() if time_category[patient] == 'acuity 2']
    acu3 = [patient for patient in left.keys() if time_category[patient] == 'acuity 3']
    acu4 = [patient for patient in left.keys() if time_category[patient] == 'acuity 4']
    acu5 = [patient for patient in left.keys() if time_category[patient] == 'acuity 5']

    # Get arrivals by hour
    arrivals_df, non_day1, arrivals_df_1, arrivals_df_2, arrivals_df_3, arrivals_df_4, arrivals_df_5, bar_width, \
        max_value = get_arrivals_by_hour(arrival_time, time_category)

    # Figure 1 plotting
    sns.set(rc={"figure.figsize": (18, 7)}, font_scale=1.8)
    fig, ax = plt.subplots(figsize=(18, 7))
    plt.bar(x=arrivals_df_1['Arrival Time'], height=arrivals_df_1['Count'], color=dark_red, width=bar_width,
            bottom=arrivals_df_2['Count'].values + arrivals_df_3['Count'].values + arrivals_df_4['Count'].values +
            arrivals_df_5['Count'].values)
    plt.bar(x=arrivals_df_2['Arrival Time'], height=arrivals_df_2['Count'], color=dark_orange, width=bar_width,
            bottom=arrivals_df_3['Count'].values + arrivals_df_4['Count'].values + arrivals_df_5['Count'].values)
    plt.bar(x=arrivals_df_3['Arrival Time'], height=arrivals_df_3['Count'], color='yellow', width=bar_width,
            bottom=arrivals_df_4['Count'].values + arrivals_df_5['Count'].values)
    plt.bar(x=arrivals_df_4['Arrival Time'], height=arrivals_df_4['Count'], alpha=0.7, color=dark_green,
            width=bar_width, bottom=arrivals_df_5['Count'].values)
    plt.bar(x=arrivals_df_5['Arrival Time'], height=arrivals_df_5['Count'], color=dark_blue, width=bar_width)
    ax.set_xlabel('Hour of Arrival')
    ax.set_ylabel('Count')
    summary_top = 'Daily average number of patients: ' + str(round(arrivals_df.Count.sum()))
    plt.text(-0.5, max_value * 1.05, summary_top, fontsize=18)
    plt.ylim(0, 1.15 * max_value)
    plt.title('Distribution of incoming patients throughout the day')
    plt.savefig('NumPatients_PerDay.png')

    # Get admissions and discharges by hour
    min_value, max_value, admission, discharge, min_value, time_until_a_or_d, time_until_a_copy, time_until_d_copy, \
        adms_4hr, discharge_4hr, adms_12hr, discharge_12hr, adm_1, adm_2, adm_3, adm_4, adm_5, disc_1, disc_2, disc_3, \
        disc_4, disc_5 = get_admissions_and_discharges_by_hour(time_until_admission, time_until_discharge, non_day1,
                                                               arrival_time, time_category)

    # Figure 2 plotting
    sns.set(rc={"figure.figsize": (18, 7)}, font_scale=1.8)
    bar_width = 10
    fig, ax = plt.subplots(figsize=(18, 7))
    plt.bar(x=disc_5['Time Until Discharge (min)'], height=disc_5['Perc Discharged'], alpha=0.7, color=light_blue,
            width=bar_width)
    plt.bar(x=disc_4['Time Until Discharge (min)'], height=disc_4['Perc Discharged'], alpha=0.7, color=light_green,
            width=bar_width, bottom=disc_5['Perc Discharged'].values)
    plt.bar(x=disc_3['Time Until Discharge (min)'], height=disc_3['Perc Discharged'], alpha=0.7, color=light_yellow,
            width=bar_width, bottom=disc_4['Perc Discharged'].values + disc_5['Perc Discharged'].values)
    plt.bar(x=disc_2['Time Until Discharge (min)'], height=disc_2['Perc Discharged'], alpha=0.7, color=light_orange,
            width=bar_width, bottom=disc_3['Perc Discharged'].values + disc_4['Perc Discharged'].values + disc_5[
            'Perc Discharged'].values)
    plt.bar(x=disc_1['Time Until Discharge (min)'], height=disc_1['Perc Discharged'], alpha=0.7, color=light_red,
            width=bar_width, bottom=disc_2['Perc Discharged'].values + disc_3['Perc Discharged'].values + disc_4[
            'Perc Discharged'].values + disc_5['Perc Discharged'].values)
    plt.bar(x=adm_1['Time Until Admission (min)'], height=adm_1['Perc Admitted'], color=dark_red, width=bar_width,
            bottom=adm_2['Perc Admitted'].values + adm_3['Perc Admitted'].values + adm_4['Perc Admitted'].values +
            adm_5['Perc Admitted'].values)
    plt.bar(x=adm_2['Time Until Admission (min)'], height=adm_2['Perc Admitted'], color=dark_orange, width=bar_width,
            bottom=adm_3['Perc Admitted'].values + adm_4['Perc Admitted'].values + adm_5['Perc Admitted'].values)
    plt.bar(x=adm_3['Time Until Admission (min)'], height=adm_3['Perc Admitted'], color='yellow', width=bar_width,
            bottom=adm_4['Perc Admitted'].values + adm_5['Perc Admitted'].values)
    plt.bar(x=adm_4['Time Until Admission (min)'], height=adm_4['Perc Admitted'], alpha=0.7, color=dark_green,
            width=bar_width, bottom=adm_5['Perc Admitted'].values)
    plt.bar(x=adm_5['Time Until Admission (min)'], height=adm_5['Perc Admitted'], color=dark_blue, width=bar_width)
    ax.set_xlabel('')
    index = admission['Time Until Admission (min)'].unique()
    ax.set_xticks(index[::6],
                  list([str(i // 60) + 'Hr' for i in discharge['Time Until Discharge (min)'].unique()][::6])[
                  :-1] + list(['12+Hr']))
    ax.set_ylabel('%')
    ax.set_ylim(min_value - 3, max_value + 5)  # This is how we would set y-axis limits
    ax.set_xlim(-5, 725)
    summary_top = 'Attends: ' + str(time_until_a_or_d.shape[0]) + ';    Adms: ' + str(
        time_until_a_copy.shape[0]) + ';    NonAdms: ' + str(time_until_d_copy.shape[0])
    summary_bottom = '% Patients left by: 4hrs = ' + str(
        round(adms_4hr + abs(discharge_4hr))) + '%;    % Adms at: 12+hrs = ' + str(
        round(adms_12hr + abs(discharge_12hr), 1)) + '%;'  # % Patients left by: 4hrs A1 = ' + str(
    # round(adms_4hr_a1 + abs(discharge_4hr_a1))) + '%;    % Adms at: 12+hrs A1 = ' + str(
    # round(adms_12hr_a1 + abs(discharge_12hr_a1), 2)) + '%; % Patients left by: 4hrs A2 = ' + str(
    # round(adms_4hr_a2 + abs(discharge_4hr_a2))) + '%;    % Adms at: 12+hrs A2 = ' + str(
    # round(adms_12hr_a2 + abs(discharge_12hr_a2), 2)) + '%; % Patients left by: 4hrs A3 = ' + str(
    # round(adms_4hr_a3 + abs(discharge_4hr_a3))) + '%;    % Adms at: 12+hrs A3 = ' + str(
    # round(adms_12hr_a3 + abs(discharge_12hr_a3), 2)) + '%; % Patients left by: 4hrs A4 = ' + str(
    # round(adms_4hr_a4 + abs(discharge_4hr_a4))) + '%;    % Adms at: 12+hrs A4 = ' + str(
    # round(adms_12hr_a4 + abs(discharge_12hr_a4), 2)) + '%; % Patients left by: 4hrs A5 = ' + str(
    # round(adms_4hr_a5 + abs(discharge_4hr_a5))) + '%;    % Adms at: 12+hrs A5 = ' + str(
    # round(adms_12hr_a5 + abs(discharge_12hr_a5), 2)) + '%'
    plt.text(5, max_value + 4, summary_top, fontsize=18)
    plt.text(5, min_value - 2.5, summary_bottom, fontsize=18, wrap=True)
    plt.title('Flow chart - Admissions (darker) vs Discharges (lighter)')
    plt.savefig('TimeInDept_Acuity.png')

    # Printing 4 hr discharge time for Monte-Carlo
    print("4 hr discharge time:", str(round(adms_4hr + abs(discharge_4hr))))

    # Get time in department by hour
    time_in_dept, time_in_dept_1, time_in_dept_2, time_in_dept_3, time_in_dept_4, time_in_dept_5, mean_time_overall, \
        std_time_overall, longest_time = get_time_in_department_by_hour(arrival_time, time_until_admission,
                                                                        time_until_discharge, time_until_a_or_d,
                                                                        waiting_time, time_category)

    # Figure 3 plotting
    sns.set(rc={"figure.figsize": (18, 7)}, font_scale=1.8)
    bar_width = 0.7
    fig, ax = plt.subplots(figsize=(18, 7))
    plt.bar(x=time_in_dept_1['Arrival Time'], height=time_in_dept_1['Time in Dept (min)'], color=dark_red,
            width=bar_width,
            bottom=time_in_dept_2['Time in Dept (min)'].values + time_in_dept_3['Time in Dept (min)'].values +
            time_in_dept_4['Time in Dept (min)'].values + time_in_dept_5['Time in Dept (min)'].values)
    plt.bar(x=time_in_dept_2['Arrival Time'], height=time_in_dept_2['Time in Dept (min)'], color=dark_orange,
            width=bar_width,
            bottom=time_in_dept_3['Time in Dept (min)'].values + time_in_dept_4['Time in Dept (min)'].values +
            time_in_dept_5['Time in Dept (min)'].values)
    plt.bar(x=time_in_dept_3['Arrival Time'], height=time_in_dept_3['Time in Dept (min)'], color='yellow',
            width=bar_width,
            bottom=time_in_dept_4['Time in Dept (min)'].values + time_in_dept_5['Time in Dept (min)'].values)
    plt.bar(x=time_in_dept_4['Arrival Time'], height=time_in_dept_4['Time in Dept (min)'], alpha=0.7, color=dark_green,
            width=bar_width, bottom=time_in_dept_5['Time in Dept (min)'].values)
    plt.bar(x=time_in_dept_5['Arrival Time'], height=time_in_dept_5['Time in Dept (min)'], color=dark_blue,
            width=bar_width)
    ax.set_xlabel('Hour of Arrival')
    ax.set_ylabel('Time in department (min)')
    plt.title('Mean time in the department (min)')
    plt.savefig('MeanTime_Stacked.png')

    # Get time in department before and after crtp
    max_value, before_crtp, after_crtp, time_in_dept_1, time_in_dept_2, time_in_dept_3, time_in_dept_4, time_in_dept_5\
        = get_time_in_department_before_and_after_crtp(time_in_dept)

    # Figure 4 plotting
    sns.set(rc={"figure.figsize": (18, 10)}, font_scale=1.8)
    matplotlib.rcParams['legend.fontsize'] = 15
    ax1 = plt.subplot(511)
    ax1.bar(x=time_in_dept_1['Arrival Time'].values, height=after_crtp, color=dark_red, width=bar_width,
            bottom=before_crtp, label='After CRTP')
    ax1.bar(x=time_in_dept_1['Arrival Time'].values, height=before_crtp, color=light_red, width=bar_width,
            label='Before CRTP')
    plt.tick_params('x', labelbottom=False)
    ax1.set_ylim(0, max_value * 1.1)
    ax1.set_ylabel('')
    ax1.set_xlabel('')

    ax2 = plt.subplot(512, sharex=ax1, sharey=ax1)
    before_crtp = time_in_dept_2['Waiting Time (before A/D) (min)'].values
    after_crtp = time_in_dept_2['Time waiting for A/D (min)'].values
    ax2.bar(x=time_in_dept_2['Arrival Time'].values, height=after_crtp, color=dark_orange, width=bar_width,
            bottom=before_crtp, label='After CRTP')
    ax2.bar(x=time_in_dept_2['Arrival Time'].values, height=before_crtp, color=light_orange, width=bar_width,
            label='Before CRTP')
    plt.tick_params('x', labelbottom=False)
    ax2.set_ylim(0, max_value * 1.1)
    ax2.set_ylabel('')
    ax2.set_xlabel('')

    ax3 = plt.subplot(513, sharex=ax1, sharey=ax1)
    before_crtp = time_in_dept_3['Waiting Time (before A/D) (min)'].values
    after_crtp = time_in_dept_3['Time waiting for A/D (min)'].values
    ax3.bar(x=time_in_dept_3['Arrival Time'].values, height=after_crtp, color=dark_yellow, width=bar_width,
            bottom=before_crtp, label='After CRTP')
    ax3.bar(x=time_in_dept_3['Arrival Time'].values, height=before_crtp, color=light_yellow, width=bar_width,
            label='Before CRTP')
    plt.tick_params('x', labelbottom=False)
    ax3.set_ylim(0, max_value * 1.1)
    ax3.set_xlabel('')

    ax4 = plt.subplot(514, sharex=ax1, sharey=ax1)
    before_crtp = time_in_dept_4['Waiting Time (before A/D) (min)'].values
    after_crtp = time_in_dept_4['Time waiting for A/D (min)'].values
    ax4.bar(x=time_in_dept_4['Arrival Time'].values, height=after_crtp, color=dark_green, alpha=0.7, width=bar_width,
            bottom=before_crtp, label='After CRTP')
    ax4.bar(x=time_in_dept_4['Arrival Time'].values, height=before_crtp, color=light_green, width=bar_width,
            label='Before CRTP')
    plt.tick_params('x', labelbottom=False)
    ax4.set_ylabel('')
    ax4.set_xlabel('')

    ax5 = plt.subplot(515, sharex=ax1, sharey=ax1)
    before_crtp = time_in_dept_5['Waiting Time (before A/D) (min)'].values
    after_crtp = time_in_dept_5['Time waiting for A/D (min)'].values
    ax5.bar(x=time_in_dept_5['Arrival Time'].values, height=after_crtp, color=dark_blue, width=bar_width,
            bottom=before_crtp, label='After CRTP')
    ax5.bar(x=time_in_dept_5['Arrival Time'].values, height=before_crtp, color=light_blue, width=bar_width,
            label='Before CRTP')
    ax5.set_ylim(0, max_value * 1.2)
    ax5.set_ylabel('')

    ax3.set_ylabel('Time in department (min)')
    ax5.set_xlabel('Hour of Arrival')
    for i in [ax1, ax2, ax3, ax4, ax5]:
        i.legend(loc='upper right')

    plt.savefig('MeanTime_MultipleBarCharts.png')

    # Get number of people who have left
    no_left = get_number_left(non_day1, left, time_category, arrival_time)

    # Getting all the data form the events dictionary
    waiting_room_list, minors_list, majors_list, resus_list, sdec_list, department_list, corridor_list,\
        doctorslist, sdec_doctorslist, rat_doctorslist, nt_doctorslist = get_rooms_list(events)

    # Get patients in different rooms
    patients_in_waiting_room = get_patients_in_room(waiting_room_list)
    patients_in_minors = get_patients_in_room(minors_list)
    patients_in_majors = get_patients_in_room(majors_list)
    patients_in_resus = get_patients_in_room(resus_list)
    patients_in_sdec = get_patients_in_room(sdec_list)
    patients_in_corridor = get_patients_in_room(corridor_list)

    # Get numbers in different rooms
    no_waiting_room = get_no_room(patients_in_waiting_room)
    no_minors = get_no_room(patients_in_minors)
    no_majors = get_no_room(patients_in_majors)
    no_resus = get_no_room(patients_in_resus)
    no_sdec = get_no_room(patients_in_sdec)
    no_corridor = get_no_room(patients_in_corridor)

    # Get occupancies of different rooms

    # Waiting room
    final_wr, mean_wr_occupancy = get_mean_occupancy(no_waiting_room)

    # Minors
    final_minors, mean_minors_occupancy = get_mean_occupancy(no_minors)

    # Majors
    final_majors, mean_majors_occupancy = get_mean_occupancy(no_majors)

    # Resus
    final_resus, mean_resus_occupancy = get_mean_occupancy(no_resus)

    # SDEC
    final_sdec, mean_sdec_occupancy = get_mean_occupancy(no_sdec)

    # Corridor
    final_corridor, mean_corridor_occupancy = get_mean_occupancy(no_corridor)
    #creating mean occupancy sdec if it is empty (if there is no sdec in the model)
    if not mean_sdec_occupancy:
        mean_sdec_occupancy = {key: 0 for key in range(24)}
    # Figure 5 plotting
    xgfs_tarnish6 = sns.color_palette("rocket_r")
    bar_width = 0.7
    fig, ax = plt.subplots(figsize=(18, 7))
    plt.bar(x=mean_resus_occupancy.keys(), height=np.array(list(mean_resus_occupancy.values())), color=xgfs_tarnish6[0],
            width=bar_width, bottom=np.array(list(mean_corridor_occupancy.values())) + np.array(
            list(mean_majors_occupancy.values())) + np.array(list(mean_minors_occupancy.values())) + np.array(
            list(mean_wr_occupancy.values())), label='Resus')
    
    if not all(val == 0 for val in mean_sdec_occupancy.values()):
        plt.bar(x=mean_sdec_occupancy.keys(), height=np.array(list(mean_sdec_occupancy.values())), color=dark_blue,
            width=bar_width, bottom=np.array(list(mean_corridor_occupancy.values())) + np.array(
            list(mean_majors_occupancy.values())) + np.array(list(mean_minors_occupancy.values())) + np.array(
            list(mean_wr_occupancy.values())), label='Sdec')
 

    
    plt.bar(x=mean_majors_occupancy.keys(), height=np.array(list(mean_majors_occupancy.values())),
            color=(244 / 255, 136 / 255, 102 / 255), width=bar_width,
            bottom=np.array(list(mean_corridor_occupancy.values())) + np.array(
                list(mean_minors_occupancy.values())) + np.array(list(mean_wr_occupancy.values())), label='Majors')
    plt.bar(x=mean_minors_occupancy.keys(), height=np.array(list(mean_minors_occupancy.values())),
            color=(245 / 255, 61 / 255, 76 / 255), width=bar_width,
            bottom=np.array(list(mean_corridor_occupancy.values())) + np.array(list(mean_wr_occupancy.values())),
            label='Minors')
    plt.bar(x=mean_wr_occupancy.keys(), height=np.array(list(mean_wr_occupancy.values())), color=xgfs_tarnish6[3],
            width=bar_width, bottom=np.array(list(mean_corridor_occupancy.values())), label='Waiting Room')
    plt.bar(x=mean_corridor_occupancy.keys(), height=np.array(list(mean_corridor_occupancy.values())),
            color=xgfs_tarnish6[4], width=bar_width, label='Corridor')
    ax.set_xlabel('Hour of Arrival')
    ax.set_xlabel('Hour of Arrival')
    ax.set_ylabel('Number of patients')
    ax.legend()
    plt.title('Distribution of patients in the ED - split by treatment area')
    plt.savefig('MeanOccupancy_per_room.png')

    # Figure 6 calculations
    # Waiting room
    final_wr, mean_wr_occupancy, mean_wr_occupancy_ac1, mean_wr_occupancy_ac2, mean_wr_occupancy_ac3, \
        mean_wr_occupancy_ac4, mean_wr_occupancy_ac5 = get_mean_occupancy2(
            patients_in_waiting_room, no_waiting_room, acu1, acu2, acu3, acu4, acu5)

    # Minors
    final_minors, mean_minors_occupancy, mean_minors_occupancy_ac1, mean_minors_occupancy_ac2, \
        mean_minors_occupancy_ac3, mean_minors_occupancy_ac4, mean_minors_occupancy_ac5 = get_mean_occupancy2(
            patients_in_minors, no_minors, acu1, acu2, acu3, acu4, acu5)

    # Majors
    final_majors, mean_majors_occupancy, mean_majors_occupancy_ac1, mean_majors_occupancy_ac2, \
        mean_majors_occupancy_ac3, mean_majors_occupancy_ac4, mean_majors_occupancy_ac5 = get_mean_occupancy2(
            patients_in_majors, no_majors, acu1, acu2, acu3, acu4, acu5)

    # Resus
    final_resus, mean_resus_occupancy, mean_resus_occupancy_ac1, mean_resus_occupancy_ac2, \
        mean_resus_occupancy_ac3, mean_resus_occupancy_ac4, mean_resus_occupancy_ac5 = get_mean_occupancy2(
            patients_in_resus, no_resus, acu1, acu2, acu3, acu4, acu5)

    # Sdec
    
    final_sdec, mean_sdec_occupancy, mean_sdec_occupancy_ac1, mean_sdec_occupancy_ac2,\
        mean_sdec_occupancy_ac3, mean_sdec_occupancy_ac4, mean_sdec_occupancy_ac5 = get_mean_occupancy2(
            patients_in_sdec, no_sdec, acu1, acu2, acu3, acu4, acu5)

    # Corridor
    final_corridor, mean_corridor_occupancy, mean_corridor_occupancy_ac1, mean_corridor_occupancy_ac2,\
        mean_corridor_occupancy_ac3, mean_corridor_occupancy_ac4, mean_corridor_occupancy_ac5 = get_mean_occupancy2(
            patients_in_corridor, no_corridor, acu1, acu2, acu3, acu4, acu5)

    # Create arrays for helping figure 6 plotting
    ac1_occ = np.array(list(mean_wr_occupancy_ac1.values())) + np.array(
        list(mean_minors_occupancy_ac1.values())) + np.array(list(mean_majors_occupancy_ac1.values())) + np.array(
        list(mean_resus_occupancy_ac1.values())) + np.array(list(mean_sdec_occupancy_ac1.values())) + \
        np.array(list(mean_corridor_occupancy_ac1.values()))
    ac2_occ = np.array(list(mean_wr_occupancy_ac2.values())) + np.array(
        list(mean_minors_occupancy_ac2.values())) + np.array(list(mean_majors_occupancy_ac2.values())) + np.array(
        list(mean_resus_occupancy_ac2.values())) + np.array(list(mean_sdec_occupancy_ac2.values())) + \
        np.array(list(mean_corridor_occupancy_ac2.values()))
    ac3_occ = np.array(list(mean_wr_occupancy_ac3.values())) + np.array(
        list(mean_minors_occupancy_ac3.values())) + np.array(list(mean_majors_occupancy_ac3.values())) + np.array(
        list(mean_resus_occupancy_ac3.values())) + np.array(list(mean_sdec_occupancy_ac3.values())) +\
        np.array(list(mean_corridor_occupancy_ac3.values()))
    ac4_occ = np.array(list(mean_wr_occupancy_ac4.values())) + np.array(
        list(mean_minors_occupancy_ac4.values())) + np.array(list(mean_majors_occupancy_ac4.values())) + np.array(
        list(mean_resus_occupancy_ac4.values())) + np.array(list(mean_sdec_occupancy_ac4.values())) +\
        np.array(list(mean_corridor_occupancy_ac4.values()))
    ac5_occ = np.array(list(mean_wr_occupancy_ac5.values())) + np.array(
        list(mean_minors_occupancy_ac5.values())) + np.array(list(mean_majors_occupancy_ac5.values())) + np.array(
        list(mean_resus_occupancy_ac5.values())) + np.array(list(mean_sdec_occupancy_ac5.values())) +\
        np.array(list(mean_corridor_occupancy_ac5.values()))

    # Figure 6 plotting
    sns.set(rc={"figure.figsize": (18, 7)}, font_scale=1.8)
    bar_width = 0.7
    fig, ax = plt.subplots(figsize=(18, 7))
    plt.bar(x=mean_resus_occupancy.keys(), height=ac1_occ, color=dark_red, width=bar_width,
            bottom=ac2_occ + ac3_occ + ac4_occ + ac5_occ, label='Acuity 1')
    plt.bar(x=mean_majors_occupancy.keys(), height=ac2_occ, color=dark_orange, width=bar_width,
            bottom=ac3_occ + ac4_occ + ac5_occ, label='Acuity 2')
    plt.bar(x=mean_minors_occupancy.keys(), height=ac3_occ, color='yellow', width=bar_width, bottom=ac4_occ + ac5_occ,
            label='Acuity 3')
    plt.bar(x=mean_wr_occupancy.keys(), height=ac4_occ, alpha=0.7, color=dark_green, width=bar_width, bottom=ac5_occ,
            label='Acuity 4')
    plt.bar(x=mean_corridor_occupancy.keys(), height=ac5_occ, color=dark_blue, width=bar_width, label='Acuity 5')

    ax.set_xlabel('Hour of Arrival')
    ax.set_ylabel('Number of patients')
    plt.title('Distribution of patients in the ED - split by acuity')
    ax.legend()
    plt.savefig('MeanOccupancy_per_acuity.png')


    # Call function for all types of doctor and get number of interruptions and mean time until first doc

    no_interruptions_df, time_until_first_doc_mean = get_interruptions_df(events, num_doctors, doctorslist,
                                                                          time_until_a_or_d, arrival_time,
                                                                          time_category, '')
    no_sdec_interruptions_df, time_until_first_sdec_doc_mean = get_interruptions_df(events, num_sdec_doctors,
                                                                                    sdec_doctorslist, time_until_a_or_d,
                                                                                    arrival_time, time_category,
                                                                                    'sdec_')
    no_rat_interruptions_df, time_until_first_rat_doc_mean = get_interruptions_df(events, num_rat_doctors,
                                                                                  rat_doctorslist, time_until_a_or_d,
                                                                                  arrival_time, time_category, 'rat_')
    no_nt_interruptions_df, time_until_first_nt_doc_mean = get_interruptions_df(events, num_nt_doctors,
                                                                                nt_doctorslist, time_until_a_or_d,
                                                                                arrival_time, time_category, 'nt_')

    # Return values
    return mean_time_overall, std_time_overall, longest_time, time_until_first_doc_mean,\
        time_until_first_sdec_doc_mean,\
        time_until_first_rat_doc_mean, time_until_first_nt_doc_mean, no_left, no_interruptions_df,\
        no_sdec_interruptions_df, no_rat_interruptions_df, no_nt_interruptions_df
