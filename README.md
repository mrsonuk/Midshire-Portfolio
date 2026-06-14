# UEC Feature list

## Important notes
- The functionality for hospital culture (i.e. hospital culture influencing time to admit) is currently disabled. Choosing hospital culture W/S will give the same result (= the parameters set in the config.json)
- The functionality for bed occupancy influencing time to get a bed is currently disabled. Choosing any option for bed occupancy will give the same result ( = the parameters set in the config.json)

## Priority list

[ ] Explore variability of simulations. This would require Monte-Carlo modelling.

[ ] Include stdevs in time calculations (e.g. time_assess, time to diagnostics) - need to get distributions from data to inform distributions.

[ ] Transfer the model to different hospitals. To prevent overfitting, we suggest a) looking for process map similarities across multiple hospitals, b) treating the model more like a machine learning problem where there is clear training, validation, test sets/metrics and avoiding data leakage.

[ ] Introduce the role of the human efficiency factor into the model. 

[ ] Further QA of model, including potentially through unit tests, validation of all parameters, validation of final modelled process map, additional metric validation, etc. 

[ ] Get list of occupancy of rooms (i.e. average occupancy of waiting room, majors etc) and resource use (doctors) as an easy to read output.

[ X ] Turn off SDEC completely. 

[ ] Better parametrise acuity 3 MH delay time in Majors - this could be informed by PAH data, if provided.  

## Longer term tasks (see below Misc and Model functionality)

## Misc

[ ] Decide if health economics modelling is to be incorporated. 

## Model functionality

[ ] XRay and CTScan should potentially be in rooms where you wait for a resource (machine) to be free (i.e. similar to doctors and waiting/treatment rooms).

[ ] Open animations from past runs in the UI.

[ ] Increase scenario functionality in the UI.

[ ] Reload model environment and variables.

[ ] Way of preloading simulations.

## Visuals

[ ] Separate XRay and CTScan; and add in Bloods.

[ ] Change logos and title.




