# /*

#     Sim-ED : Emergency Department Simulation 2023
#     Copyright (C) 2023 Thomas Hughes, Cambridge UK

#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.

#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.

#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <https://www.gnu.org/licenses/>.

# */

# /*

# Subsequent contributors to the code include:

# Health Economics Unit (HEU): David Sgorbati, Joseph Lillington, Javier Igea, Santosh Kumar, Sophie Hodges.
# DHSC - UEC team: Janos Suto, Lucy Palmer, Matthew Lyth, David Green, Tracey Congdon, Ana-Maria Taradaciuc, Cameron Rose

# Acknowledgement should be given to all contributors when further developing the code.

# */

# Import modules
import utils.producePDF as producePDF
import simpy
import random
import matplotlib
matplotlib.use('Agg')
import numpy as np
import pandas as pd
import json
import utils.inputs as input
import datetime
import os
import shutil

# Define printing options
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)


# Read in other functions .rom other files

# Read in patient distribution functions - These contain user defined parameters
from utils.patient_distribution_inputs import get_nhpp, get_max_waiting_time

# Read in individual patient functions - These involve actions on an individual patient-level
from utils.individual_patient_functions import \
    generic_get_leave_seat, \
    diagnose_treat_discharge_without_interruption, diagnose_treat_discharge_with_interruption, perform_CT_XRay_Blood, \
    initialise_vars, set_resource_size_context, assess_with_interruption

# Import analysis functions
from utils.analysis_functions import get_room_data, get_mean_occupancy

# Import plotting_functions
from utils.plotting_functions import plotting_functions

# Import animation function
from utils.animation_function import generate_json

# Import json functions
from utils.json_functions import build_json, NpEncoder

# Import sim_visualisation functions
from utils.sim_visualisation import sim_visualisation

# Import ED class
from utils.Class_ED import ED

# Function to run entire simulation. It takes the four user inputs as arguments,
# Plus a context variable to passed around and mitigate the previous use of global variables.


def run(params, context):

    # Let the user know the simulation is running
    print("Simulation running")

    # Make output file empty before later appending
    if not context.monte_carlo:
        f = open("distribution_outputs.csv", "w")
        f.close()

    # Try to run the discrete-event simulation
    try:

      
        # Add additional context object parameters
        context = set_resource_size_context(context,
                                            params.max_waiting_room,
                                            params.max_minors,
                                            params.max_resus,
                                            params.max_sdec,
                                            params.max_majors,
                                            params.num_doctors,
                                            params.num_sdec_doctors,
                                            params.num_rat_doctors,
                                            params.num_nt_doctors)
        #Sending these parameters to context variable
        context.mean_target = params.mean_target
        context.std_target = params.std_target
        context.mean_bed = params.mean_bed
        context.std_bed = params.std_bed

        # Function for simulating the ED process. The process depends upon your acuity.
        # Function is on an individual person basis.

        def go_to_AE(env, patient, ed, acuity, patience, context):

            # Initialisation - boolean to indicate that patient has not left ED.
            left[patient] = False

            # Has not gone through sdec
            got_sdec_boolean = False

            # Read in input times for assessment, treatment, and discharge.
            # These depend upon acuity. The assessment times differ depending on type of doctor, nt, rat vs generic.
            (time_assess_nt,
             time_assess_rat,
             time_wait_mh,
             time_assess,
             time_treat, 
             time_discharge) = input.get_doctor_times(acuity)

            # Read in diagnostic percentages
            (ct_percentage,
             XRay_percentage,
             blood_percentage) = input.get_diagnostic_percentages(acuity)

            # Read in times for diagnostics
            (time_CT,
             time_XRay,
             time_blood) = input.get_diagnostic_times(acuity)

            # Setup
            if env.now > context.time_end and context.number_treated_init == 0:
                context.number_treated_init = len(waiting_time.keys())

            # Acuity 1 and 2 - Most serious people
            if acuity in ['acuity 1', 'acuity 2']:

                # Define decision making booleans

                # True means patient arrives by ambulance. False means patient arrives of own accord.
                context.ambulance_vs_nonambulance_boolean = random.choices([True, False], weights=(
                    params.ambulance_vs_nonambulance_Percentage, 100 - params.ambulance_vs_nonambulance_Percentage), k=1)[0]

                # People going to resus from non-ambulance arm. True means going to resus as opposed to going
                # to either direct majors or indirect resus through waiting room
                context.a12_nonambulance_resus_vs_non_resus_boolean = random.choices([True, False], weights=(
                    params.a12_nonambulance_resus_vs_non_resus_Percentage,
                    100 - params.a12_nonambulance_resus_vs_non_resus_Percentage), k=1)[0]

                # Decision for non-ambulance patient who has followed non-resus arm to go to majors directly,
                # as opposed to waiting room and then resus.
                context.ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_boolean = random.choices([True, False], weights=(
                    params.ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_Percentage,
                    100 - params.ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_Percentage), k=1)[0]

                # Decision for person who arrives by ambulance to go from Resus or Majors.
                # True means go to Majors.
                context.ac12_ambulance_Majors_vs_Resus_boolean = random.choices([True, False], weights=(
                    params.ac12_ambulance_Majors_vs_Resus_Percentage, 100 - params.ac12_ambulance_Majors_vs_Resus_Percentage), k=1)[0]

                # Start processes

                # Arrivals
                # If person arrives by ambulance they have event 'Arrived'
                # (currently model does label these differently to non-ambulance arrivals, see else loop below)
                if context.ambulance_vs_nonambulance_boolean:

                    context.arrival_time[patient] = env.now
                    context.events[patient] = [('Arrived', env.now, acuity)]
                    arrive = env.now

                # Else if person arrives of own accord (non-ambulance).
                else:

                    context.arrival_time[patient] = env.now
                    context.events[patient] = [('Arrived', env.now, acuity)]
                    arrive = env.now

                # Initialising dicts for doctors and other staff
                my_vars = initialise_vars(params.num_doctors)
                my_sdec_vars = initialise_vars(params.num_sdec_doctors)
                my_rat_vars = initialise_vars(params.num_rat_doctors)
                my_nt_vars = initialise_vars(params.num_nt_doctors)

                # Person is registered - This applies to both ambulance and non-ambulance arrivals
                yield env.process(ed.patient_performs_registration(patient, acuity))

                # Case where patient has arrived by ambulance and has been registered:
                if context.ambulance_vs_nonambulance_boolean:

                    # Patient has combined RAT-NT according to the process map in parallel.
                    # Currently, we assume that assessment time is NT duration
                    # and resource is NT.
                    context.priority[patient] = 1  # Patient made priority 1
                    doctor_type = 'nt_doctors'
                    doctor_name = 'nt_'

                    result = yield from assess_with_interruption(
                        time_assess_nt, context,
                        patient, ed, env,
                        params.num_nt_doctors, my_nt_vars, doctor_type, doctor_name,
                        timeoutduration = 0,
                        interruption_effect = 'weak',
                        initial_priority = 0)

                    context, my_nt_vars = result

                    # If person goes to majors instead of resus
                    if context.ac12_ambulance_Majors_vs_Resus_boolean:

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Person goes to majors
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Got majors', edroom='majors')

                        context, ed.majors = result

                        # There is some movement time in going to majors
                        yield env.timeout(2 * context.movement_time)

                        # Generic Doctor requested - assesses -
                        # Doctor is released - Weaker role of interruption than other acuities and no delay
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from assess_with_interruption(time_assess, context, patient, ed, env,
                                                                     params.num_doctors, my_vars, doctor_type, doctor_name,
                                                                     timeoutduration = 0,
                                                                     interruption_effect = 'weak',
                                                                     initial_priority = 0)
                       
                        context, my_vars = result

                        # Person has CT, X-ray, Bloods - any combination of these.
                        # These are modelled as happening in majors.
                        context = yield from perform_CT_XRay_Blood(context, env, ed, patient, ct_percentage,
                                                                   XRay_percentage, blood_percentage, time_CT,
                                                                   time_XRay, time_blood)

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Generic Doctor is requested - Person is diagnosed, treated and discharged - Person is released
                        # Priority not updated from previous.
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from diagnose_treat_discharge_without_interruption(context, patient,
                                                                                          ed, my_vars,
                                                                                          params.num_doctors, env,
                                                                                          time_treat,
                                                                                          time_discharge,
                                                                                          doctor_type,
                                                                                          doctor_name)

                        context, my_vars = result

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Patient now leaves majors.
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Left majors',
                                                                   edroom='majors')

                        context, ed.majors = result

                        # There is some movement time leaving majors.
                        yield env.timeout(2 * context.movement_time)

                    # Else person goes to resus
                    else:

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Go to Resus
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Got resus',
                                                                   edroom='resus')

                        context, ed.resus = result

                        # There is some movement time in going to resus.
                        yield env.timeout(2 * context.movement_time)

                        # Generic Doctor requested - assesses - Doctor is released - Weaker
                        # role of interruption than other acuities and no delay
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from assess_with_interruption(time_assess, context, patient, ed, env,
                                                                     params.num_doctors, my_vars, doctor_type, doctor_name,
                                                                     timeoutduration = 0,
                                                                     interruption_effect = 'weak',
                                                                     initial_priority = 0)

                        context, my_vars = result

                        # Person has CT, X-ray, Bloods - any combination of these.
                        # These are modelled as happening in resus.
                        # CT
                        context = yield from perform_CT_XRay_Blood(context, env, ed, patient, ct_percentage,
                                                                   XRay_percentage, blood_percentage, time_CT,
                                                                   time_XRay, time_blood)

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Generic Doctor is requested - Person is diagnosed, treated and discharged
                        # - Doctor is released
                        # Priority not updated from previous.
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from diagnose_treat_discharge_without_interruption(context, patient, ed, my_vars,
                                                                                          params.num_doctors, env, time_treat,
                                                                                          time_discharge, doctor_type,
                                                                                          doctor_name)

                        context, my_vars = result

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Patient now leaves resus.
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Left resus',
                                                                   edroom='resus')

                        context, ed.resus = result

                        # There is some movement time leaving resus.
                        yield env.timeout(2 * context.movement_time)

                # Alternative pathway where patient does not arrive by ambulance.
                # The patient has previously been registered:
                else:

                    # Nurse triage
                    # NT Doctor requested - assesses - Doctor is released
                    context.priority[patient] = 1  # Priority 1
                    doctor_type = 'nt_doctors'
                    doctor_name = 'nt_'
                    result = yield from assess_with_interruption(time_assess_nt, context, patient, ed, env,
                                                                     params.num_nt_doctors, my_nt_vars, doctor_type, doctor_name,
                                                                     timeoutduration = 0,
                                                                     interruption_effect = 'weak',
                                                                     initial_priority = 0)
                    
                    context, my_nt_vars = result

                    # Case where person goes to Resus
                    if context.a12_nonambulance_resus_vs_non_resus_boolean:

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Go to Resus
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Got resus',
                                                                   edroom='resus')

                        context, ed.resus = result

                        # There is some movement time in going to resus.
                        yield env.timeout(2 * context.movement_time)

                        # Generic Doctor requested - assesses - Doctor is released -
                        # Weaker role of interruption than other acuities and no delay
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from assess_with_interruption(time_assess, context, patient, ed, env,
                                                                     params.num_doctors, my_vars, doctor_type, doctor_name,
                                                                     timeoutduration = 0,
                                                                     interruption_effect = 'weak',
                                                                     initial_priority = 0)
                        
                        context, my_vars = result

                        # Diagnostic tests - These in the model happen in resus.
                        # CT
                        context = yield from perform_CT_XRay_Blood(context, env, ed, patient, ct_percentage,
                                                                   XRay_percentage, blood_percentage, time_CT,
                                                                   time_XRay, time_blood)

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Generic Doctor is requested - Person is diagnosed, treated and discharged
                        # - Person is released
                        # Priority not updated
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from diagnose_treat_discharge_without_interruption(context, patient, ed, my_vars,
                                                                                          params.num_doctors, env, time_treat,
                                                                                          time_discharge, doctor_type,
                                                                                          doctor_name)

                        context, my_vars = result

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Patient now leaves resus.
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Left resus',
                                                                   edroom='resus')

                        context, ed.resus = result

                        # There is some movement time leaving resus.
                        yield env.timeout(2 * context.movement_time)

                    # Case where person follows non-resus arm. There are two choices - patient
                    # either goes to majors directly or goes to waiting room (and subsequently to resus).
                    else:

                        # If person goes to majors directly
                        if context.ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_boolean:

                            # 1 min delay to help process mining
                            yield env.timeout(1)

                            # Go to majors
                            result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                       directionandroom='Got majors',
                                                                       edroom='majors')

                            context, ed.majors = result

                            # There is some waiting time in going to waiting room.
                            yield env.timeout(2 * context.movement_time)

                            # Generic Doctor requested - assesses - Doctor is released -
                            # Weaker role of interruption than other acuities and no delay
                            doctor_type = 'doctors'
                            doctor_name = ''
                            result = yield from assess_with_interruption(time_assess, context, patient, ed, env,
                                                                     params.num_doctors, my_vars, doctor_type, doctor_name,
                                                                     timeoutduration = 0,
                                                                     interruption_effect = 'weak',
                                                                     initial_priority = 0)
                            
                            context, my_vars = result

                            # Diagnostic tests - These in the model happen in majors
                            # CT
                            context = yield from perform_CT_XRay_Blood(context, env, ed, patient, ct_percentage,
                                                                       XRay_percentage, blood_percentage, time_CT,
                                                                       time_XRay, time_blood)

                            # 1 min delay to help process mining
                            yield env.timeout(1)

                            # Generic Doctor is requested - Person is diagnosed, treated and discharged -
                            # Person is released
                            # Priority not updated
                            doctor_type = 'doctors'
                            doctor_name = ''
                            result = yield from diagnose_treat_discharge_without_interruption(context, patient, ed,
                                                                                              my_vars, params.num_doctors,
                                                                                              env, time_treat,
                                                                                              time_discharge,
                                                                                              doctor_type,
                                                                                              doctor_name)

                            context, my_vars = result

                            # 1 min delay to help process mining
                            yield env.timeout(1)

                            # Patient now leaves majors.
                            result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                       directionandroom='Left majors',
                                                                       edroom='majors')

                            context, ed.majors = result

                            # There is some movement time leaving resus.
                            yield env.timeout(2 * context.movement_time)

                        # Else patient goes to waiting room and then to resus.
                        else:

                            # 1 min delay to help process mining
                            yield env.timeout(1)

                            # Go to WR
                            yield ed.waiting_room.get(1)
                            context.events[patient].append(('Got waiting room', env.now,
                                                            np.where(context.wr_seats == 0)[0][0]))
                            context.wr_seats[np.where(context.wr_seats == 0)[0][0]] = patient

                            # There is some movement time in going to waiting room.
                            yield env.timeout(2 * context.movement_time)

                            # Assessment by RAT. Assessment by RAT deemed to be in WR.
                            # Doctor requested - assesses - Doctor is released -
                            # Weaker role of interruption than other acuities and no delay. #
                            # RAT assessment modelled as happening in WR.
                            doctor_type = 'rat_doctors'
                            doctor_name = 'rat_'
                            result = yield from assess_with_interruption(time_assess_rat, context, patient, ed, env,
                                                                     params.num_rat_doctors, my_rat_vars, doctor_type, doctor_name,
                                                                     timeoutduration = 0,
                                                                     interruption_effect = 'weak',
                                                                     initial_priority = 0)
                            

                            context, my_rat_vars = result

                            # 1 min delay to help process mining
                            yield env.timeout(1)

                            # Leave WR
                            yield ed.waiting_room.put(1)
                            context.events[patient].append(
                                ('Left waiting room', env.now, np.where(context.wr_seats == patient)[0][0]))
                            context.wr_seats[np.where(context.wr_seats == patient)[0][0]] = 0

                            # There's some movement time in leaving waiting room.
                            yield env.timeout(2 * context.movement_time)

                            # Go to Resus
                            result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                       directionandroom='Got resus',
                                                                       edroom='resus')

                            context, ed.resus = result

                            # There is some movement time in going to resus.
                            yield env.timeout(2 * context.movement_time)

                            # Generic Doctor requested - assesses - Doctor is released -
                            # Weaker role of interruption than other acuities and no delay
                            doctor_type = 'doctors'
                            doctor_name = ''
                            result = yield from assess_with_interruption(time_assess, context, patient, ed, env,
                                                                     params.num_doctors, my_vars, doctor_type, doctor_name,
                                                                     timeoutduration = 0,
                                                                     interruption_effect = 'weak',
                                                                     initial_priority = 0)
                            
                            context, my_vars = result

                            # Diagnostic tests. These are deemed to happen in resus.
                            # CT
                            context = yield from perform_CT_XRay_Blood(context, env, ed, patient, ct_percentage,
                                                                       XRay_percentage, blood_percentage, time_CT,
                                                                       time_XRay, time_blood)

                            # 1 min delay to help process mining
                            yield env.timeout(1)

                            # Generic doctor is requested - Person is diagnosed, treated and discharged -
                            # Person is released
                            # Priority note updated
                            doctor_type = 'doctors'
                            doctor_name = ''
                            result = yield from diagnose_treat_discharge_without_interruption(context, patient, ed,
                                                                                              my_vars, params.num_doctors,
                                                                                              env, time_treat,
                                                                                              time_discharge,
                                                                                              doctor_type, doctor_name)

                            context, my_vars = result

                            # 1 min delay to help process mining
                            yield env.timeout(1)

                            # Patient now leaves resus.
                            result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                       directionandroom='Left resus',
                                                                       edroom='resus')

                            context, ed.resus = result

                            # There is some movement time leaving resus.
                            yield env.timeout(2 * context.movement_time)

            # Next scenario is for acuity 4 and 5 people (Least sick people).
            elif acuity in ['acuity 4', 'acuity 5']:  # acuity 4 or 5

                # Define decision-making boolean

                # True means person may go to sdec if also acuity 4 and if in opening hours.
                context.sdec_boolean_patient = random.choices([True, False], weights=(params.sdec_Percentage,
                                                                                      100 - params.sdec_Percentage), k=1)[0]

                # Arrivals process (all by non-ambulance)
                context.arrival_time[patient] = env.now
                context.events[patient] = [('Arrived', env.now, acuity)]
                arrive = env.now

                # Initialising dicts for doctors and other staff
                my_vars = initialise_vars(params.num_doctors)
                my_sdec_vars = initialise_vars(params.num_sdec_doctors)
                my_rat_vars = initialise_vars(params.num_rat_doctors)
                my_nt_vars = initialise_vars(params.num_nt_doctors)

                # Person is registered.
                yield env.process(ed.patient_performs_registration(patient, acuity))

                # Nurse-led triage
                # Doctor requested - assesses - Doctor is released
                initial_priority = 3
                timeoutduration = 60  # Timeoutduration for function
                doctor_type = 'nt_doctors'
                doctor_name = 'nt_'
                result = yield from assess_with_interruption(time_assess_nt, context, patient, ed, env,
                                                                     params.num_nt_doctors, my_nt_vars, doctor_type, doctor_name,
                                                                     timeoutduration = timeoutduration,
                                                                     initial_priority = initial_priority,
                                                                     interruption_effect = 'strong')
 
                context, my_nt_vars = result

                # Assuming sdec is open sdec_opening_hour to sdec_closing_hour.
                if (env.now % 1440 > 60 * params.sdec_opening_hour) and (env.now % 1440 < 60 * params.sdec_closing_hour):
                    sdec_boolean_open = True
                else:
                    sdec_boolean_open = False

                # If diverted to sdec and sdec is open and acuity 4
                if context.sdec_boolean_patient and sdec_boolean_open and acuity == 'acuity 4':

                    # Boolean useful for writing data to output_distribution file.
                    got_sdec_boolean = True

                    # 1 min delay to help process mining
                    yield env.timeout(1)

                    # Go to SDEC
                    result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                               directionandroom='Got sdec',
                                                               edroom='sdec')

                    context, ed.sdec = result

                    # There is some movement time going to sdec.
                    yield env.timeout(2 * context.movement_time)

                    # Request doctor - assess - release
                    timeoutduration = 60  # Timeoutduration for function
                    doctor_type = 'sdec_doctors'
                    doctor_name = 'sdec_'
                    result = yield from assess_with_interruption(time_assess, context, patient, ed, env,
                                                                     params.num_sdec_doctors, my_sdec_vars, doctor_type, doctor_name,
                                                                     timeoutduration = timeoutduration,
                                                                     initial_priority = initial_priority,
                                                                     interruption_effect = 'strong')

                    context, my_sdec_vars = result

                    # 1 min delay to help process mining
                    yield env.timeout(1)

                    # Diagnose-treat-discharge with interruption process
                    # Diagnose-treat-discharge with interruption process
                    # to be same as generic doctors.
                    timewait = 60
                    doctor_type = 'sdec_doctors'
                    doctor_name = 'sdec_'
                    result = yield from diagnose_treat_discharge_with_interruption(context, patient, ed,
                                                                                   my_sdec_vars,
                                                                                   params.num_sdec_doctors, env,
                                                                                   time_treat, time_discharge,
                                                                                   timewait, doctor_type,
                                                                                   doctor_name)

                    context, my_sdec_vars = result

                    # 1 min delay to help process mining
                    yield env.timeout(1)

                    # Patient leaves SDEC.
                    result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                               directionandroom='Left sdec',
                                                               edroom='sdec')

                    context, ed.sdec = result

                    # There is some movement time leaving sdec.
                    yield env.timeout(2 * context.movement_time)

                # Else go through waiting room - diagnostics process.
                else:

                    # Did not go through sdec
                    got_sdec_boolean = False

                    # If person has lost patience prior to going to waiting room., then leave
                    if env.now > arrive + patience:
                        left[patient] = True
                        context.events[patient].append(('Left because lost patience', env.now))
                    else:

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Go to WR
                        yield ed.waiting_room.get(1)
                        context.events[patient].append(('Got waiting room', env.now,
                                                        np.where(context.wr_seats == 0)[0][0]))
                        context.wr_seats[np.where(context.wr_seats == 0)[0][0]] = patient

                        # There is some movement time in going to resus.
                        yield env.timeout(2 * context.movement_time)

                    # If person has lost patience prior to going to minors., then leave:
                    if left[patient] == True:
                        pass
                    elif env.now > arrive + patience:
                        left[patient] = True

                        # Leave waiting room
                        yield ed.waiting_room.put(1)
                        context.events[patient].append(
                            ('Left waiting room', env.now, np.where(context.wr_seats == patient)[0][0]))
                        context.wr_seats[np.where(context.wr_seats == patient)[0][0]] = 0

                        # There's some movement time in leaving waiting room.
                        yield env.timeout(2 * context.movement_time)

                        # Add event
                        context.events[patient].append(('Left because lost patience', env.now))
                    else:

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Go to Minors and leave waiting room- There's now a leave waiting room aspect built in
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Got minors',
                                                                   edroom='minors')

                        context, ed.minors = result

                        # There is some movement time in going to resus.
                        yield env.timeout(2 * context.movement_time)

                        # Generic Doctor requested - assesses - Doctor is released -
                        # Weaker role of interruption than other acuities and no delay
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from assess_with_interruption(time_assess, context, patient, ed, env,
                                                                     params.num_doctors, my_vars, doctor_type, doctor_name,
                                                                     timeoutduration = timeoutduration,
                                                                     initial_priority = initial_priority,
                                                                     interruption_effect = 'strong')

                        context, my_vars = result

                        # Diagnostic tests. These are deemed to happen in minors.
                        # CT
                        context = yield from perform_CT_XRay_Blood(context, env, ed, patient, ct_percentage,
                                                                   XRay_percentage, blood_percentage,
                                                                   time_CT, time_XRay, time_blood)

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Patient now leaves minors.
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Left minors',
                                                                   edroom='minors')

                        context, ed.minors = result

                        # There is some movement time in leaving minors.
                        yield env.timeout(2 * context.movement_time)

                    # If person has lost patience prior to going back to waiting room, then leave:
                    if left[patient] == True:
                        pass
                    elif env.now > arrive + patience:
                        left[patient] = True
                        context.events[patient].append(('Left because lost patience', env.now))
                    else:
                        # Person goes back to waiting room
                        yield ed.waiting_room.get(1)
                        context.events[patient].append(('Got waiting room',
                                                        env.now, np.where(context.wr_seats == 0)[0][0]))
                        context.wr_seats[np.where(context.wr_seats == 0)[0][0]] = patient

                        # There is some movement time in going to waiting room.
                        yield env.timeout(2 * context.movement_time)

                        # Generic doctor is requested - Person is diagnosed, treated and discharged -
                        # Person is released
                        # Priority note updated
                        timewait = 60
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from diagnose_treat_discharge_with_interruption(context, patient,
                                                                                       ed, my_vars,
                                                                                       params.num_doctors, env,
                                                                                       time_treat,
                                                                                       time_discharge,
                                                                                       timewait, doctor_type,
                                                                                       doctor_name)

                        context, my_vars = result

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Leave WR
                        yield ed.waiting_room.put(1)
                        context.events[patient].append(
                            ('Left waiting room', env.now, np.where(context.wr_seats == patient)[0][0]))
                        context.wr_seats[np.where(context.wr_seats == patient)[0][0]] = 0

                        # There is some movement time in leaving waiting room.
                        yield env.timeout(2 * context.movement_time)

            # Acuity 3 (Medium severity)
            elif acuity == 'acuity 3':  # acuity 3

                # Define decision-making booleans:

                # True means patient arrives by ambulance
                context.ambulance_vs_nonambulance_boolean = random.choices([True, False],
                                                                           weights=(params.ambulance_vs_nonambulance_Percentage,
                                                                           100 - params.ambulance_vs_nonambulance_Percentage),
                                                                           k=1)[0]

                # True means person who arrived by ambulance is a mental health patient
                context.a3_AmbulanceMHPatient_boolean = random.choices([True, False],
                                                                       weights=(params.a3_AmbulanceMHPatient_Percentage,
                                                                                100 - params.a3_AmbulanceMHPatient_Percentage),
                                                                       k=1)[0]

                # True means person who arrived by non-ambulance is a mental health patient
                context.a3_NonAmbulance_MHPatient_boolean = \
                    random.choices([True, False], weights=(params.a3_NonAmbulance_MHPatient_Percentage,
                                                           100 - params.a3_NonAmbulance_MHPatient_Percentage), k=1)[0]

                # Arrivals process
                # Patient arrives by ambulance
                if context.ambulance_vs_nonambulance_boolean:

                    # Person arrives by ambulance
                    context.arrival_time[patient] = env.now
                    context.events[patient] = [('Arrived', env.now, acuity)]
                    arrive = env.now

                # Patient arrives of own accord.
                else:
                    context.arrival_time[patient] = env.now
                    context.events[patient] = [('Arrived', env.now, acuity)]
                    arrive = env.now

                # Initialising dicts for doctors and other staff
                my_vars = initialise_vars(params.num_doctors)
                my_sdec_vars = initialise_vars(params.num_sdec_doctors)
                my_rat_vars = initialise_vars(params.num_rat_doctors)
                my_nt_vars = initialise_vars(params.num_nt_doctors)

                # Person is registered.
                yield env.process(ed.patient_performs_registration(patient, acuity))

                # If patient has arrived by ambulance
                if context.ambulance_vs_nonambulance_boolean:

                    # Person has RAT/Triage nurse
                    # Doctor requested - assesses - Doctor is released
                    initial_priority = 2
                    timeoutduration = 60  # Timeoutduration for function
                    doctor_type = 'nt_doctors'
                    doctor_name = 'nt_'
                    result = yield from assess_with_interruption(time_assess_nt, context, patient, ed, env,
                                                                     params.num_nt_doctors, my_nt_vars, doctor_type, doctor_name,
                                                                     timeoutduration = timeoutduration,
                                                                     initial_priority = initial_priority,
                                                                     interruption_effect = 'strong')

                    context, my_nt_vars = result

                    # If patient is a MH patient, then they have longer assessment in majors.
                    if context.a3_AmbulanceMHPatient_boolean:

                        context.timeLeft[patient] = time_assess

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Person goes to majors
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Got majors',
                                                                   edroom='majors')

                        context, ed.majors = result

                        # Movement time to majors
                        yield env.timeout(2 * context.movement_time)

                        # Request generic doctor - assess - release
                        timeoutduration = 60  # Timeoutduration for function
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from assess_with_interruption(time_assess, context, patient, ed, env,
                                                                     params.num_doctors, my_vars, doctor_type, doctor_name,
                                                                     timeoutduration = timeoutduration,
                                                                     initial_priority = initial_priority,
                                                                     interruption_effect = 'strong')

                        context, my_vars = result

                        # Assuming time_wait_mh delay
                        yield env.timeout(time_wait_mh)

                        # Assuming no diagnostics for MH patient

                        # Generic doctor Diagnose-treat-discharge with interruption
                        # Priority not updated
                        timewait = 60
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from diagnose_treat_discharge_with_interruption(context, patient,
                                                                                       ed, my_vars,
                                                                                       params.num_doctors, env,
                                                                                       time_treat,
                                                                                       time_discharge,
                                                                                       timewait, doctor_type,
                                                                                       doctor_name)

                        context, my_vars = result

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Person leaves majors
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Left majors',
                                                                   edroom='majors')

                        context, ed.majors = result

                        # There is some movement time leaving majors.
                        yield env.timeout(2 * context.movement_time)

                    # Else if person who has arrived by ambulance is not mental health patient, still go to majors
                    else:

                        context.timeLeft[patient] = time_assess

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Person goes to majors
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Got majors',
                                                                   edroom='majors')

                        context, ed.majors = result

                        # Movement time to majors
                        yield env.timeout(2 * context.movement_time)

                        # Request generic doctor - assess - release
                        timeoutduration = 60  # Timeoutduration for function
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from assess_with_interruption(time_assess, context, patient, ed, env,
                                                                     params.num_doctors, my_vars, doctor_type, doctor_name,
                                                                     timeoutduration = timeoutduration,
                                                                     initial_priority = initial_priority,
                                                                     interruption_effect = 'strong')

                        context, my_vars = result

                        # Diagnostic tests - assumed to happen in majors.
                        # Worth validating with PAH if diagnostics would actually occur.
                        # CT
                        context = yield from perform_CT_XRay_Blood(context, env, ed, patient, ct_percentage,
                                                                   XRay_percentage, blood_percentage, time_CT,
                                                                   time_XRay, time_blood)

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Generic doctor Diagnose-treat-discharge with interruption
                        # Priority not updated
                        timewait = 60
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from diagnose_treat_discharge_with_interruption(context, patient,
                                                                                       ed, my_vars,
                                                                                       params.num_doctors, env,
                                                                                       time_treat,
                                                                                       time_discharge,
                                                                                       timewait, doctor_type,
                                                                                       doctor_name)

                        context, my_vars = result

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Person leaves majors
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Left majors',
                                                                   edroom='majors')

                        context, ed.majors = result

                        # There is some movement time leaving majors.
                        yield env.timeout(2 * context.movement_time)

                # Else if person arrives by own accord (not by ambulance)
                else:

                    # Patient has nurse triage
                    # Doctor requested - assesses - Doctor is released
                    initial_priority = 2
                    timeoutduration = 60  # Timeoutduration for function
                    doctor_type = 'nt_doctors'
                    doctor_name = 'nt_'
   
                    result = yield from assess_with_interruption(time_assess_nt, context, patient, ed, env,
                                                                     params.num_nt_doctors, my_nt_vars, doctor_type, doctor_name,
                                                                     timeoutduration = timeoutduration,
                                                                     initial_priority = initial_priority,
                                                                     interruption_effect = 'strong')

                    context, my_nt_vars = result

                    # 1 min delay to help process mining
                    yield env.timeout(5)

                    # Patient goes to WR.
                    yield ed.waiting_room.get(1)
                    context.events[patient].append(
                        ('Got waiting room', env.now, np.where(context.wr_seats == 0)[0][0]))
                    context.wr_seats[np.where(context.wr_seats == 0)[0][0]] = patient

                    # There's some movement time in going to waiting room.
                    yield env.timeout(2 * context.movement_time)

                    # RAT Doctor requested - assesses - Doctor is released
                    timeoutduration = 60  # Timeoutduration for function
                    doctor_type = 'rat_doctors'
                    doctor_name = 'rat_'
                    result = yield from assess_with_interruption(time_assess_rat, context, patient, ed, env,
                                                                     params.num_rat_doctors, my_rat_vars, doctor_type, doctor_name,
                                                                     timeoutduration = timeoutduration,
                                                                     initial_priority = initial_priority,
                                                                     interruption_effect = 'strong')

                    context, my_rat_vars = result

                    # 1 min delay to help process mining
                    yield env.timeout(5)

                    # Leave WR
                    yield ed.waiting_room.put(1)
                    context.events[patient].append(
                        ('Left waiting room', env.now, np.where(context.wr_seats == patient)[0][0]))
                    context.wr_seats[np.where(context.wr_seats == patient)[0][0]] = 0

                    # If patient is a MH patient
                    if context.a3_NonAmbulance_MHPatient_boolean:

                        context.timeLeft[patient] = time_assess

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Person goes to majors
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Got majors',
                                                                   edroom='majors')

                        context, ed.majors = result

                        # Movement time to majors
                        yield env.timeout(2 * context.movement_time)

                        # Request generic doctor - assess - release
                        timeoutduration = 60  # Timeoutduration for function
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from assess_with_interruption(time_assess, context, patient, ed, env,
                                                                     params.num_doctors, my_vars, doctor_type, doctor_name,
                                                                     timeoutduration = timeoutduration,
                                                                     initial_priority = initial_priority,
                                                                     interruption_effect = 'strong')

                        context, my_vars = result

                        # Assuming no diagnostics

                        # Assuming time_wait_mh delay
                        yield env.timeout(time_wait_mh)

                        # Generic doctor Diagnose-treat-discharge with interruption
                        # Priority is not updated
                        timewait = 60
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from diagnose_treat_discharge_with_interruption(context, patient,
                                                                                       ed, my_vars,
                                                                                       params.num_doctors, env,
                                                                                       time_treat,
                                                                                       time_discharge,
                                                                                       timewait, doctor_type,
                                                                                       doctor_name)

                        context, my_vars = result

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Person leaves majors
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Left majors',
                                                                   edroom='majors')

                        context, ed.majors = result

                        # There is some movement time leaving majors.
                        yield env.timeout(2 * context.movement_time)

                    # Else if not a MH patient
                    else:

                        context.timeLeft[patient] = time_assess

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Person goes to majors
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Got majors',
                                                                   edroom='majors')

                        context, ed.majors = result

                        # Movement time to majors
                        yield env.timeout(2 * context.movement_time)

                        # Request generic doctor - assess - release
                        timeoutduration = 60  # Timeoutduration for function
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from assess_with_interruption(time_assess, context, patient, ed, env,
                                                                     params.num_doctors, my_vars, doctor_type, doctor_name,
                                                                     timeoutduration = timeoutduration,
                                                                     initial_priority = initial_priority,
                                                                     interruption_effect = 'strong')

                        context, my_vars = result

                        # Diagnostic tests - assumed to happen in majors.
                        # Worth validating with PAH if diagnostics would actually occur.
                        # CT, X-Ray, Blood
                        context = yield from perform_CT_XRay_Blood(context, env, ed, patient, ct_percentage,
                                                                   XRay_percentage, blood_percentage, time_CT,
                                                                   time_XRay, time_blood)

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Generic doctor Diagnose-treat-discharge with interruption
                        timewait = 60
                        doctor_type = 'doctors'
                        doctor_name = ''
                        result = yield from diagnose_treat_discharge_with_interruption(context, patient,
                                                                                       ed, my_vars,
                                                                                       params.num_doctors, env,
                                                                                       time_treat,
                                                                                       time_discharge,
                                                                                       timewait, doctor_type,
                                                                                       doctor_name)

                        context, my_vars = result

                        # 1 min delay to help process mining
                        yield env.timeout(1)

                        # Person leaves majors
                        result = yield from generic_get_leave_seat(context, patient, env, ed,
                                                                   directionandroom='Left majors',
                                                                   edroom='majors')

                        context, ed.majors = result

                        # There is some movement time leaving majors.
                        yield env.timeout(2 * context.movement_time)

            # This small section has statements independent of acuity - Run admission or discharge process
            if left[patient] == False:

                waiting_time[patient] = env.now - arrive

                # Patient is admitted or discharged
                yield env.process(ed.run_discharge_or_admit(patient, acuity, params.target, got_sdec_boolean, context, env))

        # Function run_ED. Function runs on individual patient basis.

        def run_ED(env, num_doctors, num_sdec_doctors, num_rat_doctors, num_nt_doctors, max_resus,
                   max_sdec, max_majors, max_minors, max_waiting_room, acuity1_perc, acuity2_perc,
                   acuity3_perc, acuity4_perc, acuity5_perc, target):

            ed = ED(env, params.num_doctors, params.num_sdec_doctors, params.num_rat_doctors, params.num_nt_doctors, max_resus,
                    max_sdec, max_majors, max_minors, max_waiting_room)
            patient = 0
            while True:
                t_nhpp = get_nhpp(env.now, params.daily_num_patients)
                yield env.timeout(random.expovariate(1/t_nhpp))
                patient += 1
                max_waiting_time[patient] = get_max_waiting_time()
                time_category[patient] = random.choices(['acuity 1', 'acuity 2', 'acuity 3', 'acuity 4', 'acuity 5'],
                                                        weights=(acuity1_perc, acuity2_perc, acuity3_perc,
                                                                 acuity4_perc, acuity5_perc), k=1)[0]
                env.process(go_to_AE(env, patient, ed, time_category[patient],   max_waiting_time[patient], context))

        # Run main simulation

        # Initialisers
        left = {}
        context.timeLeft = {}
        max_waiting_time = {}
        time_category = {}
        waiting_time = {}
        context.number_treated_init = 0
        number_treated_after = 0
        rdn_seed = random.randint(0, 10000)
        trials = 0
        errorTrials = "no"

        # Run over number of trials - currently max trials set to 4. Trials sets stops stopping criterion.
        while context.number_treated_init == number_treated_after and trials < 4 and context.errorCatch == "":

            # Initialisers
            context.events, context.priority, context.arrival_time, context.time_until_admission, \
                context.time_until_discharge = {}, {}, {}, {}, {}
            context.doctors_list = []
            context.sdec_doctors_list = []
            context.rat_doctors_list = []
            context.nt_doctors_list = []
            context.time_doctors = 0
            context.time_sdec_doctors = 0
            context.time_rat_doctors = 0
            context.time_nt_doctors = 0

            context = set_resource_size_context(context,
                                           params.max_waiting_room,
                                            params.max_minors,
                                            params.max_resus,
                                            params.max_sdec,
                                            params.max_majors,
                                            params.num_doctors,
                                            params.num_sdec_doctors,
                                            params.num_rat_doctors,
                                            params.num_nt_doctors)
            
            left, time_left, context.timeLeft, max_waiting_time, time_category, waiting_time = {}, {}, {}, {}, {}, {}

            # Define initial seed
            random.seed(rdn_seed)

            # Create simpy environment
            env = simpy.Environment()

            # Run ED function
            env.process(run_ED(env, params.num_doctors, params.num_sdec_doctors, params.num_rat_doctors, params.num_nt_doctors,
                               params.max_resus, params.max_sdec, params.max_majors, params.max_minors, params.max_waiting_room,
                               params.acuity1_perc, params.acuity2_perc, params.acuity3_perc, params.acuity4_perc, params.acuity5_perc, params.target))

            # Runs simulation until end time.
            time_end2 = context.time_end+(12*60) #add half a day 'cooldown' to record waiting time for people arriving to end of sim
            env.run(until=time_end2)

            # Updates
            number_treated_after = len(waiting_time.keys())

            if number_treated_after == context.number_treated_init:
                print('Need to change seed')

            # Update seed and number of trials
            rdn_seed += 1
            trials += 1

        # Ensures simulation completes after 3 trials
        if trials == 4:
            errorTrials = "yes"
    # Checks for errors
    except ValueError:

        context.errorCatch = "ValueError"
        errorTrials = "No"
        params.num_doctors = 0
        params.num_sdec_doctors = 0
        params.num_rat_doctors = 0
        params.num_nt_doctors = 0
        params.acuity_type = ""
        params.ed_simtype = ""
        params.sdec_Percentage = ""
        params.sdec_Percentage = ""
        params.ambulance_vs_nonambulance_Percentage = ""
        params.ac12_ambulance_Majors_vs_Resus_Percentage = ""
        params.ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_Percentage = ""
        params.a12_nonambulance_resus_vs_non_resus_Percentage = ""
        params.a3_AmbulanceMHPatient_Percentage = ""
        params.a3_NonAmbulance_MHPatient_Percentage = ""
        time_end2 = 0
        jsondata = {}
    
    except Exception:

        context.errorCatch = "OtherValue"
        errorTrials = "No"
        params.num_doctors = 0
        params.num_sdec_doctors = 0
        params.num_rat_doctors = 0
        params.num_nt_doctors = 0
        params.acuity_type = ""
        params.ed_simtype = ""
        params.sdec_Percentage = ""
        params.sdec_Percentage = ""
        params.ambulance_vs_nonambulance_Percentage = ""
        params.ac12_ambulance_Majors_vs_Resus_Percentage = ""
        params.ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_Percentage = ""
        params.a12_nonambulance_resus_vs_non_resus_Percentage = ""
        params.a3_AmbulanceMHPatient_Percentage = ""
        params.a3_NonAmbulance_MHPatient_Percentage = ""
        time_end2 = 0
        jsondata = {}
        
    if context.monte_carlo:
       output_data = {
           'acuity': time_category,
           'arrival_time': context.arrival_time,
           'discharge_time': context.time_until_discharge,
           'admission_time': context.time_until_admission
           }
       
       output = pd.DataFrame(output_data)
       return(output)
    else:
        
        # Print some of the outputs
        print('Outputs:')
        print('Total time for', params.num_doctors, 'doctors:', context.time_doctors, 'during a', str(context.time_end),
              'minute simulation, meaning an occupation rate of',
              round(context.time_doctors/context.time_end/params.num_doctors, 2))
        if params.sdec_Percentage > 0:
            print('Total time for', params.num_sdec_doctors, 'sdec_doctors:', context.time_sdec_doctors,
              'during a', str(context.time_end), 'minute simulation, meaning an occupation rate of',
              round(context.time_sdec_doctors / context.time_end / params.num_sdec_doctors, 2))        
        print('Total time for', params.num_rat_doctors, 'rat_doctors:', context.time_rat_doctors, 'during a',
              str(context.time_end), 'minute simulation, meaning an occupation rate of',
              round(context.time_rat_doctors / context.time_end / params.num_rat_doctors, 2))
        print('Total time for', params.num_nt_doctors, 'nt_doctors:', context.time_nt_doctors, 'during a',
              str(context.time_end), 'minute simulation, meaning an occupation rate of',
              round(context.time_nt_doctors / context.time_end / params.num_nt_doctors, 2))
        print('Number of people who arrived at registration:', len(left.keys()), '. Out of these,',
              sum(left.values()), 'have left')
        print('Number treated', len(waiting_time.keys()))
        print('Average waiting time', round(np.mean(list(waiting_time.values())), 2), 'min')
    
        # Build json object
        data = build_json(params.max_waiting_room, params.max_minors, params.max_majors, params.max_resus, params.max_sdec, time_category, context)
    
        # Create json data
        jsondata = json.dumps(data, cls=NpEncoder)
    
        # Waiting room
        patients_in_waiting_room, no_waiting_room, data_wr = get_room_data(context.events, 'waiting room')
        final_wr, mean_wr_occupancy = get_mean_occupancy(no_waiting_room)
    
        # Minors
        patients_in_minors, no_minors, data_minors = get_room_data(context.events, 'minors')
        final_minors, mean_minors_occupancy = get_mean_occupancy(no_minors)
    
        # Majors
        patients_in_majors, no_majors, data_majors = get_room_data(context.events, 'majors')
        final_majors, mean_majors_occupancy = get_mean_occupancy(no_majors)
    
        # Resus
        patients_in_resus, no_resus, data_resus = get_room_data(context.events, 'resus')
        final_resus, mean_resus_occupancy = get_mean_occupancy(no_resus)
    
        # Sdec
        if params.sdec_Percentage > 0:
            patients_in_sdec, no_sdec, data_sdec = get_room_data(context.events, 'sdec')
            final_sdec, mean_sdec_occupancy = get_mean_occupancy(no_sdec)
                    
        # Department
        patients_in_department, no_department, data_department = get_room_data(context.events, 'department')
        final_department, mean_department_occupancy = get_mean_occupancy(no_department)
    
        # Corridor
        patients_in_corridor, no_corridor, data_corridor = get_room_data(context.events, 'corridor')
        final_corridor, mean_corridor_occupancy = get_mean_occupancy(no_corridor)
    
        #Create an outputs folder
        if not os.path.isdir("outputs"):
            print("No outputs folder found, generating output folder")
            os.mkdir("outputs")
        
        output_dir = "outputs/"+context.scenario_name
        if os.path.isdir(output_dir):
            print("Scenario name already exists, outputs will be overwritten")
        else:
            os.mkdir(output_dir)
    
        # Run plotting_functions
        non_day1 = [key for key, value in context.arrival_time.items() if value > 24 * 60 * 1]
    
        patients_a_or_d = set(context.time_until_admission.keys()).union(set(context.time_until_discharge.keys()))
    
    
        ad_patients = pd.DataFrame()
        ad_patients['PatientID'] = [i for i in non_day1 if i in patients_a_or_d]
    
        acuities = []
        for key in ad_patients['PatientID']:
            acuities.append(time_category[key])
        ad_patients['Acuity'] = acuities
        if not context.produce_pdf:
            print("produce_pdf set to False, no PDF will be produced")
        elif len(np.unique(ad_patients['Acuity'])) < 5:
            print("PDF plot requires admission or discharge of some patients in all acuities, no pdf will be produced")
        else :
            # Generate charts
            mean_time_overall, std_time_overall, longest_time, time_until_first_doc_mean,\
                time_until_first_sdec_doc_mean, time_until_first_rat_doc_mean, time_until_first_nt_doc_mean,\
                no_left, no_interruptions_df, no_sdec_interruptions_df, no_rat_interruptions_df,\
                no_nt_interruptions_df = plotting_functions(context.arrival_time,
                                                            left, time_category, context.time_until_admission,
                                                            context.time_until_discharge, waiting_time,
                                                            context.events, params.num_doctors, params.num_sdec_doctors,
                                                            params.num_rat_doctors, params.num_nt_doctors)
    
            # Produce pdf
            pdf = producePDF.PDF()
            producePDF.produce_pdf(pdf, output_dir, params.acuity_type, params.daily_num_patients, params.num_doctors, params.num_sdec_doctors,
                                   params.num_rat_doctors, params.num_nt_doctors, params.max_resus, params.max_sdec, params.max_majors, params.max_minors,
                                   params.max_waiting_room, context.time_end,
                                   params.acuity1_perc, params.acuity2_perc, params.acuity3_perc, params.acuity4_perc, params.acuity5_perc,
                                   mean_time_overall, std_time_overall, longest_time, time_until_first_doc_mean,
                                   no_left)
    
        # Even if we don't make the pdf, can still make JSON files
        if context.produce_animation:
            corridor_room_json, waiting_room_json, majors_room_json, minors_room_json, resus_room_json, \
                sdec_room_json = generate_json(context.events)
    
    
    
        # Run visualisation function
        if context.produce_animation:
            var = sim_visualisation(params.num_doctors, params.daily_num_patients, params.acuity_type, params.ed_simtype,
                                    params.sdec_Percentage, params.ambulance_vs_nonambulance_Percentage, params.ac12_ambulance_Majors_vs_Resus_Percentage,
                                    params.ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_Percentage, params.a12_nonambulance_resus_vs_non_resus_Percentage,
                                    params.a3_AmbulanceMHPatient_Percentage, params.a3_NonAmbulance_MHPatient_Percentage,
                                    params.hospital_bed_culture, params.bed_occupancy, errorTrials, context.errorCatch, time_end2)
    
            # Write to js file
            with open("static/js/simulation_flask.js", 'w') as out_file:
                out_file.write('//#region\n')
                out_file.write('const data = %s;\n' % jsondata)
                out_file.write('//#endregion\n')
                out_file.write('//#region\n')
                out_file.write('const no_corridor = %s;\n' % corridor_room_json)
                out_file.write('//#endregion\n')
                out_file.write('//#region\n')
                out_file.write('const no_waitingroom = %s;\n' % waiting_room_json)
                out_file.write('//#endregion\n')
                out_file.write('//#region\n')
                out_file.write('const no_majors = %s;\n' % majors_room_json)
                out_file.write('//#endregion\n')
                out_file.write('//#region\n')
                out_file.write('const no_minors = %s;\n' % minors_room_json)
                out_file.write('//#endregion\n')
                out_file.write('//#region\n')
                out_file.write('const no_resus = %s;\n' % resus_room_json)
                out_file.write('//#endregion\n')
                out_file.write('//#region\n')
                out_file.write('const no_sdec = %s;\n' % sdec_room_json)
                out_file.write('//#endregion\n')
                out_file.write(var)
                
            shutil.copy("static/js/simulation_flask.js", output_dir+"/simulation_flask.js")
        else:
            print("produce_animation set to false, not producing animation")
        
        # Copy the distribution outputs, config and console log
        shutil.copy("distribution_outputs.csv", output_dir+"/distribution_outputs.csv")
        shutil.copy("config.json", output_dir+"/config.json")
        
    
