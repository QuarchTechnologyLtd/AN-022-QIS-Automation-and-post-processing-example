#!/usr/bin/env python
'''
This example demonstrates basic automation with QIS and post processing of raw data after recording.
We will record at a high rate and post process down to a lower rate, ending with 100uS and 500uS sample rates

########### VERSION HISTORY ###########

03/10/2019 - Andy Norrie     - First Version

########### INSTRUCTIONS ###########

1- Connect a Quarch power module to your PC via USB or LAN and power it on
2- Ensure quarcypy is installed
3- Set the text ID of the PPM you want to connect to in myDeviceID


####################################
'''


import os, time

import quarchpy
from quarchpy import qisInterface
from quarchpy.device import *
from quarchpy.qis import *
# Timing to check how long it takes to end the stream
from timeit import default_timer as timer

# Path where stream will be saved to (defaults to current script path)
streamPath = os.path.dirname(os.path.realpath(__file__))

'''
Main function, containing the example code to execute
'''
def main():

    # Required min version for this application note
    quarchpy.requiredQuarchpyVersion ("2.0.9")
    
    # Display title text
    print ("\n################################################################################\n")
    print ("\n                           QUARCH TECHNOLOGY                                  \n\n")
    print ("     Automated capture and post processing with Quarch Instrument Server (QIS).     ")
    print ("\n################################################################################\n")


    # Checks is QIS is running on the localhost
    if not isQisRunning():
        print ("-Starting QIS")
    # Start the version on QIS installed with the quarchpy, otherwise use the running version
        startLocalQis()

    myQis = qisInterface() 
    # Wait for QIS to find modules, this will be handled in GetQisModuleSelection soon
    time.sleep(2)
    
    # Request a list of all USB and LAN accessible modules
    print ("-Select a device, MUST be USB or TCP (not REST)")
    myDeviceID = myQis.GetQisModuleSelection(additionalOptions=["rescan"])
    while myDeviceID == "rescan":
        myDeviceID = myQis.GetQisModuleSelection(additionalOptions=["rescan"])

    # Specify the device to connect to, we are using a local version of QIS here, otherwise specify "QIS:192.168.1.101:9722"
    myQuarchDevice = getQuarchDevice(myDeviceID, ConType = "QIS")
    # Convert the base device to a power device class
    myQisDevice = quarchPPM (myQuarchDevice)

    # Prints out connected module information        
    print ("MODULE CONNECTED: \n" + myQisDevice.sendCommand ("*idn?"))
    
    print ("-Waiting for drive to be ready")
    # Setup the voltage mode and enable the outputs. This is used so the script is compatible with older XLC modules which do not autodetect the fixtures
    myQisDevice.setupPowerOutput()
    # (OPTIONAL) Wait for device to power up and become ready (you can also start your workloads here if needed)
    # time.sleep(5)

    print ("-Setting up module record parameters")

    # Sets for a manual record trigger, so we can start the stream from the script
    msg = myQisDevice.sendCommand("record:trigger:mode manual")
    if (msg != "OK"):
        print ("Failed to set trigger mode: " + msg)
    # Set the averaging rate to the module to 16 (64uS) as the closest to 100uS
    msg = myQisDevice.sendCommand ("record:averaging 16")   
    if (msg != "OK"):
        print ("Failed to set hardware averaging: " + msg)
    # Set the resampling mode to give us exactly 100uS
    msg = myQisDevice.sendCommand ("stream mode resample 100uS")
    if (msg != "OK"):
        print ("Failed to set software resampling: " + msg)
    # Ask QIS to include power calculations
    msg = myQisDevice.sendCommand ("stream mode power enable")
    if (msg != "OK"):
        print ("Failed to set power record mode: " + msg)
    # Ask QIS to include power total
    msg = myQisDevice.sendCommand ("stream mode power total enable")
    if (msg != "OK"):
        print ("Failed to set total power record mode: " + msg)
    # Ensure the latest level of header is requested so PPM and PAM data format is the same in the CSV
    msg = myQisDevice.sendCommand ("stream mode header v3")
    if (msg != "OK"):
        print ("Failed to set software resampling: " + msg)


    print ("-Recording data...")
    # Start a stream, using the local folder of the script and a time-stamp file name in this example
    fileName = "RawData100us.csv"        
    myQisDevice.startStream (streamPath + "\\" + fileName, 2000, 'Example stream to file with 2000Mb limit',separator=",")
           
    # Wait for a few seconds to record data then stop the stream     
    for x in range(5):
        time.sleep(1)
        print (".")
    
    print ("-Stopping recording")
    start = timer()
    myQisDevice.stopStream()    
    end = timer()
    print(str((end - start)) + " Seconds to save the stream")

    print ("-Closing module")
    myQisDevice.closeConnection()

    # Request raw CSV data from the stream, into the local folder (NOTE: current QPS does not support spaces in the export path)
    rawOutputPath = streamPath + "\\RawData100us.csv"        

    # Run the post process step.  The first one is purely for the stats calculations, as we alredy have it in the correct sample rate
    print ("-Post processing step 1")
    post_process_resample (rawOutputPath, 1, streamPath + "\\PostData100us.csv")
    print ("-Post processing step 2")
    post_process_resample (rawOutputPath, 5, streamPath + "\\PostData500us.csv")
    print ("-Post processing step 3")
    post_process_resample (rawOutputPath, 10, streamPath + "\\PostData1ms.csv")

    
# Post process and resample the CSV file (for now assuming all data is in one file, v1.09 maxes out at 100k lines right now in a single file, this limit will be removed in the next version)    
# Assumes standard channels are enabled for this example, this could be automated by parsing the stream header to see the record channels
def post_process_resample (raw_file_path, resample_count, output_file_path):    
    # Init variables
    headerLines = 0
    stripeCount = 0
    dilimiter = ","
    number_of_columns = 9
    averaged_stripe_count = 0
    # Storage for the accumulating data (9 columns of data)
    procData = [0,0,0,0,0,0,0,0,0]
    # Storage for the summary data (8 columns as time is note processed)
    maxData = [0,0,0,0,0,0,0,0]
    minData = [999999,999999,999999,999999,999999,999999,999999,999999]
    aveData = [0,0,0,0,0,0,0,0]
    # Open both the input and output files in appropriate access modes
    with open(raw_file_path, 'r') as rawFile:
        with open (output_file_path, 'w') as postFile:
            # Iterate through all input files
            for fileLine in rawFile:
                # headerline is unique, copy it directly
                if (headerLines < 2):
                    postFile.write (fileLine + "\n")
                    headerLines = headerLines + 1
                    continue

                # Accumulate the required number of lines                
                lineSections = fileLine.split(dilimiter)
                # Update to the latest time point
                procData[0] = lineSections[0]
                # Sum the values for all other columns
                for i in range (1, number_of_columns):                                    
                    procData[i] += int(lineSections[i])
                stripeCount += 1

                # When we have enough data to complete one output line we can process it
                if (stripeCount == resample_count):
                    # Track the number of output stripes
                    averaged_stripe_count += 1

                    # Divide down the averaged colums to get the final result
                    for i in range (1, number_of_columns):                                    
                        procData[i] /= resample_count
                    # Generate the single line for the output file
                    outStr = dilimiter.join (str(x) for x in procData)
                    postFile.write (outStr + "\n")
                    # Track maximums
                    for i in range (1, number_of_columns):       
                        if (procData[i] > maxData[i-1]):
                            maxData[i-1] = procData[i]
                    # Track minimums
                    for i in range (1, number_of_columns):
                        if (procData[i] < minData[i-1]):
                            minData[i-1] = procData[i]
                    # Track averages (Note: large datasets may overflow this simple averaging mechanism)
                    for i in range (1, number_of_columns):                       
                        aveData[i-1] += procData[i]

                    # Reset the accumulating data buffer
                    procData = [0,0,0,0,0,0,0,0,0]    
                    stripeCount = 0

            # Complete the calculation of the average values
            for i in range (1, number_of_columns):                       
                aveData[i-1] /= averaged_stripe_count

            # Add the stats data to the bottom of the output file
            postFile.write ("\n\nSTATISTICS\n")
            postFile.write ("MAX," + dilimiter.join(str(x) for x in maxData) + "\n")
            postFile.write ("MIN," + dilimiter.join(str(x) for x in minData) + "\n")
            postFile.write ("AVE," + dilimiter.join(str(x) for x in aveData) + "\n")



if __name__=="__main__":
    main()
