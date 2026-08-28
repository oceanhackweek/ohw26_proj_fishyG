# ohw26_proj_fishyG

Repository for the OceanHackWeek26 fishyG project

## Project fishyG

## Predicting and visualizing salmon spawning in the Strait of Georgia based on local stream conditions

## Collaborators

| Name                | Role                | Github    |
|---------------------|---------------------|---------------------|
| Zoe Crookshank      |  Data Acquisition and Initial Cleaning|https://github.com/zcrookshank |
| Linnea Goh          |  Modelling and Data Processing|https://github.com/linneagoh |
| Hannah Budroe       |  Shiny App Design and Development|https://github.com/hbudroe |



## Planning

* Initial idea: Predict and visualize salmon spawning in the Strait of Georgia based on local stream conditions
* Ideation Slide: https://docs.google.com/presentation/d/1_KLEDpLLvtKpH3awDlZRAiOKuHzbEti4CWmhEykuCG8/edit?slide=id.g3f84d57b716_31_0#slide=id.g3f84d57b716_31_0 
* Slack channel: ohw26_proj_fishyG
* Final presentation: https://docs.google.com/presentation/d/1w-ZIwuPwnJTOPN1T32VMp2RVbx90vWiTed2cLdvnsfU/edit?usp=sharing

## Background
(we <3 fish)
Pacific salmon are ecologically & culturally relevant, particularly around Vancouver & Vancouver Island; however, they are also threatened by anthropogenic climate change-related ocean warming, etc. Salmon hatch in freshwater systems, swim out to the open ocean to feed and develop as adults, and return to their birth watersheds to spawn and die. Notably, there are many salmon spawn sites located in the Strait of Georgia (between mainland and Vancouver Island), which is a generally warmer and shallower body of water compared to the larger Pacific Ocean, and generally experiences anomalous precipitation compared to other parts of Canada. When these salmon are swimming upriver/upstream to return to their spawn sites, mortality can occur due to extreme high temperatures or stranding from extremely low water flow in the watershed.

## Goals
To build a model & visualize a map predicting salmon return to several streams in the Strait of Georgia based upon current stream conditions. We have focused on 4 rivers: Nanaimo River, Qualicum River, Chemainus River, Cowichan River; and we are focused on the Fall Chinook run.
1. Build a model connecting local stream parameters (flow and temperature) as well as global parameters (temperature and precipitation) to the spawning data collected from each river.
2. Create an app that shows the locations and allows user to see older years trends as well as the models predictions for the year ahead.
Future goals would be to expand the predictions to other seasonal salmon runs, other salmon species, and other stream locations near the Strait of Georgia.

## Datasets
Salmon River arrival data:
Focusing on fall chinook runs in this area - data from NuSEDs

https://open.canada.ca/data/en/dataset/c48669a3-045b-400d-b730-48aafe8c5ee6/resource/1d343cd3-5614-3bda-814b-48a08084b051 

River flow:
https://wateroffice.ec.gc.ca/map/index_e.html?type=historical

Nanaimo riv: 08HB034 - NANAIMO RIVER NEAR CASSIDY

Little Qualicum Riv: 08HB029 - LITTLE QUALICUM RIVER NEAR QUALICUM BEACH

Chemanius Riv: 08HA001 - CHEMAINUS RIVER NEAR WESTHOLME

Cowichan Riv: 08HA011 - COWICHAN RIVER NEAR DUNCAN

Trend data:
Freshwater life-cycle timing of Pacific salmon and steelhead (Oncorhynchus spp.) in Canada paper

Data source: https://datadryad.org/dataset/doi:10.5061/dryad.wm37pvmwx

“Global” weather:
Paper: ​​https://www.mdpi.com/2306-5338/13/2/52 

Data source: https://services.pacificclimate.org/portal/gridded_observations/map/ + Daymet + NCEP North American Regional Reanalysis (NARR)

## Workflow/Roadmap
1. Retrieve environmental data for temperature, stream discharge, global weather, and salmon spawn. Note that data patchiness created issues with this step & downstream interpretations.
2. Reformat data for input into model. For the final model product, data was reformatted into a hazard table. Also calculate averages and relevant summarizations of daily data (eg. rolling 7day average of river discharge, whether flow is increasing/decreasing over 14 days)
3. Fit model. Salmon arrival (day of year [doy]) was modeled as a binomial glm : arrived ~ ns(doy, 3) + <covariates, standardised>
4. Build shiny app in R. The app includes a map layer, layers of BC temperature and precipitation, and points for all the stream sites. The 4 relevant streams were clickable & included a pop-up with information about the stream, trends since the 1960s on salmon arrival & abundance, and model results.

## Results/Findings
No clear relationship between temperature and flow for the four rivers chosen here, date currently still best predictor but this could be a limitation of the model and validation methods. 

## Lessons Learned
We have made friends with git mostly. 

## References

