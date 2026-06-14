#Libraries
import pandas as pd
import numpy as np

#Define output directory
output_dir = "outputs/"+ "mc"

#Read in monte_carlo_table
df_monte_carlo = pd.read_csv(output_dir+"/monte_carlo_table.csv")

#Relabel two columns
dict = {'Unnamed: 0': 'Run_No',
        'Unnamed: 1': 'Patient_No'}

# call rename () method
df_monte_carlo.rename(columns=dict, inplace=True)

#Create boolean
df_monte_carlo['4hr_leave'] = (df_monte_carlo['discharge_time'] < 240) | (df_monte_carlo['admission_time'] < 240)

#Filter on specific ac only
df_monte_carlo = df_monte_carlo[df_monte_carlo['acuity'] == 'acuity 5']

#Find 4 hr percentages by run number
df = 100*df_monte_carlo.groupby('Run_No')['4hr_leave'].mean()

#Print statistics
print("Mean", df.values.mean().round(2))
print("Median", np.median(df.values).round(2))
print("St.dev", df.values.std().round(2))
print("Max", df.values.max().round(2))
print("Min", df.values.min().round(2))