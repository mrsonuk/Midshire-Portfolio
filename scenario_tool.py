# Scenario tool for analytical users. Choose parameters in config.json in the main directory,
# set the scenario name here.
# The user can decide whether to generate the pdf and json animation file

# Imports
from simulationFlaskED import run
import numpy as np
import os
from utils.inputs import read_parameters
#sophie test 2
# Variables to decide outputs
scenario_name = "Check"
overwrite_scenario = True
produce_animation = True
produce_pdf = True

# Scenario name
if not overwrite_scenario:
    new_name = scenario_name
    i = 1
    while os.path.isdir("outputs/"+new_name):
        new_name = scenario_name + str(i)
        i += 1
    scenario_name = new_name
    

# Define class object to pass around information through functions, as opposed to previous method
# of assigning global variables
class Object_global(object):
    def __init__(self):
        self.scenario_name = scenario_name
        self.produce_animation = produce_animation
        self.produce_pdf = produce_pdf
        self.monte_carlo = False
        self.movement_time = 2
        self.time_end = 24*60*14.5
        self.walk_to_exit = 5
        self.mean_bed = 0
        self.std_bed = 0
        self.mean_target = 0
        self.std_target = 0
        self.number_registered = 0
        self.time_doctors = 0
        self.time_sdec_doctors = 0
        self.time_rat_doctors = 0
        self.time_nt_doctors = 0
        self.timeLeft = {}
        self.arrival_time = {}
        self.priority = {}
        self.events = {}
        self.wr_seats = np.zeros(2)
        self.minors_seats = np.zeros(2)
        self.resus_seats = np.zeros(2)
        self.sdec_seats = np.zeros(2)
        self.majors_seats = np.zeros(2)
        self.doctors = np.zeros(2)
        self.sdec_doctors = np.zeros(2)
        self.rat_doctors = np.zeros(2)
        self.nt_doctors = np.zeros(2)
        self.doctors_list = []
        self.sdec_doctors_list = []
        self.rat_doctors_list = []
        self.nt_doctors_list = []
        self.time_until_admission = {}
        self.time_until_discharge = {}
        self.number_treated_init = 0
        self.errorCatch = ""
        self.sdec_boolean_patient = False
        self.ambulance_vs_nonambulance_boolean = False
        self.ac12_ambulance_Majors_vs_Resus_boolean = False
        self.ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_boolean = False
        self.a12_nonambulance_resus_vs_non_resus_boolean = False
        self.a3_AmbulanceMHPatient_boolean = False
        self.a3_NonAmbulance_MHPatient_boolean = False


# Intialise context object
context = Object_global()

# Run simulation
params = read_parameters("Custom", "Custom", "Custom", "95")
run(params, context)
