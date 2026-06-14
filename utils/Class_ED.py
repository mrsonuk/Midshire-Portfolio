# Define class ED

# Imports
import simpy
import random
import json


# Create class ED
class ED(object):

    # Initialise
    def __init__(self, env, num_doctors, num_sdec_doctors, num_rat_doctors, num_nt_doctors,
                 max_resus, max_sdec, max_majors, max_minors, max_waiting_room):
        self.env = env
        self.doctors = simpy.PreemptiveResource(env, num_doctors)
        self.sdec_doctors = simpy.PreemptiveResource(env, num_sdec_doctors)
        self.rat_doctors = simpy.PreemptiveResource(env, num_rat_doctors)
        self.nt_doctors = simpy.PreemptiveResource(env, num_nt_doctors)
        self.resus = simpy.Container(env, max_resus, init=max_resus)
        self.sdec = simpy.Container(env, max_sdec, init=max_sdec)
        self.majors = simpy.Container(env, max_majors, init=max_majors)
        self.minors = simpy.Container(env, max_minors, init=max_minors)
        self.waiting_room = simpy.Container(env, max_waiting_room, init=max_waiting_room)

    # Method for performing assessment
    def doctor_performs_assessment(self, patient, time_category):
        yield self.env.timeout(time_category)

    # Method for performing CT
    def patient_performs_CT(self, patient, time_CT):
        yield self.env.timeout(time_CT)

    # Method for performing x-ray
    def patient_performs_XRay(self, patient, time_XRay):
        yield self.env.timeout(time_XRay)

    # Method for performing blood test
    def patient_performs_blood(self, patient, time_blood):
        yield self.env.timeout(time_blood)

    # Method for performing diagnosis, treatment and discharge
    def doctor_performs_DTD(self, patient, time_DTD):  # group together diagnosis, treatment and discharge
        yield self.env.timeout(time_DTD)

    # Method for performing combined assessment, diagnosis, treatment, and discharge.
    # This is useful for when patient has no diagnostics.
    def doctor_performs_ADTD(self, patient, time_ADTD):
        yield self.env.timeout(time_ADTD)

    # Method for performing registration
    def patient_performs_registration(self, patient, acuity):

        #Parameters in config file
        with open("config.json") as file:
            config = json.load(file)

        # Read in times for registration (these depend on acuity).
        time = config['Registration_Times'].get(acuity)

        yield self.env.timeout(time)

    # Function for admitting patient. This depends on both time to be accepted by team,
    # movement time, and time to subsequently get a bed.
    def admit_patient(self, patient, acuity, target, got_sdec_boolean, context, env):

        # Starting admission process
        context.events[patient].append(('Started admission', env.now))

        # Compute admission time. Not this is just the decision time to decide if patient is to be admitted.
        time_admit = random.gauss(context.mean_target, context.std_target)
        while time_admit < 0:
            time_admit = random.gauss(context.mean_target, context.std_target)

        # Get accepted by the team
        yield self.env.timeout(time_admit)
        context.events[patient].append(('Got accepted by team', env.now))

        # Compute time to get bed in hospital
        time_bed = random.gauss(context.mean_bed, context.std_bed)
        while time_bed < 0:
            time_bed = random.gauss(context.mean_bed, context.std_bed)

        # Some movement time
        yield self.env.timeout(2 * context.movement_time)

        # Add time to get bed in hospital
        yield self.env.timeout(time_bed)
        context.events[patient].append(('Got bed in hospital', env.now))

        # If went through sdec do not record time_until_admission
        if got_sdec_boolean == False:
            context.time_until_admission[patient] = env.now - context.arrival_time[patient]

        context.events[patient].append(('Finished admission', env.now))

    # Function for discharging a patient.

    def discharge_patient(self, patient, got_sdec_boolean, context, env):

        # Starting discharge process
        context.events[patient].append(('Started discharge', env.now))

        with open("config.json") as file:
            config = json.load(file)

        mean_time_to_exit = config["Time_to_Exit"]["mean"]
        stdev_time_to_exit = config["Time_to_Exit"]["stdev"]

        # Find discharge time
        time_to_exit = random.gauss(mean_time_to_exit, stdev_time_to_exit)
        while time_to_exit < 0:
            time_to_exit = random.gauss(mean_time_to_exit, stdev_time_to_exit)

        # Add discharge time
        yield self.env.timeout(time_to_exit)

        # If went through sdec do not record time_until_discharge
        if got_sdec_boolean == False:
            context.time_until_discharge[patient] = env.now - context.arrival_time[patient]

        # Finish discharge
        context.events[patient].append(('Finished discharge', env.now))

    # Function for admitting or discharging a patient. This is a random choice, weighted by the acuity.
    # You are more likely to be admitted if you are acuity 1 than 5.
    def run_discharge_or_admit(self, patient, acuity, target, got_sdec_boolean, context, env):

        with open("config.json") as file:
            config = json.load(file)

        prob_admission = config["Prob_Admission"].get(acuity)

        admit = random.choices([True, False], weights=(prob_admission, 1 - prob_admission), k=1)[0]

        if admit:
            yield env.process(self.admit_patient(patient, acuity, target, got_sdec_boolean, context, env))
        else:
            yield env.process(self.discharge_patient(patient, got_sdec_boolean, context, env))

        # Write event log to file for those patients admitted or discharged. This event log can be
        # used by process_mapping.R when validating the model.
        if not context.monte_carlo:
            f = open("distribution_outputs.csv", "a")
            f.write(str(context.events[patient]) + "\n")
            f.close()
