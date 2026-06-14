# Imports
import pandas as pd
import numpy as np
import simpy
import random

# Function for performing CT, XRay, Bloods


def perform_CT_XRay_Blood(context, env, ed, patient, ct_percentage, XRay_percentage, blood_percentage,
                          time_CT, time_XRay, time_blood):

    # CT
    ct = random.choices([True, False], weights=(ct_percentage, 100 - ct_percentage), k=1)[0]
    if ct:
        yield env.process(ed.patient_performs_CT(patient, time_CT))
        context.events[patient].append(('CT finished', env.now))
    # X-ray
    XR = random.choices([True, False], weights=(XRay_percentage, 100 - XRay_percentage), k=1)[0]
    if XR:
        yield env.process(ed.patient_performs_XRay(patient, time_XRay))
        context.events[patient].append(('XRay finished', env.now))
    # Blood
    blood = random.choices([True, False], weights=(blood_percentage, 100 - blood_percentage), k=1)[0]
    if blood:
        yield env.process(ed.patient_performs_blood(patient, time_blood))
        context.events[patient].append(('Blood finished', env.now))

    return context

# Function to get time until 8am for patient who has arrived to ED. This is a legacy function that is not used in the
# main model.


def get_time_until8am(arrived):
    key = arrived
    days = int(key / 60 / 24)
    hours = int(key / 60 % 24)
    minutes = int(key % 60)
    seconds = int((key % 60 - (key % 60)) * 60)
    date = pd.to_datetime('2023-10-01 00:00:00') + pd.Timedelta(pd.offsets.Day(days)) + pd.Timedelta(
        pd.offsets.Hour(hours)) + pd.Timedelta(pd.offsets.Minute(minutes)) + pd.Timedelta(pd.offsets.Second(seconds))
    if date.hour < 8:
        next_8am = pd.datetime(date.year, date.month, date.day, 8, 0, 0)

    else:
        next_8am = pd.datetime(date.year, date.month, date.day + 1, 8, 0, 0)

    time_until8am = next_8am - date
    time_until8am_mins = time_until8am.total_seconds() / 60
    return time_until8am_mins


# Function for getting and leaving seat from a particular room.


def generic_get_leave_seat(context, patient, env, ed, directionandroom, edroom):

    # If got room
    if directionandroom.split()[0] == 'Got':
        yield getattr(ed, edroom).get(1)

        # If 'Got minors' then leave waiting room
        if directionandroom == "Got minors":
            # Leave WR
            yield ed.waiting_room.put(1)
            context.events[patient].append(
                ('Left waiting room', env.now, np.where(context.wr_seats == patient)[0][0]))
            context.wr_seats[np.where(context.wr_seats == patient)[0][0]] = 0

            # There's some movement time in leaving waiting room.
            yield env.timeout(2 * context.movement_time)

        context.events[patient].append((directionandroom, env.now,
                                        np.where(getattr(context, edroom + '_seats') == 0)[0][0]))
        getattr(context, edroom + '_seats')[np.where(getattr(context, edroom + '_seats') == 0)[0][0]] = patient

    # Else if left room
    else:
        yield getattr(ed, edroom).put(1)
        context.events[patient].append((directionandroom, env.now))
        getattr(context, edroom + '_seats')[np.where(getattr(context, edroom + '_seats') == patient)[0][0]] = 0

    return context, getattr(ed, edroom)


# Function for performing interruption event


def perform_interruption_event(interrupt, env, context, patient, doctor_type, doctor_name):

    by = interrupt.cause.by
    usage = env.now - interrupt.cause.usage_since
    context.timeLeft[patient] -= usage
    setattr(context, 'time_' + doctor_type, getattr(context, 'time_' + doctor_type) + usage)
    context.events[patient].append((doctor_name + 'Interrupted at', env.now, usage))

    return by, usage, context



#assessment by doctor with different effects of interruption
#interruption can have a strong effect (interruption_effect = 'strong' and timeoutduration > 0)
#or a weak effect (interruption_effect = 'weak' and timeoutduration = 0 and initial_priority = 1)
def assess_with_interruption(time_assess, context, patient, ed,
                             env, num_doctors, my_vars, doctor_type,
                             doctor_name,
                             timeoutduration,
                             initial_priority,
                             interruption_effect):
                                                                        
    # Set time left to be assessment time
    context.timeLeft[patient] = time_assess
    times_interrupt = 0
    #for a weak effect of interruption effectively there is no timeout
    if interruption_effect == 'weak':
        timeoutduration = 10000
    # Request doctor - assess - release doctor
    while context.timeLeft[patient] > 0:
        try:
            #initial priority is ignored for interrupt_effect = weak
            if ((times_interrupt == 0) and (interruption_effect == 'strong')):
                context.priority[patient] = initial_priority
            req = getattr(ed, doctor_type).request(priority=context.priority[patient], preempt=True)
            timeout = env.timeout(timeoutduration)
            results = yield req | timeout
       
            # Doctor is requested
            if req in results:
                context, my_vars, env = assign_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name)
                assess_start = env.now
                # Doctor performs assessment
                yield env.process(ed.doctor_performs_assessment(patient, context.timeLeft[patient]))
                context.events[patient].append(('Finished assessment', env.now))

                # Doctor is released
                yield getattr(ed, doctor_type).release(req)
                context, my_vars, env = release_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name)
                setattr(context, 'time_' + doctor_type, getattr(context, 'time_' + doctor_type) + env.now - assess_start)
                context.timeLeft[patient] = 0
                # Doctor is requested unless there is this interruption.
            else:
                req.cancel()
                if times_interrupt == 0:
                        context.priority[patient] = 2.1
                req = getattr(ed, doctor_type).request(priority=context.priority[patient], preempt=True)
                yield req
                context, my_vars, env = assign_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name)
                assess_start = env.now
                yield env.process(ed.doctor_performs_assessment(patient, context.timeLeft[patient]))
                context.events[patient].append(('Finished assessment', env.now))
                yield getattr(ed, doctor_type).release(req)
                # Update doctors list
                context, my_vars, env = release_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name)
                setattr(context, 'time_' + doctor_type, getattr(context, 'time_' + doctor_type) + env.now - assess_start)
                context.timeLeft[patient] = 0

        
        except simpy.Interrupt as interrupt:
            if interruption_effect == 'strong':
                times_interrupt += 1
            
            # Perform interruption
            by, usage, context = perform_interruption_event(interrupt, env, context, patient, doctor_type, doctor_name)
            # Change priority of patient to lower value.
            if usage == 0:
                if interruption_effect == 'strong':
                    context.priority[patient] = max(1,
                                                context.priority[patient] - random.uniform(0.001, 0.01))
                elif interruption_effect == 'weak':
                    context.priority[patient] = max(0,
                                                context.priority[patient] - random.uniform(0.001, 0.01))
            else:
                if interruption_effect == 'strong':
                    context.priority[patient] = max(1,
                                                context.priority[patient] - random.uniform(0.001, 0.1))
                elif interruption_effect == 'weak':
                    context.priority[patient] = max(0,
                                                context.priority[patient] - random.uniform(0.001, 0.01))
                       
                # Update doctors list
                context, my_vars, env = release_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name)

    return context, my_vars


#this function assigns a doctor and records the event
def assign_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name):
    
    #find available doctor and assign in context
    getattr(context, doctor_type)[np.where(getattr(context, doctor_type) == 0)[0][0]] = patient
    for i in range(num_doctors):
        my_vars[i] = getattr(context, doctor_type)[i]
    getattr(context, doctor_type + '_list').append((env.now, list(my_vars.values())))
    
    #record the event
    context.events[patient].append(('Requested' + ' ' + doctor_name + 'doctor', env.now))

    return context, my_vars, env

#this function releases a doctor and records the event
def release_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name):
    getattr(context, doctor_type)[np.where(getattr(context, doctor_type) == patient)[0][0]] = 0
    for i in range(num_doctors):
        my_vars[i] = getattr(context, doctor_type)[i]
    getattr(context, doctor_type + '_list').append((env.now, list(my_vars.values())))
    context.events[patient].append(('Released' + ' ' + doctor_name + 'doctor', env.now))

    return context, my_vars, env


# Function for diagnosis, treatment, discharge without interruption
##new function
def diagnose_treat_discharge_without_interruption(context, patient, ed, my_vars, num_doctors, env, time_treat,
                                                  time_discharge, doctor_type, doctor_name):
    #request doctor
    req = getattr(ed, doctor_type).request(priority=context.priority[patient])
    yield req
    context, my_vars, env = assign_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name)
    #perform diagnosis, treatment and discharge
    dtd_start = env.now
    yield env.process(ed.doctor_performs_DTD(patient, time_treat + time_discharge))

    context.events[patient].append(('Finished DTD', env.now))
    setattr(context, 'time_' + doctor_type, getattr(context, 'time_' + doctor_type) + (env.now - dtd_start))

    # Doctor is released.
    yield getattr(ed, doctor_type).release(req)
    context, my_vars, env = release_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name)

    return context, my_vars



#new function for diagnosis, treatment, discharge with interruption
def diagnose_treat_discharge_with_interruption(context, patient, ed, my_vars, num_doctors, env, time_treat,
                                               time_discharge, timewait, doctor_type, doctor_name):
    context.timeLeft[patient] = time_treat + time_discharge
    times_interrupt = 0
    while context.timeLeft[patient] > 0:
        try:
            req = getattr(ed, doctor_type).request(priority=context.priority[patient], preempt=True)
            timeout = env.timeout(timewait)
            results = yield req | timeout
            if req in results:
                context, my_vars, env = assign_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name)
                # They have not been waiting for more than X minutes
                dtd_start = env.now
                # Then diagnosis, treatment, discharge
                yield env.process(ed.doctor_performs_DTD(patient, context.timeLeft[patient]))
                context.events[patient].append(('Finished DTD', env.now))
                setattr(context, 'time_' + doctor_type, getattr(context, 'time_' + doctor_type) + (env.now - dtd_start))
                # Doctor is released.
                yield getattr(ed, doctor_type).release(req)
                context, my_vars, env = release_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name)
                context.timeLeft[patient] = 0
            else:
                # They have been waiting for more than X minutes
                req.cancel()
                if times_interrupt == 0:
                    context.priority[patient] = 1
                req = getattr(ed, doctor_type).request(priority=context.priority[patient], preempt=True)
                yield req
                context, my_vars, env = assign_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name)
                dtd_start = env.now
                # Then diagnosis, treatment, discharge
                yield env.process(ed.doctor_performs_DTD(patient, context.timeLeft[patient]))
                context.events[patient].append(('Finished DTD', env.now))
                setattr(context, 'time_' + doctor_type, getattr(context, 'time_' + doctor_type) + (env.now - dtd_start))
                # Doctor is released.
                yield getattr(ed, doctor_type).release(req)
                context, my_vars, env = release_doctor(context, patient, my_vars, num_doctors, env, doctor_type, doctor_name)
                context.timeLeft[patient] = 0
        
        except simpy.Interrupt as interrupt:
            times_interrupt += 1
            usage = env.now - interrupt.cause.usage_since
            context.timeLeft[patient] -= usage
            setattr(context, 'time_' + doctor_type, getattr(context, 'time_' + doctor_type) + usage)
            context.events[patient].append((doctor_name + 'Interrupted at', env.now, usage))
            if usage == 0:
                context.priority[patient] = max(0, context.priority[patient] - random.uniform(0.001, 0.01))
            else:
                context.priority[patient] = max(0, context.priority[patient] - random.uniform(0.001, 0.1))
                getattr(context, doctor_type)[np.where(getattr(context, doctor_type) == patient)[0][0]] = 0
                for i in range(num_doctors):
                    my_vars[i] = getattr(context, doctor_type)[i]
                getattr(context, doctor_type + '_list').append((env.now, list(my_vars.values())))

    return context, my_vars

 

# This function initialises the dictionaries for doctors and other staff
def initialise_vars(num_doctors_vect):
    my_vars_dict = {}
    for i in range(num_doctors_vect):
        my_vars_dict[i] = 0
    return my_vars_dict

# This function initialises the room sizes and doctor pool sizes for the context object


def set_resource_size_context(context,
                              max_waiting_room,
                              max_minors,
                              max_resus,
                              max_sdec,
                              max_majors,
                              num_doctors,
                              num_sdec_doctors,
                              num_rat_doctors,
                              num_nt_doctors):
    
    context.wr_seats = np.zeros(max_waiting_room)
    context.minors_seats = np.zeros(max_minors)
    context.resus_seats = np.zeros(max_resus)
    context.sdec_seats = np.zeros(max_sdec)
    context.majors_seats = np.zeros(max_majors)
    context.doctors = np.zeros(num_doctors)
    context.sdec_doctors = np.zeros(num_sdec_doctors)
    context.rat_doctors = np.zeros(num_rat_doctors)
    context.nt_doctors = np.zeros(num_nt_doctors)
    return context
