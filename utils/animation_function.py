# -*- coding: utf-8 -*-

# Import analysis functions
from utils.analysis_functions import get_no_room, get_patients_in_room

# Generate json function


def generate_json(events):

    # Function to return "CAPACITY" event
    def create_capacity_json(room_size):
        json = {}
        json["time_events"] = []
        for time in room_size:
            events = {}
            events["time"] = round(time, 1)
            events["size"] = room_size[time]
            events["event"] = "CAPACITY"
            json["time_events"].append(events)
        return json
    
    # Function to get room lists
    def get_rooms_list(events):
        waiting_room_list, minors_list, majors_list, resus_list, sdec_list, department_list, corridor_list, \
            doctorslist, sdec_doctorslist, rat_doctorslist, nt_doctorslist = [], [], [], [], [], [], [], [], [], [], []
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
        return waiting_room_list, minors_list, majors_list, resus_list, sdec_list, department_list, corridor_list, \
            doctorslist, sdec_doctorslist, rat_doctorslist, nt_doctorslist

    # Get lists
    waiting_room_list, minors_list, majors_list, resus_list, sdec_list, department_list, corridor_list, doctorslist, \
        sdec_doctorslist, rat_doctorslist, nt_doctorslist = get_rooms_list(events)

    # Get patients in rooms
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

    # Create room jsons
    corridor_room_json = create_capacity_json(no_corridor)
    waiting_room_json = create_capacity_json(no_waiting_room)
    majors_room_json = create_capacity_json(no_majors)
    minors_room_json = create_capacity_json(no_minors)
    resus_room_json = create_capacity_json(no_resus)
    sdec_room_json = create_capacity_json(no_sdec)

    # Return values
    return corridor_room_json, waiting_room_json, majors_room_json, minors_room_json, resus_room_json, sdec_room_json
