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
from fpdf import FPDF
import shutil
# Class PDF


class PDF(FPDF):

    def basic_table(self, headings, rows):
        for heading in headings:
            self.cell(180/len(headings), 7, heading, 1)
        self.ln()
        for row in rows:
            for col in row:
                self.cell(180/len(headings), 6, col, 1)
            self.ln()
        self.ln()

    def basic_table_acuity(self, headings, rows):
        for i, heading in enumerate(headings):
            pdf.set_font("Helvetica", size=12, style='B')
            if i == 1:
                self.set_text_color(r=227, g=26, b=28)
            elif i == 2:
                self.set_text_color(r=255, g=127, b=0)
            elif i == 3:
                self.set_text_color(r=212, g=212, b=7)
            elif i == 4:
                self.set_text_color(r=51, g=160, b=44)
            else:
                self.set_text_color(r=31, g=120, b=180)
            self.cell(180/len(headings), 7, heading, 1)
        self.ln()
        pdf.set_font("Helvetica", size=12, style='')
        self.set_text_color(r=0, g=0, b=0)
        for row in rows:
            for col in row:
                self.cell(180/len(headings), 6, col, 1)
            self.ln()
        self.ln()

    def basic_table_summary(self, headings, rows):
        for i, heading in enumerate(headings):
            if i == 0:
                self.cell(63, 7, heading, 1)
            else:
                self.cell(117/(len(headings)-1), 7, heading, 1)

            pdf.set_font("Helvetica", size=12, style='B')
            if i == 0:
                self.set_text_color(r=227, g=26, b=28)
            elif i == 1:
                self.set_text_color(r=255, g=127, b=0)
            elif i == 2:
                self.set_text_color(r=212, g=212, b=7)
            elif i == 3:
                self.set_text_color(r=51, g=160, b=44)
            else:
                self.set_text_color(r=31, g=120, b=180)

        self.ln()
        pdf.set_font("Helvetica", size=12, style='')
        self.set_text_color(r=0, g=0, b=0)
        for i, row in enumerate(rows):
            for j, col in enumerate(row):
                if j == 0:
                    self.cell(63, 6, col, 1)
                else:
                    self.cell(117/(len(headings)-1), 6, col, 1)
            self.ln()
        self.ln()

# Initialise pdf


pdf = PDF()


# Function to produce PDF
def produce_pdf(pdf, output_dir, ed_simtype, daily_num_patients, num_doctors, num_sdec_doctors, num_rat_doctors,
                num_nt_doctors, max_resus, max_sdec, max_majors, max_minors, max_waiting_room, time_end,
                acuity1_perc, acuity2_perc, acuity3_perc, acuity4_perc, acuity5_perc,
                mean_time_overall, std_time_overall, longest_time, time_until_first_doc_mean,
                no_left):

    if ed_simtype == 'Rural Trauma':
        typeED = 'Rural Trauma Centre'
    elif ed_simtype == 'Urban':
        typeED = 'Urban'
    elif ed_simtype == 'Rural':
        typeED = 'Rural'
    elif ed_simtype == 'Urban Trauma Centre':
        typeED = 'Urban Trauma Centre'
    elif ed_simtype == 'Paediatric':
        typeED = 'Paediatrics'
    elif ed_simtype == 'Custom':
        typeED = 'Custom'
    else:
        typeED = 'Standard ED'

    # Add a page
    pdf.add_page()

    # Set style and size of font that you want in the pdf
    pdf.set_font("Helvetica", size=15, style='B')

    # Create a cell
    pdf.cell(200, 20, txt="Emergency Department Simulator", ln=1, align='L')
    pdf.set_font("Helvetica", size=12, style='B')

    # Create a cell
    pdf.cell(200, 5, txt="Setup", ln=2, align='L')
    pdf.set_font("Helvetica", size=12, style='')

    # Create a cell
    pdf.cell(200, 5, txt="Type of ED: " + typeED, ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="Daily Attendance = " + str(daily_num_patients) + ' patients', ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="Number of doctors = " + str(num_doctors) + " doctors", ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="Number of sdec_doctors = " + str(num_sdec_doctors) + " sdec_doctors",
             ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="Number of rat_doctors = " + str(num_rat_doctors) + " rat_doctors",
             ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="Number of nt_doctors = " + str(num_nt_doctors) + " nt_doctors",
             ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="Resus cubicles = " + str(max_resus) + " cubicles", ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="SDEC cubicles = " + str(max_sdec) + " cubicles", ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="Majors cubicles = " + str(max_majors) + " cubicles", ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="Minors cubicles  = " + str(max_minors) + " cubicles", ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="Waiting room capacity = " + str(max_waiting_room) + " seats", ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="Days to run simulation = " + str(time_end//1440) + " days", ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="", ln=2, align='L')

    # Set font size
    pdf.set_font(family='Helvetica', style='B')

    # Create a cell
    pdf.cell(200, 5, txt="Number of incoming patients / patients in the ED and distribution throughout the day",
             ln=2, align='L')

    # Set font size
    pdf.set_font(family='Helvetica', style='')

    # Create a cell
    pdf.cell(200, 5, txt="", ln=2, align='L')
    col_names = ["", "Acuity 1", "Acuity 2", "Acuity 3", "Acuity 4", "Acuity 5"]
    data = [["Percentage", str(acuity1_perc) + '%', str(acuity2_perc) + '%', str(acuity3_perc) + '%', str(acuity4_perc)
             + '%', str(acuity5_perc) + '%'],
            ["Daily number", str(round(acuity1_perc/100*daily_num_patients)),
             str(round(acuity2_perc/100*daily_num_patients)), str(round(acuity3_perc/100*daily_num_patients)),
             str(round(acuity4_perc/100*daily_num_patients)), str(round(acuity5_perc/100*daily_num_patients))]]

    # Add table
    pdf.basic_table_acuity(col_names, data)

    # Add figure 1
    pdf.image('NumPatients_PerDay.png',  w=200)

    # Add figure 2
    pdf.image('MeanOccupancy_per_room.png',  w=200)

    # Add figure 3
    pdf.image('MeanOccupancy_per_acuity.png',  w=200)

    # Set font size
    pdf.set_font(family='Helvetica', style='B')

    # Create a cell
    pdf.cell(200, 5, txt="", ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="Main metrics regarding time spent in the department depending on acuity", ln=2, align='L')

    # Create a cell
    pdf.cell(200, 5, txt="", ln=2, align='L')
    col_names = ["", "Acuity 1", "Acuity 2", "Acuity 3", "Acuity 4", "Acuity 5"]
    data = [["Mean time ± std", str(int(round(mean_time_overall['acuity 1']))) + '±' +
             str(int(round(std_time_overall['acuity 1']))), str(int(round(mean_time_overall['acuity 2']))) + '±' +
             str(int(round(std_time_overall['acuity 2']))), str(int(round(mean_time_overall['acuity 3']))) + '±' +
             str(int(round(std_time_overall['acuity 3']))), str(int(round(mean_time_overall['acuity 4']))) + '±' +
             str(int(round(std_time_overall['acuity 4']))), str(int(round(mean_time_overall['acuity 5']))) + '±' +
             str(int(round(std_time_overall['acuity 5'])))],
            ["Longest time", str(int(round(longest_time['acuity 1']))), str(int(round(longest_time['acuity 2']))),
             str(int(round(longest_time['acuity 3']))), str(int(round(longest_time['acuity 4']))),
             str(int(round(longest_time['acuity 5'])))],
            ["Time to see doctor - mean ± std", str(int(round(time_until_first_doc_mean['Time (min)'].values[0]))) +
             '±' + str(int(round(time_until_first_doc_mean['Std'].values[0]))),
             str(int(round(time_until_first_doc_mean['Time (min)'].values[1]))) +
             '±' + str(int(round(time_until_first_doc_mean['Std'].values[1]))),
             str(int(round(time_until_first_doc_mean['Time (min)'].values[2]))) +
             '±' + str(int(round(time_until_first_doc_mean['Std'].values[2]))),
             str(int(round(time_until_first_doc_mean['Time (min)'].values[3]))) +
             '±' + str(int(round(time_until_first_doc_mean['Std'].values[3]))),
             str(int(round(time_until_first_doc_mean['Time (min)'].values[4]))) +
             '±' + str(int(round(time_until_first_doc_mean['Std'].values[4])))],
            ["Mean number left / day", str(int(round(no_left['acuity 1']))), str(int(round(no_left['acuity 2']))),
             str(int(round(no_left['acuity 3']))), str(int(round(no_left['acuity 4']))),
             str(int(round(no_left['acuity 5'])))]]
    pdf.set_font(family='Helvetica', style='')

    # Add table
    pdf.basic_table_summary(col_names, data)
    # Create a cell
    pdf.cell(200, 20, txt="", ln=2, align='L')

    # Add figure 4
    pdf.image('MeanTime_Stacked.png', w=200)

    # Add figure 5
    pdf.image('MeanTime_MultipleBarCharts.png', w=200)
    pdf.set_font(family='Helvetica', style='B')

    # Create cell
    pdf.cell(200, 5, txt="Percentage of admitted and discharged patients as a function of the time spent in ED",
             ln=2, align='L')

    # Add figure 6
    pdf.image('TimeInDept_Acuity.png',  w=200)

    # Write config file to pdf
    pdf.add_page()
    pdf.multi_cell(w=210, h=6, txt='List of model input parameters:', border=0, align='L', fill=False)

    # Function to get config.json file information for printing at end of pdf

    def get_file_content():
        text = ""
        with open('config.json') as f:
            for line in f:
                text += line
        return text

    # Add config file to pdf
    text = get_file_content()
    pdf.multi_cell(w=210, h=6, txt=text, border=0, align='L', fill=False)

    # Save the pdf with name .pdf
    pdf_dir = output_dir+"/simulation_report.pdf"
    pdf.output(pdf_dir)

    # Copy the pdf to old location so UI can find it (workaround until we implement scenario control into the UI)
    shutil.copy(pdf_dir, "./static/js/ED_Simulator.pdf")
