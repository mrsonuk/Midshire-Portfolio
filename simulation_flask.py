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

# Imports
from __future__ import print_function
from simulationFlaskED import run
from flask import Flask, render_template, request
app = Flask(__name__)
import numpy as np
from utils.inputs import read_parameters

# Define class object to pass around information through functions, as opposed to previous method
# of assigning global variables
# The scenario name for users of UI for now is generic so it will alway overwrite itself, unless made unique.

#Sophie testing code.
class Object_global(object):
    def __init__(self):
        self.scenario_name = "UI_Trial"
        self.produce_animation = True
        self.produce_pdf = True
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


# Define get, post methods
@app.route("/", methods=['GET', 'POST'])
def home():
    if request.method == "POST":
        acType = request.form.get("acType")
        edType = request.form.get("edType")
        hospitalbedCulture = request.form.get("hospitalbedCulture")
        bedOccupancy = request.form.get("bedOccupancy")
        params = read_parameters(acType, edType, hospitalbedCulture, bedOccupancy)
        run(params, context)
    return render_template("simulation_display_flask.html")

# When running main, run app


if __name__ == "__main__":
    app.run()
