# Imports
import json
import random


# Function to check acuity percentages have been provided in config file


def parse_config_acuity():

    with open("config.json") as file:
        config = json.load(file)
    
    out = [config["Acuity_Percentages"][f"Acuity {number}"] for number in range(1, 6)]

    # If values incorrect throw error
    if not all(val >= 0 for val in out):
        raise ValueError('Invalid acuity percentages')
    
    return out

# Function to check if simulation parameters, such as number of patients, numbers of doctors,
# maximum capacity of rooms, etc. have been provided in config file

def parse_config_simtype():

    with open("config.json") as file:
        config = json.load(file)

    sim_parameters = config['Sim_Parameters']

    out = [sim_parameters["daily_num_patients"],
           sim_parameters["num_doctors"],
           sim_parameters["num_sdec_doctors"],
           sim_parameters["num_rat_doctors"],
           sim_parameters["num_nt_doctors"],
           sim_parameters["max_resus"],
           sim_parameters["max_sdec"],
           sim_parameters["max_majors"],
           sim_parameters["max_minors"],
           sim_parameters["max_waiting_room"]]

    # If values incorrect throw error
    if not all(val > 0 for val in out):
        raise ValueError('Invalid simtype parameters')
    return out


# Function to check if other simulation parameters have been provided. These parameters are specific to
# different pathway arms, such as opening and closing hour of the sdec
def parse_config_Sim_Parameters():

    with open("config.json") as file:
        config = json.load(file)

    # Listing all parameters to check
    config_Sim_Parameters = ['sdec_Percentage',
                             'ambulance_vs_nonambulance_Percentage',
                             'ac12_ambulance_Majors_vs_Resus_Percentage',
                             'ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_Percentage',
                             'a12_nonambulance_resus_vs_non_resus_Percentage',
                             'a3_AmbulanceMHPatient_Percentage',
                             'a3_NonAmbulance_MHPatient_Percentage',
                             'sdec_opening_hour',
                             'sdec_closing_hour']
    
    # Check if all parameters are empty or negative and if so throw error
    if any(config['Sim_Parameters'][p] < 0 for p in config_Sim_Parameters):
        raise ValueError('Invalid config_Sim_Parameters')
    
    return [config['Sim_Parameters'][p] for p in config_Sim_Parameters]

# Function to get EDtype parameters

# Main function for getting ED type parameters either from config or non-config files.
# It obtains the pathway parameters and acuity percentages


def get_EDtype_parameters(acuity_type):

    # Get pathway parameters from config file
    sdec_Percentage, ambulance_vs_nonambulance_Percentage, ac12_ambulance_Majors_vs_Resus_Percentage, \
        ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_Percentage, a12_nonambulance_resus_vs_non_resus_Percentage, \
        a3_AmbulanceMHPatient_Percentage, a3_NonAmbulance_MHPatient_Percentage, sdec_opening_hour, \
        sdec_closing_hour = parse_config_Sim_Parameters()

    # If "Custom" type, read in acuity parameters from config.json
    if acuity_type == "Custom":
        acuity1_perc, acuity2_perc, acuity3_perc, acuity4_perc, acuity5_perc = parse_config_acuity()
    
    # This assumes that the names in config_EDtypes.json are the same that will be passed to acuity_type
    # If not, it will use "Standard" parameters
    else:
        with open("config_EDtypes.json") as file:
            config_edtypes = json.load(file)
        
        if acuity_type in config_edtypes:
            acuity_perc = config_edtypes[acuity_type]
        
        else:
            acuity_perc = config_edtypes['Standard']

        acuity1_perc, acuity2_perc, acuity3_perc, acuity4_perc, acuity5_perc = acuity_perc.values()
    
    
    return acuity1_perc, acuity2_perc, acuity3_perc, acuity4_perc, acuity5_perc, \
        sdec_Percentage, ambulance_vs_nonambulance_Percentage, ac12_ambulance_Majors_vs_Resus_Percentage, \
        ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_Percentage, a12_nonambulance_resus_vs_non_resus_Percentage, \
        a3_AmbulanceMHPatient_Percentage, a3_NonAmbulance_MHPatient_Percentage, sdec_opening_hour, sdec_closing_hour

# Function to get EDsize parameters from config or non-config files


def get_EDsize_parameters(ed_simtype):

    # if "Custom" type, read in parameters from config.json
    if ed_simtype == "Custom":
        daily_num_patients, num_doctors, num_sdec_doctors, num_rat_doctors, num_nt_doctors, max_resus, max_sdec, \
            max_majors, max_minors, max_waiting_room = parse_config_simtype()
    
    # this assumes that the names in config_EDsizes.json are the same that will be passed to acuity_type
    # if not, it will use "Small" parameters
    else:
        with open("config_EDsizes.json") as file:
            config_edsizes = json.load(file)
        
        if ed_simtype in config_edsizes:
            simtype_params = config_edsizes[ed_simtype]
        
        else:
            simtype_params = config_edsizes['Standard']  

        daily_num_patients, num_doctors, num_sdec_doctors, num_rat_doctors, num_nt_doctors, max_resus, max_sdec, \
            max_majors, max_minors, max_waiting_room = simtype_params.values()
    
    return daily_num_patients, num_doctors, num_sdec_doctors, num_rat_doctors, num_nt_doctors, max_resus, max_sdec, \
        max_majors, max_minors, max_waiting_room


# Function to get target time from config file. Note that W and S have the same parameters now.-
# Hospital culture has no effect.


def get_target_time(use_target):

    with open("config.json") as file:
        config = json.load(file)
    
    if use_target == "W" or use_target == "Weak":
        try:
            mean_target = config["Target_Parameters"]["W"]["mean_target"]
            std_target = config["Target_Parameters"]["W"]["std_target"]
            target = False
        except:
            mean_target = config["Target_Parameters_Default_Values"]["W"]["mean_target"]
            std_target = config["Target_Parameters_Default_Values"]["W"]["std_target"]
            target = False
    
    elif use_target == "S" or use_target == "Strong":
        try:
            mean_target = config["Target_Parameters"]["S"]["mean_target"]
            std_target = config["Target_Parameters"]["S"]["std_target"]
            target = True
        except:
            mean_target = config["Target_Parameters_Default_Values"]["S"]["mean_target"]
            std_target = config["Target_Parameters_Default_Values"]["S"]["std_target"]
            target = True


    # This is redundant at the moment - there is a need to decide what the default option is were target not == W
    else:
        try:
            mean_target = config["Target_Parameters"]["S"]["mean_target"]
            std_target = config["Target_Parameters"]["S"]["std_target"]
            target = True
        except:
            mean_target = config["Target_Parameters_Default_Values"]["S"]["mean_target"]
            std_target = config["Target_Parameters_Default_Values"]["S"]["std_target"]
            target = True

    # If values incorrect throw error
    if mean_target < 0 or std_target < 0:
        raise ValueError
    
    return target, mean_target, std_target


# Function to get bed occupancy from config file
def parse_bed_occupancy(bed_occupancy):

    # Initial transformation
    bed_occupancy = str(bed_occupancy)

    # Start to read from config file
    with open("config.json") as file:
        config = json.load(file)

    # If data present extract it.
    if bed_occupancy in config["Bed_Occupancy"]:
        try:
            mean_bed = config["Bed_Occupancy"][bed_occupancy]['mean_bed']
            std_bed = config["Bed_Occupancy"][bed_occupancy]['std_bed']
        except:
            mean_bed = config["Bed_Occupancy_Default_Values"][bed_occupancy]['mean_bed']
            std_bed = config["Bed_Occupancy_Default_Values"][bed_occupancy]['std_bed']

    # If data not there then throw error
    else:
        return 'Please introduce a valid value for bed occupancy'
    
    print(f"General Acute Bed occupancy in the previous 24 hours: less than {bed_occupancy}%")
    return mean_bed, std_bed


# Function to get assessment, treatment and discharge times by acuity from config file
def get_doctor_times(acuity):

    with open("config.json") as file:
        config = json.load(file)

    # Create dictionary of parameters to return (and subparameters like mean and stdev)
    if acuity in config["Doctor_Times"]:
        doctor_params = {
            'time_assess_nt': ['mean', 'stdev'],
            'time_assess_rat': ['mean', 'stdev'],
            'time_wait_mh': None,
            'time_assess': None,
            'time_treat': None,
            'time_discharge': ['mean', 'stdev']
        }

        if any(p not in config["Doctor_Times"][acuity] for p in doctor_params.keys()):
            raise ValueError('Please introduce a valid value for assessment, diagnosis and treatment times')
        # Fill a dictionary with the values - sampling from truncated normal if there is mean/stdev
        doctor_times = {}
        for param, subparam in doctor_params.items():
            if subparam is None:
                doctor_times[param] = config["Doctor_Times"][acuity][param]
            else:
                mean = config["Doctor_Times"][acuity][param]['mean']
                stdev = config["Doctor_Times"][acuity][param]['stdev']
                # This samples from a truncated normal so there are no negative values
                time = random.gauss(mean, stdev)
                while time < 0:
                    time = random.gauss(mean, stdev)
                doctor_times[param] = time
        
        return tuple(doctor_times.values())
    
    else:
        return 'Please enter a valid value for acuity'
        

# Get diagnostic percentages from config file by acuity
def get_diagnostic_percentages(acuity):

    with open("config.json") as file:
        config = json.load(file)

    # If data there then extract it
    if acuity in config["Diagnostic_Tests"]:

        CT_percentage = config["Diagnostic_Tests"][acuity]['ct_percentage']
        XRay_percentage = config["Diagnostic_Tests"][acuity]['XRay_percentage']
        blood_percentage = config["Diagnostic_Tests"][acuity]['blood_percentage']

    # Else if data not here then throw error
    else:
        return 'Please introduce a valid value for diagnostic test percentages'
    
    return CT_percentage, XRay_percentage, blood_percentage


# Get diagnostic times by acuity
# TODO JIC: this could be simplified following get_doctor_times_above
def get_diagnostic_times(acuity):

    with open("config.json") as file:
        config = json.load(file)

    # If data there then extract it
    if acuity in config["Diagnostic_Tests"]:

        mean_time_ct = config["Diagnostic_Tests"][acuity]['time_ct_mean']
        stdev_time_ct = config["Diagnostic_Tests"][acuity]['time_ct_stdev']

        mean_time_XRay = config["Diagnostic_Tests"][acuity]['time_XRay_mean']
        stdev_time_XRay = config["Diagnostic_Tests"][acuity]['time_XRay_stdev']

        mean_time_blood = config["Diagnostic_Tests"][acuity]['time_blood_mean']
        stdev_time_blood = config["Diagnostic_Tests"][acuity]['time_blood_stdev']

    # Else if data not there then throw error
    else:
        return 'Please introduce a valid value for diagnostic test times'
    
    time_CT = random.gauss(mean_time_ct, stdev_time_ct)
    while time_CT < 0:
        time_CT = random.gauss(mean_time_ct, stdev_time_ct)

    time_XRay = random.gauss(mean_time_XRay, stdev_time_XRay)
    while time_XRay < 0:
        time_XRay = random.gauss(mean_time_XRay, stdev_time_XRay)

    time_blood = random.gauss(mean_time_blood, stdev_time_blood)
    while time_blood < 0:
        time_blood = random.gauss(mean_time_blood, stdev_time_blood)

    return time_CT, time_XRay, time_blood



def read_parameters(ac_type, edSimType, hospitalbedCulture, bedOccupancy):
    class object_parameters(object):
         # Read in acuity, x-ray/CT percentages and percentages which inform the relative contribution
         # of PAH added arms (Triage nurse, RAT, etc.)
         acuity1_perc, acuity2_perc, acuity3_perc, acuity4_perc, acuity5_perc, \
             sdec_Percentage, ambulance_vs_nonambulance_Percentage, ac12_ambulance_Majors_vs_Resus_Percentage, \
             ac12_nonambulanceNonResus_MajorsDirect_Vs_WR_Percentage, a12_nonambulance_resus_vs_non_resus_Percentage, \
             a3_AmbulanceMHPatient_Percentage, \
             a3_NonAmbulance_MHPatient_Percentage, sdec_opening_hour, sdec_closing_hour = \
             get_EDtype_parameters(ac_type)
             
         # Read in daily number of patients, number of doctors, and capacity of resus, majors, minors, waiting room
         daily_num_patients, num_doctors, num_sdec_doctors, num_rat_doctors, num_nt_doctors, max_resus, max_sdec, \
             max_majors, max_minors, max_waiting_room = get_EDsize_parameters(edSimType)
         
         # Is ED strong/weak hospital culture for admission
         hospital_bed_culture = hospitalbedCulture
         ed_simtype = edSimType
    
         # Previous bed occupancy in last 24 hours
         bed_occupancy = bedOccupancy
         acuity_type = ac_type
         # target = Boolean (True or False, here); mean_/std_target: mean/std time under admission
         target, mean_target, std_target = get_target_time(hospital_bed_culture)
    
         # Mean/Std percentage bed occupancy in previous 24 hours
         mean_bed, std_bed = parse_bed_occupancy(bed_occupancy)

    return(object_parameters())






