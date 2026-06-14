#Remove all variables
rm(list = ls())

#Please ensure that that the working directory is set to the file source location

###1
#Import libraries
library(dplyr)
library(bupaR)
library(processmapR)
library(ggplot2)
library("ggpubr")
#Printing options
options(repr.matrix.max.rows=50000, repr.matrix.max.cols=200)
###2
#Read in data
df <- readLines("distribution_outputs.csv")

output_df <- data.frame()
#Process each line
for (i in 1:length(df)) {
  print(i)
  line <- gsub("\\[|\\]", "", df[i])
  line <- gsub("^\\(","", line)
  line <- gsub("\\)$","", line)
  line <- gsub("\\'", "", line)
  line <- gsub("\\, \\(", "", line)
  patient_events <- unlist(strsplit(line,'\\)'))
  #Get acuity value
  patient <- i
  acuity <- gsub('.* acuity','acuity',patient_events[1])
  acuity <- gsub(' ','', acuity)
  #Loop through list just taking the first two elements
  #(ie the name of the event and the time)
  for (event in patient_events){
    event <- unlist(strsplit(event, ','))
    event_name <- gsub(' ', '', event[1])
    event_time <- as.numeric(event[2])
    output_df <- rbind(output_df, data.frame(patient = patient,
                                             acuity = acuity,
                                             activity = event_name,
                                             time = event_time))
  }
  
  
}
df_final <- output_df


###7
#Calculate time in department for non-sdec patients per acuity per patient. 
df_final %>% 
  filter(acuity =='acuity1') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(mean_time_in_department = ifelse((any(activity=='Finishedadmission') | any(activity=='Finisheddischarge')), max(as.numeric(time)) - as.numeric(time[activity == 'Arrived']), NA)) %>%
  filter(row_number()==1) -> df_time_in_department

#Calculate mean, max, and stdev times
mean_time = mean(df_time_in_department$mean_time_in_department, na.rm=TRUE)
print(mean_time)

max_time = max(df_time_in_department$mean_time_in_department, na.rm=TRUE)
print(max_time)

stdev_time = sd(df_time_in_department$mean_time_in_department, na.rm=TRUE)
print(stdev_time)

###8
#Calculate percentage who are admitted or discharged < 4 hr or > 12 hr time. Excluding SDEC patients. This can be filtered by acuity. 
df_final %>% 
  filter(acuity =='acuity2') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(A_and_D_Number = ifelse((any(activity=='Finishedadmission') | any(activity=='Finisheddischarge')) & (max(as.numeric(time)) - as.numeric(time[activity == 'Arrived']) < 240) , 1, 0)) %>%
  filter(row_number()==1) -> df_admissions_and_discharges

#Percentage admitted or discharged before 4 hours
print("Percentage of released before 4 hours")
print(100*sum(df_admissions_and_discharges$A_and_D_Number)/nrow(df_admissions_and_discharges))

#Calculate percentage of non-sdec patients who are admitted or discharged within x time. THE EXAMPLE SHOW is for 12 hours
df_final %>% 
  filter(acuity =='acuity2') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(A_and_D_Number = ifelse((any(activity=='Finishedadmission') | any(activity=='Finisheddischarge')) & (max(as.numeric(time)) - as.numeric(time[activity == 'Arrived']) > 720) , 1, 0)) %>%
  filter(row_number()==1) -> df_admissions_and_discharges


#Percentage admitted or discharged after 12 hours
print("Percentage of people released after 12 hours")
print(100*sum(df_admissions_and_discharges$A_and_D_Number)/nrow(df_admissions_and_discharges))

###9
#Draw graphs - Time to assess. One subplot per acuity. Note this is not strictly time to assess, but time to first generic doctor.
df_final %>% 
  filter(acuity =='acuity1') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Requesteddoctor'), as.numeric(time[activity=='Requesteddoctor'][1]) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  #scale_y_continuous(breaks = seq(0,1000,100)) +
  ggtitle("Acuity 1") +labs(x = "Time to assess", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f1_assess

df_final %>% 
  filter(acuity =='acuity2') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Requesteddoctor'), as.numeric(time[activity=='Requesteddoctor'][1]) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  #scale_y_continuous(breaks = seq(0,1000,100)) +
  ggtitle("Acuity 2") +labs(x = "Time to assess", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f2_assess

df_final %>% 
  filter(acuity =='acuity3') %>%
  filter(!any(activity=='Gotsdec')) %>%
  group_by(patient)%>%
  mutate(Diff = ifelse(any(activity=='Requesteddoctor'), as.numeric(time[activity=='Requesteddoctor'][1]) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  #scale_y_continuous(breaks = seq(0,1000,100)) +
  ggtitle("Acuity 3") +labs(x = "Time to assess", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f3_assess

df_final %>% 
  filter(acuity =='acuity4') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Requesteddoctor'), as.numeric(time[activity=='Requesteddoctor'][1]) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  #scale_y_continuous(breaks = seq(0,1000,100)) +
  ggtitle("Acuity 4") +labs(x = "Time to assess", y = "Patients") +
  theme(legend.position="none") +
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f4_assess

df_final %>% 
  filter(acuity =='acuity5') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Requesteddoctor'), as.numeric(time[activity=='Requesteddoctor'][1]) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  #scale_y_continuous(breaks = seq(0,1000,100)) +
  ggtitle("Acuity 5") +labs(x = "Time to assess", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f5_assess

ggarrange(f1_assess, f2_assess, f3_assess, f4_assess, f5_assess,
          labels = c("A", "B", "C", "D", "E"),
          ncol = 2, nrow = 3)

###10
#Draw graphs - Starting treatment - taking first treatment (i.e. requested doctor) after assessment (i.e. after first released doctor). Again, there will be a small error since Requested doctor won't quite equal finished DTD time. 
df_final$firstTreatment <- 0 #create another column for the first treatment
for (pat in 1:df_final$patient[length(as.numeric(df_final$patient))]){
  reld <- which(df_final$activity == 'Releaseddoctor' & df_final$patient == pat)
  first_reld <- reld[1]
  reqdAfterReld <- which(df_final$patient == pat & df_final$activity=='Requesteddoctor' & as.numeric(df_final$time) > as.numeric(df_final$time[first_reld]))
  first_reqdAfterReld <- reqdAfterReld[1]
  df_final$firstTreatment[first_reqdAfterReld] <- 1
}

df_final %>% 
  filter(acuity =='acuity1') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Requesteddoctor'), as.numeric(time[firstTreatment==1]) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 1") + labs(x = "Time of first treatment", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  scale_x_continuous(breaks = seq(0,600,100)) +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=500),
            vjust=-1,col='black',size=3)   -> f1_treatment

df_final %>% 
  filter(acuity =='acuity2') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Requesteddoctor'), as.numeric(time[firstTreatment==1]) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 2") + labs(x = "Time of first treatment", y = "Patients") +
  theme(legend.position="none") +
  theme_light() +
  scale_x_continuous(breaks = seq(0,600,100)) +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=500),
            vjust=-1,col='black',size=3) -> f2_treatment

df_final %>% 
  filter(acuity =='acuity3') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Requesteddoctor'), as.numeric(time[firstTreatment==1]) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 3") + labs(x = "Time of first treatment", y = "Patients") +
  theme(legend.position="none") + 
  scale_x_continuous(breaks = seq(0,600,100)) +
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=500),
            vjust=-1,col='black',size=3) -> f3_treatment

df_final %>% 
  filter(acuity =='acuity4') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Requesteddoctor'), as.numeric(time[firstTreatment==1]) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 4") + labs(x = "Time of first treatment", y = "Patients") +
  scale_x_continuous(breaks = seq(0,600,100)) +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=500),
            vjust=-1,col='black',size=3) -> f4_treatment

df_final %>% 
  filter(acuity =='acuity5') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Requesteddoctor'), as.numeric(time[firstTreatment==1]) - as.numeric(time[activity=='Arrived']), NA)) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 5") + labs(x = "Time of first treatment", y = "Patients") +
  scale_x_continuous(breaks = seq(0,600,100)) + 
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=500),
            vjust=-1,col='black',size=3) -> f5_treatment

ggarrange(f1_treatment, f2_treatment, f3_treatment, f4_treatment, f5_treatment,
          labels = c("A", "B", "C", "D", "E"),
          ncol = 2, nrow = 3)

###11
#Draw graphs - Time to finished discharge. Caution needed as this is for non-admitted patients only, hence the NA values. 
df_final %>% 
  filter(acuity =='acuity1') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Finisheddischarge'), as.numeric(time[activity=='Finisheddischarge']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 1") +labs(x = "Time to finished discharge", y = "Patients") +
  scale_x_continuous(breaks = seq(0,600,100)) + 
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=500),
            vjust=-1,col='black',size=3) -> f1_disch

df_final %>% 
  filter(acuity =='acuity2') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Finisheddischarge'), as.numeric(time[activity=='Finisheddischarge']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 2") +labs(x = "Time to finished discharge", y = "Patients") +
  scale_x_continuous(breaks = seq(0,600,100)) + 
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=500),
            vjust=-1,col='black',size=3) -> f2_disch

df_final %>% 
  filter(acuity =='acuity3') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Finisheddischarge'), as.numeric(time[activity=='Finisheddischarge']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 3") +labs(x = "Time to finished discharge", y = "Patients") +
  scale_x_continuous(breaks = seq(0,600,100)) + 
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=500),
            vjust=-1,col='black',size=3) -> f3_disch

df_final %>% 
  filter(acuity =='acuity4') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Finisheddischarge'), as.numeric(time[activity=='Finisheddischarge']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 4") +labs(x = "Time to finished discharge", y = "Patients") +
  scale_x_continuous(breaks = seq(0,600,100)) + 
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=500),
            vjust=-1,col='black',size=3) -> f4_disch

df_final %>% 
  filter(acuity =='acuity5') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Finisheddischarge'), as.numeric(time[activity=='Finisheddischarge']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 5") +labs(x = "Time to finished discharge", y = "Patients") +
  scale_x_continuous(breaks = seq(0,600,100)) + 
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=500),
            vjust=-1,col='black',size=3) -> f5_disch

ggarrange(f1_disch, f2_disch, f3_disch, f4_disch, f5_disch,
          labels = c("A", "B", "C", "D", "E"),
          ncol = 2, nrow = 3)

###12
#Draw graphs - Time to Finishedadmission. This is for admitted patients only, hence the NA values. 
df_final %>% 
  filter(acuity =='acuity1') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Finishedadmission'), as.numeric(time[activity=='Finishedadmission']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 1") +labs(x = "Time to finished admission", y = "Patients") +
  theme(legend.position="none") + 
  scale_x_continuous(breaks = seq(0,600,100)) +
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=600),
            vjust=-1,col='black',size=3) -> f1_finadmission

df_final %>% 
  filter(acuity =='acuity2') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Finishedadmission'), as.numeric(time[activity=='Finishedadmission']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 2") +labs(x = "Time to finished admission", y = "Patients") +
  theme(legend.position="none") + 
  scale_x_continuous(breaks = seq(0,600,100)) +
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=600),
            vjust=-1,col='black',size=3) -> f2_finadmission

df_final %>% 
  filter(acuity =='acuity3') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Finishedadmission'), as.numeric(time[activity=='Finishedadmission']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 3") +labs(x = "Time to finished admission", y = "Patients") +
  theme(legend.position="none") + 
  scale_x_continuous(breaks = seq(0,600,100)) +
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=600),
            vjust=-1,col='black',size=3) -> f3_finadmission

df_final %>% 
  filter(acuity =='acuity4') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Finishedadmission'), as.numeric(time[activity=='Finishedadmission']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 4") +labs(x = "Time to finished admission", y = "Patients") +
  theme(legend.position="none") + 
  scale_x_continuous(breaks = seq(0,600,100)) +
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=600),
            vjust=-1,col='black',size=3) -> f4_finadmission

df_final %>% 
  filter(acuity =='acuity5') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Finishedadmission'), as.numeric(time[activity=='Finishedadmission']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 5") +labs(x = "Time to finished admission", y = "Patients") +
  theme(legend.position="none") + 
  scale_x_continuous(breaks = seq(0,600,100)) +
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=600),
            vjust=-1,col='black',size=3) -> f5_finadmission

ggarrange(f1_finadmission, f2_finadmission, f3_finadmission, f4_finadmission, f5_finadmission,
          labels = c("A", "B", "C", "D", "E"),
          ncol = 2, nrow = 3)

#Create data frames for the number of times a patient visited the different room &
#for the time the patients spent in the room in each visit

#Waiting room
#Empty data frames to fill in in the loop
waitingRooms_timesIn <- data.frame(patient = 0, acuity = 0, timesIn_waitingroom = 0)
waitingRooms_timesIn <- waitingRooms_timesIn %>% 
  filter(patient > 0)
waitingRooms_timeSpent <- data.frame(patient = 0, acuity = 0, timeSpent_waitingroom = 0)
waitingRooms_timeSpent <- waitingRooms_timeSpent %>% 
  filter(patient > 0)

for (pat in 1:df_final$patient[length(as.numeric(df_final$patient))]){ #for the times each patient visited the waiting room
  waitingRooms_timesIn[nrow(waitingRooms_timesIn)+1,] <- 0
  waitingRooms_timesIn$patient[nrow(waitingRooms_timesIn)] <- pat
  waitingRooms_timesIn$acuity[nrow(waitingRooms_timesIn)] <- df_final$acuity[df_final$patient==pat][1]
  gotwr <- which(df_final$activity == 'Gotwaitingroom' & df_final$patient == pat)
  times_gtwr <- length(gotwr)
  waitingRooms_timesIn$timesIn_waitingroom[nrow(waitingRooms_timesIn)] <- times_gtwr
  
  for (times in 1:times_gtwr){ #for the time the patient spent in the room
    waitingRooms_timeSpent[nrow(waitingRooms_timeSpent)+1,] <-0
    waitingRooms_timeSpent$patient[nrow(waitingRooms_timeSpent)] <- pat
    waitingRooms_timeSpent$acuity[nrow(waitingRooms_timeSpent)] <- df_final$acuity[df_final$patient==pat][1]
    timeSpent_waitingroom <- ifelse(times_gtwr>0, as.numeric(df_final$time[df_final$activity=='Leftwaitingroom' & df_final$patient == pat][times]) - as.numeric(df_final$time[df_final$activity=='Gotwaitingroom' & df_final$patient == pat][times]), NA)
    waitingRooms_timeSpent$timeSpent_waitingroom[nrow(waitingRooms_timeSpent)] <- timeSpent_waitingroom
  }
  
}

#Plots with the time spent in one visit in the waiting room
waitingRooms_timeSpent %>% 
  filter(acuity =='acuity1' & !is.na(timeSpent_waitingroom)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_waitingroom))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 1") +labs(x = "Time spent in the waiting rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_waitingroom,na.rm=TRUE))),y=0,x=mean(timeSpent_waitingroom,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_waitingroom,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f1_wr

waitingRooms_timeSpent %>% 
  filter(acuity =='acuity2' & !is.na(timeSpent_waitingroom)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_waitingroom))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 2") +labs(x = "Time spent in the waiting rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_waitingroom,na.rm=TRUE))),y=0,x=mean(timeSpent_waitingroom,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_waitingroom,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f2_wr

waitingRooms_timeSpent %>% 
  filter(acuity =='acuity3' & !is.na(timeSpent_waitingroom)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_waitingroom))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 3") +labs(x = "Time spent in the waiting rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_waitingroom,na.rm=TRUE))),y=0,x=mean(timeSpent_waitingroom,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_waitingroom,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f3_wr

waitingRooms_timeSpent %>% 
  filter(acuity =='acuity4' & !is.na(timeSpent_waitingroom)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_waitingroom))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 4") +labs(x = "Time spent in the waiting rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_waitingroom,na.rm=TRUE))),y=0,x=mean(timeSpent_waitingroom,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_waitingroom,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f4_wr

waitingRooms_timeSpent %>% 
  filter(acuity =='acuity5' & !is.na(timeSpent_waitingroom)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_waitingroom))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 5") +labs(x = "Time spent in the waiting rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_waitingroom,na.rm=TRUE))),y=0,x=mean(timeSpent_waitingroom,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_waitingroom,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f5_wr

ggarrange(f1_wr, f2_wr, f3_wr, f4_wr, f5_wr,
          labels = c("A", "B", "C", "D", "E"),
          ncol = 2, nrow = 3)

#Plots for the times in the waiting room
waitingRooms_timesIn2 <- waitingRooms_timesIn %>% 
  group_by(acuity) %>% 
  summarise(medianTimeIn = median(timesIn_waitingroom, na.rm = TRUE))

waitingRooms_timesIn2 %>% 
  ggplot(aes(y=medianTimeIn, x=acuity)) + 
  geom_bar(position="dodge", stat="identity", fill="#00837a") + 
  ggtitle("Median number of times spent in the waiting room per acuity") + 
  labs(y = "Number of times spent", x = "Patients") +
  theme(legend.position="none") + 
  theme_light()

#Minors room
#Empty data frames to fill in in the loop
minors_timesIn <- data.frame(patient = 0, acuity = 0, timesIn_minors = 0)
minors_timesIn <- minors_timesIn %>% 
  filter(patient > 0)
minors_timeSpent <- data.frame(patient = 0, acuity = 0, timeSpent_minors = 0)
minors_timeSpent <- minors_timeSpent %>% 
  filter(patient > 0)

for (pat in 1:df_final$patient[length(as.numeric(df_final$patient))]){ #for the times each patient visited the minors room
  minors_timesIn[nrow(minors_timesIn)+1,] <- 0
  minors_timesIn$patient[nrow(minors_timesIn)] <- pat
  minors_timesIn$acuity[nrow(minors_timesIn)] <- df_final$acuity[df_final$patient==pat][1]
  gotwr <- which(df_final$activity == 'Gotminors' & df_final$patient == pat)
  times_gtwr <- length(gotwr)
  minors_timesIn$timesIn_minors[nrow(minors_timesIn)] <- times_gtwr
  
  for (times in 1:times_gtwr){ #for the time the patient spent in the room
    minors_timeSpent[nrow(minors_timeSpent)+1,] <-0
    minors_timeSpent$patient[nrow(minors_timeSpent)] <- pat
    minors_timeSpent$acuity[nrow(minors_timeSpent)] <- df_final$acuity[df_final$patient==pat][1]
    timeSpent_minors <- ifelse(times_gtwr>0, as.numeric(df_final$time[df_final$activity=='Leftminors' & df_final$patient == pat][times]) - as.numeric(df_final$time[df_final$activity=='Gotminors' & df_final$patient == pat][times]), NA)
    minors_timeSpent$timeSpent_minors[nrow(minors_timeSpent)] <- timeSpent_minors
  }
  
}

#Plots with the time spent in one visit in the minors room
minors_timeSpent %>% 
  filter(acuity =='acuity1' & !is.na(timeSpent_minors)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_minors))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 1") +labs(x = "Time spent in the minors rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_minors,na.rm=TRUE))),y=0,x=mean(timeSpent_minors,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_minors,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f1_minors

minors_timeSpent %>% 
  filter(acuity =='acuity2' & !is.na(timeSpent_minors)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_minors))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 2") +labs(x = "Time spent in the minors rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_minors,na.rm=TRUE))),y=0,x=mean(timeSpent_minors,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_minors,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f2_minors

minors_timeSpent %>% 
  filter(acuity =='acuity3' & !is.na(timeSpent_minors)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_minors))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 3") +labs(x = "Time spent in the minors rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_minors,na.rm=TRUE))),y=0,x=mean(timeSpent_minors,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_minors,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f3_minors

minors_timeSpent %>% 
  filter(acuity =='acuity4' & !is.na(timeSpent_minors)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_minors))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 4") +labs(x = "Time spent in the minors rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_minors,na.rm=TRUE))),y=0,x=mean(timeSpent_minors,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_minors,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f4_minors

minors_timeSpent %>% 
  filter(acuity =='acuity5' & !is.na(timeSpent_minors)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_minors))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 5") +labs(x = "Time spent in the minors rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_minors,na.rm=TRUE))),y=0,x=mean(timeSpent_minors,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_minors,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f5_minors

ggarrange(f1_minors, f2_minors, f3_minors, f4_minors, f5_minors,
          labels = c("A", "B", "C", "D", "E"),
          ncol = 2, nrow = 3)

#Plots for the times in the minors room
minors_timesIn2 <- minors_timesIn %>% 
  group_by(acuity) %>% 
  summarise(medianTimeIn = median(timesIn_minors, na.rm = TRUE))

minors_timesIn2 %>% 
  ggplot(aes(y=medianTimeIn, x=acuity)) + 
  geom_bar(position="dodge", stat="identity", fill="#00837a") + 
  ggtitle("Median number of times spent in the minors room per acuity") + 
  labs(y = "Number of times spent", x = "Patients") +
  theme(legend.position="none") + 
  theme_light()

#Majors room
#Empty data frames to fill in in the loop
majors_timesIn <- data.frame(patient = 0, acuity = 0, timesIn_majors = 0)
majors_timesIn <- majors_timesIn %>% 
  filter(patient > 0)
majors_timeSpent <- data.frame(patient = 0, acuity = 0, timeSpent_majors = 0)
majors_timeSpent <- majors_timeSpent %>% 
  filter(patient > 0)

for (pat in 1:df_final$patient[length(as.numeric(df_final$patient))]){ #for the times each patient visited the majors room
  majors_timesIn[nrow(majors_timesIn)+1,] <- 0
  majors_timesIn$patient[nrow(majors_timesIn)] <- pat
  majors_timesIn$acuity[nrow(majors_timesIn)] <- df_final$acuity[df_final$patient==pat][1]
  gotwr <- which(df_final$activity == 'Gotmajors' & df_final$patient == pat)
  times_gtwr <- length(gotwr)
  majors_timesIn$timesIn_majors[nrow(majors_timesIn)] <- times_gtwr
  
  for (times in 1:times_gtwr){ #for the time the patient spent in the room
    majors_timeSpent[nrow(majors_timeSpent)+1,] <-0
    majors_timeSpent$patient[nrow(majors_timeSpent)] <- pat
    majors_timeSpent$acuity[nrow(majors_timeSpent)] <- df_final$acuity[df_final$patient==pat][1]
    timeSpent_majors <- ifelse(times_gtwr>0, as.numeric(df_final$time[df_final$activity=='Leftmajors' & df_final$patient == pat][times]) - as.numeric(df_final$time[df_final$activity=='Gotmajors' & df_final$patient == pat][times]), NA)
    majors_timeSpent$timeSpent_majors[nrow(majors_timeSpent)] <- timeSpent_majors
  }
  
}

#Plots with the time spent in one visit in the majors room
majors_timeSpent %>% 
  filter(acuity =='acuity1' & !is.na(timeSpent_majors)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_majors))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 1") +labs(x = "Time spent in the majors rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_majors,na.rm=TRUE))),y=0,x=mean(timeSpent_majors,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_majors,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f1_majors

majors_timeSpent %>% 
  filter(acuity =='acuity2' & !is.na(timeSpent_majors)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_majors))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 2") +labs(x = "Time spent in the majors rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_majors,na.rm=TRUE))),y=0,x=mean(timeSpent_majors,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_majors,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f2_majors

majors_timeSpent %>% 
  filter(acuity =='acuity3' & !is.na(timeSpent_majors)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_majors))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 3") +labs(x = "Time spent in the majors rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_majors,na.rm=TRUE))),y=0,x=mean(timeSpent_majors,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_majors,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f3_majors

majors_timeSpent %>% 
  filter(acuity =='acuity4' & !is.na(timeSpent_majors)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_majors))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 4") +labs(x = "Time spent in the majors rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_majors,na.rm=TRUE))),y=0,x=mean(timeSpent_majors,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_majors,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f4_majors

majors_timeSpent %>% 
  filter(acuity =='acuity5' & !is.na(timeSpent_majors)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_majors))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 5") +labs(x = "Time spent in the majors rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_majors,na.rm=TRUE))),y=0,x=mean(timeSpent_majors,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_majors,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f5_majors

ggarrange(f1_majors, f2_majors, f3_majors, f4_majors, f5_majors,
          labels = c("A", "B", "C", "D", "E"),
          ncol = 2, nrow = 3)

#Plots for the times in the majors room
majors_timesIn2 <- majors_timesIn %>% 
  group_by(acuity) %>% 
  summarise(medianTimeIn = median(timesIn_majors, na.rm = TRUE))

majors_timesIn2 %>% 
  ggplot(aes(y=medianTimeIn, x=acuity)) + 
  geom_bar(position="dodge", stat="identity", fill="#00837a") + 
  ggtitle("Median number of times spent in the majors room per acuity") + 
  labs(y = "Number of times spent", x = "Patients") +
  theme(legend.position="none") + 
  theme_light()

#Resus room
#Empty data frames to fill in in the loop
resus_timesIn <- data.frame(patient = 0, acuity = 0, timesIn_resus = 0)
resus_timesIn <- resus_timesIn %>% 
  filter(patient > 0)
resus_timeSpent <- data.frame(patient = 0, acuity = 0, timeSpent_resus = 0)
resus_timeSpent <- resus_timeSpent %>% 
  filter(patient > 0)

for (pat in 1:df_final$patient[length(as.numeric(df_final$patient))]){ #for the times each patient visited the resus room
  resus_timesIn[nrow(resus_timesIn)+1,] <- 0
  resus_timesIn$patient[nrow(resus_timesIn)] <- pat
  resus_timesIn$acuity[nrow(resus_timesIn)] <- df_final$acuity[df_final$patient==pat][1]
  gotwr <- which(df_final$activity == 'Gotresus' & df_final$patient == pat)
  times_gtwr <- length(gotwr)
  resus_timesIn$timesIn_resus[nrow(resus_timesIn)] <- times_gtwr
  
  for (times in 1:times_gtwr){ #for the time the patient spent in the room
    resus_timeSpent[nrow(resus_timeSpent)+1,] <-0
    resus_timeSpent$patient[nrow(resus_timeSpent)] <- pat
    resus_timeSpent$acuity[nrow(resus_timeSpent)] <- df_final$acuity[df_final$patient==pat][1]
    timeSpent_resus <- ifelse(times_gtwr>0, as.numeric(df_final$time[df_final$activity=='Leftresus' & df_final$patient == pat][times]) - as.numeric(df_final$time[df_final$activity=='Gotresus' & df_final$patient == pat][times]), NA)
    resus_timeSpent$timeSpent_resus[nrow(resus_timeSpent)] <- timeSpent_resus
  }
  
}

#Plots with the time spent in one visit in the resus room
resus_timeSpent %>% 
  filter(acuity =='acuity1' & !is.na(timeSpent_resus)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_resus))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 1") +labs(x = "Time spent in the resus rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_resus,na.rm=TRUE))),y=0,x=mean(timeSpent_resus,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_resus,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f1_resus

resus_timeSpent %>% 
  filter(acuity =='acuity2' & !is.na(timeSpent_resus)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_resus))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 2") +labs(x = "Time spent in the resus rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_resus,na.rm=TRUE))),y=0,x=mean(timeSpent_resus,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_resus,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f2_resus

resus_timeSpent %>% 
  filter(acuity =='acuity3' & !is.na(timeSpent_resus)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_resus))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 3") +labs(x = "Time spent in the resus rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_resus,na.rm=TRUE))),y=0,x=mean(timeSpent_resus,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_resus,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f3_resus

resus_timeSpent %>% 
  filter(acuity =='acuity4' & !is.na(timeSpent_resus)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_resus))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 4") +labs(x = "Time spent in the resus rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_resus,na.rm=TRUE))),y=0,x=mean(timeSpent_resus,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_resus,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f4_resus

resus_timeSpent %>% 
  filter(acuity =='acuity5' & !is.na(timeSpent_resus)) %>%
  #filter(!any(activity=='Gotsdec')) %>%
  ggplot(aes(timeSpent_resus))+geom_histogram(bins=20, fill="#00837a") +
  scale_x_continuous(breaks = seq(0,500,100)) + 
  ggtitle("Acuity 5") +labs(x = "Time spent in the resus rooms", y = "Patients") +
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(timeSpent_resus,na.rm=TRUE))),y=0,x=mean(timeSpent_resus,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(timeSpent_resus,na.rm=TRUE))),y=0,x=300),
            vjust=-1,col='black',size=3) -> f5_resus

ggarrange(f1_resus, f2_resus, f3_resus, f4_resus, f5_resus,
          labels = c("A", "B", "C", "D", "E"),
          ncol = 2, nrow = 3)

#Plots for the times in the resus room
resus_timesIn2 <- resus_timesIn %>% 
  group_by(acuity) %>% 
  summarise(medianTimeIn = median(timesIn_resus, na.rm = TRUE))

resus_timesIn2 %>% 
  ggplot(aes(y=medianTimeIn, x=acuity)) + 
  geom_bar(position="dodge", stat="identity", fill="#00837a") + 
  ggtitle("Median number of times spent in the resus room per acuity") + 
  labs(y = "Number of times spent", x = "Patients") +
  theme(legend.position="none") + 
  theme_light()

###Percentage of blood tests, x ray, CT in each acuity level 
#Empty data frames to fill in in the loop
tests <- data.frame(patient = 0, acuity = 0, bloodtest = 0, xray = 0, ct = 0)
tests <- tests %>% 
  filter(patient > 0)

for (pat in 1:df_final$patient[length(as.numeric(df_final$patient))]){ #for the times each patient had each type of test
  tests[nrow(tests)+1,] <- 0
  tests$patient[nrow(tests)] <- pat
  tests$acuity[nrow(tests)] <- df_final$acuity[df_final$patient==pat][1]
  
  #Blood test
  blt <- which(df_final$activity == 'Bloodfinished' & df_final$patient == pat)
  n_blt <- length(blt)
  tests$bloodtest[nrow(tests)] <- n_blt
  
  #CT
  CT <- which(df_final$activity == 'CTfinished' & df_final$patient == pat)
  n_CT <- length(CT)
  tests$ct[nrow(tests)] <- n_CT
  
  #X ray
  XRay <- which(df_final$activity == 'XRayfinished' & df_final$patient == pat)
  n_XRay<- length(XRay)
  tests$xray[nrow(tests)] <- n_XRay
  
}

#Calculate total number of tests
tests <- tests %>% 
  mutate(totalNoTests = bloodtest + xray + ct)

#Median, mean, max, min number of tests per acuity   
tests_per_acuity <- tests %>% 
  group_by(acuity) %>% 
  summarise(medianNoBloodTests = median(bloodtest, na.rm = TRUE),
            meanNoBloodTests = mean(bloodtest, na.rm = TRUE),
            maxNoBloodTests = max(bloodtest, na.rm = TRUE),
            minNoBloodTests = min(bloodtest, na.rm = TRUE),
            medianNoXrays = median(xray, na.rm = TRUE),
            meanNoXrays = mean(xray, na.rm = TRUE),
            maxNoXrays = max(xray, na.rm = TRUE),
            minNoXrays = min(xray, na.rm = TRUE),
            medianNoCT = median(ct, na.rm = TRUE),
            meanNoCT = mean(ct, na.rm = TRUE),
            maxNoCT = max(ct, na.rm = TRUE),
            minNoCT = min(ct, na.rm = TRUE),
            medianNoTests = median(totalNoTests, na.rm = TRUE),
            meanNoTests = mean(totalNoTests, na.rm = TRUE),
            maxNoTests = max(totalNoTests, na.rm = TRUE), 
            minNoTests = min(totalNoTests, na.rm = TRUE))

print(tests_per_acuity)

#Plot for total number of tests  
total_pl <- tests_per_acuity %>% 
  ggplot(aes(y=meanNoTests, x=acuity)) + 
  geom_bar(position="dodge", stat="identity", fill="#00837a") + 
  ggtitle("Average number of tests per acuity") + 
  labs(y = "Number of tests", x = "Patients") +
  theme(legend.position="none") + 
  theme_light()
print(total_pl)

#Plot for number of blood tests  
bloodtest_pl <- tests_per_acuity %>% 
  ggplot(aes(y=meanNoBloodTests, x=acuity)) + 
  geom_bar(position="dodge", stat="identity", fill="#00837a") + 
  ggtitle("Average number of blood tests per acuity") + 
  labs(y = "Number of blood tests", x = "Patients") +
  theme(legend.position="none") + 
  theme_light()

#Plot for number of xrays  
xray_pl <- tests_per_acuity %>% 
  ggplot(aes(y=meanNoXrays, x=acuity)) + 
  geom_bar(position="dodge", stat="identity", fill="#00837a") + 
  ggtitle("Average number of x rays per acuity") + 
  labs(y = "Number of x rays", x = "Patients") +
  theme(legend.position="none") + 
  theme_light()

#Plot for number of CT  
ct_plot <- tests_per_acuity %>% 
  ggplot(aes(y=meanNoCT, x=acuity)) + 
  geom_bar(position="dodge", stat="identity", fill="#00837a") + 
  ggtitle("Average number of CT per acuity") + 
  labs(y = "Number of CT", x = "Patients") +
  theme(legend.position="none") + 
  theme_light()

ggarrange(bloodtest_pl, xray_pl, ct_plot,
          labels = c("A", "B", "C"),
          ncol = 3, nrow = 1)

#Change structure for stacked bar plot
library(reshape2)
t2 <- melt(tests, id.vars = c('patient', 'acuity'), 
           variable.name = 'typeTest', 
           value.name = 'NumberOftest')

t2 <- t2 %>% 
  filter(typeTest != "totalNoTests") %>% 
  arrange(patient)

t2_peracuity <- t2 %>% 
  group_by(acuity, typeTest) %>% 
  summarise(meantests = mean(NumberOftest, na.rm = TRUE))

stpl <- ggplot(t2_peracuity, aes(fill=typeTest, x=acuity, y=meantests)) + 
  geom_bar(position="stack", stat="identity") +
  ggtitle("Average number of tests per acuity") + 
  labs(y = "Number of tests", x = "Patients") +
  theme(legend.position="none") + 
  theme_light() + 
  scale_fill_discrete(name="Type of test",
                      labels=c("Blood test", "X ray", "CT"))
print(stpl)

#How much time until the patient gets a bed at the hospital
df_final %>% 
  filter(acuity =='acuity1') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Gotbedinhospital'), as.numeric(time[activity=='Gotbedinhospital']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 1") +labs(x = "Time to bed (from arrival)", y = "Patients") +
  scale_x_continuous(breaks = seq(0,600,100)) + 
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=700),
            vjust=-1,col='black',size=3) -> f1_bed

df_final %>% 
  filter(acuity =='acuity2') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Gotbedinhospital'), as.numeric(time[activity=='Gotbedinhospital']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 2") +labs(x = "Time to bed (from arrival)", y = "Patients") +
  scale_x_continuous(breaks = seq(0,600,100)) + 
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=700),
            vjust=-1,col='black',size=3) -> f2_bed

df_final %>% 
  filter(acuity =='acuity3') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Gotbedinhospital'), as.numeric(time[activity=='Gotbedinhospital']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 3") +labs(x = "Time to bed (from arrival)", y = "Patients") +
  scale_x_continuous(breaks = seq(0,600,100)) + 
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=700),
            vjust=-1,col='black',size=3) -> f3_bed

df_final %>% 
  filter(acuity =='acuity4') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Gotbedinhospital'), as.numeric(time[activity=='Gotbedinhospital']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 4") +labs(x = "Time to bed (from arrival)", y = "Patients") +
  scale_x_continuous(breaks = seq(0,600,100)) + 
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=700),
            vjust=-1,col='black',size=3) -> f4_bed

df_final %>% 
  filter(acuity =='acuity5') %>%
  group_by(patient)%>%
  filter(!any(activity=='Gotsdec')) %>%
  mutate(Diff = ifelse(any(activity=='Gotbedinhospital'), as.numeric(time[activity=='Gotbedinhospital']) - as.numeric(time[activity=='Arrived']), NA)) %>%
  filter(row_number()==1) %>%
  ggplot(aes(Diff))+geom_histogram(bins=20, fill="#00837a") +
  ggtitle("Acuity 5") +labs(x = "Time to bed (from arrival)", y = "Patients") +
  scale_x_continuous(breaks = seq(0,600,100)) + 
  theme(legend.position="none") + 
  theme_light() +
  geom_text(aes(label=paste("Mean:", round(mean(Diff,na.rm=TRUE))),y=0,x=mean(Diff,na.rm=TRUE)),
            vjust=-1,col='black',size=3) +
  geom_text(aes(label=paste("Median:", round(median(Diff,na.rm=TRUE))),y=0,x=700),
            vjust=-1,col='black',size=3) -> f5_bed

ggarrange(f1_bed, f2_bed, f3_bed, f4_bed, f5_bed,
          labels = c("A", "B", "C", "D", "E"),
          ncol = 2, nrow = 3)


##############################################
###13
#Convert time stamp in minutes to POSIXct variable.
calculateDate <- function(year, minutes){
  
  # here the 1440 is number of minutes in a day.  as the function needs that value in days.   
  z <- as.Date(minutes/1440, origin = paste0(year,"-01-01"))
  
  ## covert to POSIXct date to show the time also, otherwise these wont show
  z <- as.POSIXct.Date(z)
}

df_final[, "time"] = calculateDate(2023, as.numeric(df_final[, "time"]))

###14
#Filter on specific acuities for process mining
df_filtered_5 <- df_final %>% filter(acuity =='acuity5')
df_filtered_4 <- df_final %>% filter(acuity =='acuity4')
df_filtered_3 <- df_final %>% filter(acuity =='acuity3')
df_filtered_2 <- df_final %>% filter(acuity =='acuity2')
df_filtered_1 <- df_final %>% filter(acuity =='acuity1')


###15
#Merge together acuity and activity strings to allow to distinguish different events
df_filtered_5['Mergedacuityandactivity'] = paste(df_filtered_5$acuity, df_filtered_5$activity, sep=" ")
df_filtered_4['Mergedacuityandactivity'] = paste(df_filtered_4$acuity, df_filtered_4$activity, sep=" ")
df_filtered_3['Mergedacuityandactivity'] = paste(df_filtered_3$acuity, df_filtered_3$activity, sep=" ")
df_filtered_2['Mergedacuityandactivity'] = paste(df_filtered_2$acuity, df_filtered_2$activity, sep=" ")
df_filtered_1['Mergedacuityandactivity'] = paste(df_filtered_1$acuity, df_filtered_1$activity, sep=" ")

###16
#Draw process map
#Make simple event log
simplified_df_5 <- bupaR::simple_eventlog(eventlog = df_filtered_5,
                                          case_id = "patient",
                                          activity_id = "Mergedacuityandactivity",
                                          timestamp = "time")
simplified_df_4 <- bupaR::simple_eventlog(eventlog = df_filtered_4,
                                          case_id = "patient",
                                          activity_id = "Mergedacuityandactivity",
                                          timestamp = "time")
simplified_df_3 <- bupaR::simple_eventlog(eventlog = df_filtered_3,
                                          case_id = "patient",
                                          activity_id = "Mergedacuityandactivity",
                                          timestamp = "time")
simplified_df_2 <- bupaR::simple_eventlog(eventlog = df_filtered_2,
                                          case_id = "patient",
                                          activity_id = "Mergedacuityandactivity",
                                          timestamp = "time")
simplified_df_1 <- bupaR::simple_eventlog(eventlog = df_filtered_1,
                                          case_id = "patient",
                                          activity_id = "Mergedacuityandactivity",
                                          timestamp = "time")


#Draw full process map
simplified_df_5 %>%
  process_map(rankdir = "TB")
simplified_df_4 %>%
  process_map(rankdir = "TB")
simplified_df_3 %>%
  process_map(rankdir = "TB")
simplified_df_2 %>%
  process_map(rankdir = "TB")
simplified_df_1 %>%
  process_map(rankdir = "TB")

#Second plot showing performance times
simplified_df_5 %>%
  process_map(performance(mean, "mins"), rankdir = "TB")
simplified_df_4 %>%
  process_map(performance(mean, "mins"), rankdir = "TB")
simplified_df_3 %>%
  process_map(performance(mean, "mins"), rankdir = "TB")
simplified_df_2 %>%
  process_map(performance(mean, "mins"), rankdir = "TB")
simplified_df_1 %>%
  process_map(performance(mean, "mins"), rankdir = "TB")


#Save mean performance times to compute times between nodes
simplified_df_5 %>%
  process_map(performance(mean, "mins"), rankdir = "TB") -> p5
simplified_df_4 %>%
  process_map(performance(mean, "mins"), rankdir = "TB") -> p4
simplified_df_3 %>%
  process_map(performance(mean, "mins"), rankdir = "TB") -> p3
simplified_df_2 %>%
  process_map(performance(mean, "mins"), rankdir = "TB") -> p2
simplified_df_1 %>%
  process_map(performance(mean, "mins"), rankdir = "TB") -> p1

edges_p5 <- attr(p5, "edges")
edges_p4 <- attr(p4, "edges")
edges_p3 <- attr(p3, "edges")
edges_p2 <- attr(p2, "edges")
edges_p1 <- attr(p1, "edges")

#Find maximum 5 times per acuity
print("Acuity 5 - Highest mean times")
head(edges_p5[order(edges_p5$value,decreasing=TRUE),])
print("Acuity 4 - Highest mean times")
head(edges_p4[order(edges_p4$value,decreasing=TRUE),])
print("Acuity 3 - Highest mean times")
head(edges_p3[order(edges_p3$value,decreasing=TRUE),])
print("Acuity 2 - Highest mean times")
head(edges_p2[order(edges_p2$value,decreasing=TRUE),])
print("Acuity 1 - Highest mean times")
head(edges_p1[order(edges_p1$value,decreasing=TRUE),])

#Additional plots - dotted chart
## These don't appear to work
simplified_df_5 %>%
  dotted_chart(x = "relative")
simplified_df_4 %>%
  dotted_chart(x = "relative")
simplified_df_3 %>%
  dotted_chart(x = "relative")
simplified_df_2 %>%
  dotted_chart(x = "relative")
simplified_df_1 %>%
  dotted_chart(x = "relative")


#Additional plots - trace explorer
#Shows the most frequent traces
#Order of the metrics is:
#Relative coverage of the trace
#Absolute coverage of the trace
#Cumulative coverage of this and previous traces
simplified_df_5 %>%
  trace_explorer(show_labels = FALSE, n_traces = 10)
simplified_df_4 %>%
  trace_explorer(show_labels = FALSE, n_traces = 10)
simplified_df_3 %>%
  trace_explorer(show_labels = FALSE, n_traces = 10)
simplified_df_2 %>%
  trace_explorer(show_labels = FALSE, n_traces = 10)
simplified_df_1 %>%
  trace_explorer(show_labels = FALSE, n_traces = 10)


#Process matrix
simplified_df_5%>%
  process_matrix(frequency("absolute")) %>%
  plot()
simplified_df_4%>%
  process_matrix(frequency("absolute")) %>%
  plot()
simplified_df_3%>%
  process_matrix(frequency("absolute")) %>%
  plot()
simplified_df_2%>%
  process_matrix(frequency("absolute")) %>%
  plot()
simplified_df_1%>%
  process_matrix(frequency("absolute")) %>%
  plot()

