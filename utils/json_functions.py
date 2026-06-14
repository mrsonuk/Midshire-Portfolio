# Imports
import json
import numpy as np

# Function for getting event indices


def event_indices(event_title, event_names):
    return [idx for idx, i in enumerate(event_names) if i == event_title]

# Function for parsing event information


def parse_event_information(person_events):
    # Display information in an array for better processing
    information = []  # [order, event name, event space, event start time, event duration]
    event_names = [name[0] for name in person_events]

    # Waiting Room
    WR_start_indices = event_indices('Got waiting room', event_names)
    WR_end_indices = event_indices('Left waiting room', event_names)
    for i in range(len(WR_end_indices)):
        eventName = "WAITING_ROOM"
        eventSpot = person_events[WR_start_indices[i]][2] + 1
        eventStartTime = round(person_events[WR_start_indices[i]][1], 2)
        eventDuration = round(person_events[WR_end_indices[i]][1] - person_events[WR_start_indices[i]][1], 2)
        information.append([WR_end_indices[i], eventName, eventSpot, eventStartTime, eventDuration])
    if len(WR_start_indices) != len(WR_end_indices):
        eventName = "WAITING_ROOM"
        eventSpot = person_events[WR_start_indices[-1]][2] + 1
        eventStartTime = round(person_events[WR_start_indices[-1]][1], 2)
        eventDuration = 10000
        information.append([WR_start_indices[-1], eventName, eventSpot, eventStartTime, eventDuration])

    # Treatment Room
    TR_start_indices = event_indices('Got minors', event_names)
    TR_end_indices = event_indices('Left minors', event_names)

    for i in range(len(TR_end_indices)):
        eventName = "TREATMENT_ROOM"
        eventSpot = person_events[TR_start_indices[i]][2] + 1
        eventStartTime = round(person_events[TR_start_indices[i]][1], 2)
        eventDuration = round(person_events[TR_end_indices[i]][1] - person_events[TR_start_indices[i]][1], 2)
        information.append([TR_end_indices[i], eventName, eventSpot, eventStartTime, eventDuration])
    if len(TR_start_indices) != len(TR_end_indices):
        eventName = "TREATMENT_ROOM"
        eventSpot = person_events[TR_start_indices[-1]][2] + 1
        eventStartTime = round(person_events[TR_start_indices[-1]][1], 2)
        eventDuration = 10000
        information.append([TR_start_indices[-1], eventName, eventSpot, eventStartTime, eventDuration])

    # Majors Room
    majors_start_indices = event_indices('Got majors', event_names)
    majors_end_indices = event_indices('Left majors', event_names)

    for i in range(len(majors_end_indices)):
        eventName = "MAJORS"
        eventSpot = person_events[majors_start_indices[i]][2] + 1
        eventStartTime = round(person_events[majors_start_indices[i]][1], 2)
        eventDuration = round(person_events[majors_end_indices[i]][1] - person_events[majors_start_indices[i]][1], 2)
        information.append([majors_end_indices[i], eventName, eventSpot, eventStartTime, eventDuration])
    if len(majors_start_indices) != len(majors_end_indices):
        eventName = "MAJORS"
        eventSpot = person_events[majors_start_indices[-1]][2] + 1
        eventStartTime = round(person_events[majors_start_indices[-1]][1], 2)
        eventDuration = 10000
        information.append([majors_start_indices[-1], eventName, eventSpot, eventStartTime, eventDuration])

    # Resus Room
    resus_start_indices = event_indices('Got resus', event_names)
    resus_end_indices = event_indices('Left resus', event_names)

    for i in range(len(resus_end_indices)):
        eventName = "RESUS"
        eventSpot = person_events[resus_start_indices[i]][2] + 1
        eventStartTime = round(person_events[resus_start_indices[i]][1], 2)
        eventDuration = round(person_events[resus_end_indices[i]][1] - person_events[resus_start_indices[i]][1], 2)
        information.append([resus_end_indices[i], eventName, eventSpot, eventStartTime, eventDuration])
    if len(resus_start_indices) != len(resus_end_indices):
        eventName = "RESUS"
        eventSpot = person_events[resus_start_indices[-1]][2] + 1
        eventStartTime = round(person_events[resus_start_indices[-1]][1], 2)
        eventDuration = 10000
        information.append([resus_start_indices[-1], eventName, eventSpot, eventStartTime, eventDuration])

    # SDEC Room
    sdec_start_indices = event_indices('Got sdec', event_names)
    sdec_end_indices = event_indices('Left sdec', event_names)

    for i in range(len(sdec_end_indices)):
        eventName = "SDEC"
        eventSpot = person_events[sdec_start_indices[i]][2] + 1
        eventStartTime = round(person_events[sdec_start_indices[i]][1], 2)
        eventDuration = round(person_events[sdec_end_indices[i]][1] - person_events[sdec_start_indices[i]][1], 2)
        information.append([sdec_end_indices[i], eventName, eventSpot, eventStartTime, eventDuration])
    if len(sdec_start_indices) != len(sdec_end_indices):
        eventName = "SDEC"
        eventSpot = person_events[sdec_start_indices[-1]][2] + 1
        eventStartTime = round(person_events[sdec_start_indices[-1]][1], 2)
        eventDuration = 10000
        information.append([sdec_start_indices[-1], eventName, eventSpot, eventStartTime, eventDuration])

    # XRayCT Room
    XRay_start_indices = event_indices('Started Xray', event_names)
    XRay_end_indices = event_indices('Finished Xray', event_names)

    for i in range(len(XRay_end_indices)):
        eventName = "XRAYCT_ROOM"
        eventSpot = 1
        eventStartTime = round(person_events[XRay_start_indices[i]][1], 2)
        eventDuration = round(person_events[XRay_end_indices[i]][1] - person_events[XRay_start_indices[i]][1], 2)
        information.append([XRay_end_indices[i], eventName, eventSpot, eventStartTime, eventDuration])
    if len(XRay_start_indices) != len(XRay_end_indices):
        eventName = "XRAYCT_ROOM"
        eventSpot = 1
        eventStartTime = round(person_events[XRay_start_indices[-1]][1], 2)
        eventDuration = 10000
        information.append([XRay_start_indices[-1], eventName, eventSpot, eventStartTime, eventDuration])

    # Discharge process
    discharge_start_indices = event_indices('Started discharge', event_names)
    discharge_end_indices = event_indices('Finished discharge', event_names)

    for i in range(len(discharge_end_indices)):
        eventName = "DISCHARGE"
        eventSpot = 1
        eventStartTime = round(person_events[discharge_start_indices[i]][1], 2)
        eventDuration = round(person_events[discharge_end_indices[i]][1] - person_events[discharge_start_indices[i]][1],
                              2)
        information.append([discharge_end_indices[i], eventName, eventSpot, eventStartTime, eventDuration])
    if len(discharge_start_indices) != len(discharge_end_indices):
        eventName = "DISCHARGE"
        eventSpot = 1
        eventStartTime = round(person_events[discharge_start_indices[-1]][1], 2)
        eventDuration = 10000
        information.append([discharge_start_indices[-1], eventName, eventSpot, eventStartTime, eventDuration])

    # Admission process
    admission_start_indices = event_indices('Started admission', event_names)
    admission_end_indices = event_indices('Finished admission', event_names)

    for i in range(len(admission_end_indices)):
        eventName = "ADMISSION"
        eventSpot = 1
        eventStartTime = round(person_events[admission_start_indices[i]][1], 2)
        eventDuration = round(person_events[admission_end_indices[i]][1] - person_events[admission_start_indices[i]][1],
                              2)
        information.append([admission_end_indices[i], eventName, eventSpot, eventStartTime, eventDuration])
    if len(admission_start_indices) != len(admission_end_indices):
        eventName = "ADMISSION"
        eventSpot = 1
        eventStartTime = round(person_events[admission_start_indices[-1]][1], 2)
        eventDuration = 10000
        information.append([admission_start_indices[-1], eventName, eventSpot, eventStartTime, eventDuration])

    return information

# Function for building event json
def build_event_json(eventName, person, acuity, areaNumber, time, duration):
    
    event = {
        "event": eventName,
        "person": person,
        "acuity": acuity,
        "time": time,
        "duration": duration

    }
    #this has all the event names with the location
    events_dict = {
        "GO_TO_WAITING_ROOM": "waitingRoomSeat",
        "TAKE_A_SEAT": "waitingRoomSeat",
        "WAIT_IN_WAITING_ROOM": "waitingRoomSeat",
        "GO_TO_TREATMENT_ROOM": "treatmentRoom", 
        "GET_TREATMENT": "treatmentRoom",
        "GO_TO_MAJORS": "majorRoom",
        "GET_TREATMENT_MAJORS": "majorRoom",
        "GO_TO_RESUS": "resusRoom",
        "GET_TREATMENT_RESUS": "resusRoom",
        "GO_TO_SDEC": "sdecRoom",
        "GET_TREATMENT_SDEC": "sdecRoom",
        "GO_TO_XRAYCT": "xRayCT",
        "PERFORM_XRAYCT": "xRayCT",
        "GO_TO_CRTP": "CRTP",
        "IN_CRTP": "CRTP",
        "GO_TO_HOSPITAL": "hospital",
        "HOSPITAL_LEAVE": "hospital",
        "GO_TO_EXIT": "exit",
        "LEAVE": "exit"
    }
    if eventName in events_dict:
        event[events_dict[eventName]] = areaNumber
    
    return event


# Function for building json
def build_json(max_waiting_room, max_minors, max_majors, max_resus, max_sdec, time_category, context):

    data = {}
    data["waitingForED"] = 1
    data["waitingRoomSeats"] = max_waiting_room
    data["treatmentRooms"] = max_minors
    data["majorRooms"] = max_majors
    data["resusRooms"] = max_resus
    data["sdecRooms"] = max_sdec
    data["xRayCt"] = 1
    data["CRTP"] = 1
    data["hospital"] = 1
    data["exit"] = 1
    data["events"] = []

    event = {}
    event["event"] = "ARRIVE_AT_ED"
    event["time"] = 0
    event["arrival"] = 0
    event["peopleCreated"] = [x for x in range(1, len(time_category.keys()) + 1)]
    data["events"].append(event)
    # For each person, create each event
    for person in range(1, len(time_category.keys()) + 1):
        # for person in range(1, 3):
        person_events = context.events[person]
        acuity = person_events[0][2]
        information = sorted(parse_event_information(person_events))

        if information != []:
            for info in information:
                order, eventName, space, startingtime, duration = info
                nextTime = startingtime
                if eventName == "WAITING_ROOM":
                    if duration == 2 * context.movement_time:
                        duration = context.movement_time
                    else:
                        duration -= context.movement_time
                    data["events"].append(
                        build_event_json("GO_TO_WAITING_ROOM", [person], acuity, space, round(nextTime, 2),
                                         context.movement_time))
                    nextTime += context.movement_time
                    data["events"].append(
                        build_event_json("WAIT_IN_WAITING_ROOM", [person], acuity, space, round(nextTime, 2), duration))
                    nextTime += duration
                elif eventName == "TREATMENT_ROOM":
                    if duration == 2 * context.movement_time:
                        duration = context.movement_time
                    else:
                        duration -= context.movement_time
                    data["events"].append(
                        build_event_json("GO_TO_TREATMENT_ROOM", person, acuity, space, round(nextTime, 2),
                                         context.movement_time))
                    nextTime += context.movement_time
                    data["events"].append(
                        build_event_json("GET_TREATMENT", person, acuity, space, round(nextTime, 2), duration))
                    nextTime += duration
                elif eventName == "MAJORS":
                    if duration == 2 * context.movement_time:
                        duration = context.movement_time
                    else:
                        duration -= context.movement_time
                    data["events"].append(build_event_json("GO_TO_MAJORS", person, acuity, space, round(nextTime, 2),
                                                           context.movement_time))
                    nextTime += context.movement_time
                    data["events"].append(
                        build_event_json("GET_TREATMENT_MAJORS", person, acuity, space, round(nextTime, 2), duration))
                    nextTime += duration
                elif eventName == "RESUS":
                    if duration == 2 * context.movement_time:
                        duration = context.movement_time
                    else:
                        duration -= context.movement_time
                    data["events"].append(build_event_json("GO_TO_RESUS", person, acuity, space, round(nextTime, 2),
                                                           context.movement_time))
                    nextTime += context.movement_time
                    data["events"].append(
                        build_event_json("GET_TREATMENT_RESUS", person, acuity, space, round(nextTime, 2), duration))
                    nextTime += duration
                elif eventName == "SDEC":
                    if duration == 2 * context.movement_time:
                        duration = context.movement_time
                    else:
                        duration -= context.movement_time
                    data["events"].append(build_event_json("GO_TO_SDEC", person, acuity, space, round(nextTime, 2),
                                                           context.movement_time))
                    nextTime += context.movement_time
                    data["events"].append(
                        build_event_json("GET_TREATMENT_SDEC", person, acuity, space, round(nextTime, 2), duration))
                    nextTime += duration
                elif eventName == "XRAYCT_ROOM":
                    if duration == 2 * context.movement_time:
                        duration = context.movement_time
                    else:
                        duration -= context.movement_time
                    data["events"].append(build_event_json("GO_TO_XRAYCT", person, acuity, space, round(nextTime, 2),
                                                           context.movement_time))
                    nextTime += context.movement_time
                    data["events"].append(
                        build_event_json("PERFORM_XRAYCT", person, acuity, space, round(nextTime, 2), duration))
                    nextTime += duration
                elif eventName == "DISCHARGE":
                    if duration == 2 * context.movement_time:
                        duration = context.movement_time
                    else:
                        duration -= context.movement_time
                    data["events"].append(build_event_json("GO_TO_CRTP", person, acuity, space, round(nextTime, 2),
                                                           context.movement_time))
                    nextTime += context.movement_time
                    data["events"].append(
                        build_event_json("IN_CRTP", person, acuity, space, round(nextTime, 2), duration))
                    nextTime += duration
                    data["events"].append(build_event_json("GO_TO_EXIT", person, acuity, space, round(nextTime, 2),
                                                           context.movement_time))
                    nextTime += context.movement_time
                    data["events"].append(
                        build_event_json("LEAVE", person, acuity, space, round(nextTime, 2), duration))
                    nextTime += duration
                elif eventName == "ADMISSION":
                    if duration == 2 * context.movement_time:
                        duration = context.movement_time
                    else:
                        duration -= context.movement_time
                    data["events"].append(build_event_json("GO_TO_CRTP", person, acuity, space, round(nextTime, 2),
                                                           context.movement_time))
                    nextTime += context.movement_time
                    data["events"].append(
                        build_event_json("IN_CRTP", person, acuity, space, round(nextTime, 2), duration))
                    nextTime += duration
                    data["events"].append(build_event_json("GO_TO_HOSPITAL", person, acuity, space, round(nextTime, 2),
                                                           context.movement_time))
                    nextTime += context.movement_time
                    data["events"].append(
                        build_event_json("HOSPITAL_LEAVE", person, acuity, space, round(nextTime, 2), duration))
                    nextTime += duration
            if person_events[-1][0] in ["Left because lost patience"]:
                data["events"].append(
                    build_event_json("GO_TO_EXIT", person, acuity, 1, round(nextTime, 2), context.walk_to_exit))
                nextTime += context.walk_to_exit
                data["events"].append(build_event_json("LEAVE", person, acuity, 1, round(nextTime, 2), 0.2))
    return data

# Class NpEncoder


class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)
