#!/usr/bin/python
import constants as c
from pxputil import disk as pdisk
from time import sleep

############################################
#    all encoder/camera-related functions  #
############################################


def getOnCams():
	import json, os
	try:
		# check if there are any teradek devices
		# cams = json.loads(pdisk.file_get_contents(c.devCamList))
		cams = json.loads(pdisk.sockSendWait('CML|',addnewline=False,timeout=10))
		if((type(cams) is dict) and (len(cams)>0)):
			return cams
	except:
		pass
	# no RTSP sources found
	return {}
#end getOnCams

#returns a camera parameter
def camParam(param,camID=False):
	cams = getOnCams()
	# check if the specified camera exists in the list
	if(camID and not (camID in cams)):
		return False #specified camera doesn't exist
	cam = False
	if(camID): #get the specified camera
		cam = cams[camID]
	else: # user didn't specify a camera - get the first available camera
		while(len(cams)>0): #look for the first camera that has the requested parameter
			camID, cam = cams.popitem()
			if(param in cam): #found first camera that has the requested parameter defined
				break 
		#end while cams>0
	#end else (no camID)
	# get the parameter from that camera
	if(cam and param in cam):
		return cam[param]
	# the requested parameter doesn't exist
	return False
#end camParam

# start an encode from all cameras
def camStart(quality='high'):
	import os
	try:
		# get active cameras
		cameras = getOnCams()
		if(len(cameras)<1): #no cameras active
			return False
		pdisk.sockSend('STR|'+quality,addnewline=False)
		sleep(3) #wait for 3 seconds before returning result - to make sure streams start up properly
		return True
	except:
		return False
#end camStart
# pause cameras
def camPause(camID = False):
	pdisk.sockSend("PSE",addnewline=False)
	return True
#end camPause
#resume paused cameras
def camResume(camID = False):
	pdisk.sockSend("RSM",addnewline=False)
	return True
#end camResume
# stops the cameras from streaming (even if they weren't streaming)
def camStop():
	pdisk.sockSend("STP",addnewline=False)
	return True
#end camStop

# returns status of a blackmagic Pro Recorder
# possible values: 'on', 'recorder' (not found), 'camera' (not found), 'unknown'
def _bmStatus():
	# state bits		
	#       app starting
	#       | encoder streaming
	#       | | camera present
	#       | | | pro recorder present
	#       | | | |
	# bits: 0 0 0 0
	# get bm status
	try:
		bmSdkOn = pdisk.psOn("pxpStream.app")
		state = int(pdisk.file_get_contents("/tmp/pxpstreamstatus"))
		if((state & (1+2+4))==7):
			status = "on"
		elif(not (state&1)): #pro recorder is missing
			status = "recorder"
		elif(not (state&2)): #camera is missing
			status = "camera"
		else: 	 #the app is just starting
			status = "unknown"
		if (not bmSdkOn):
			status = "unknown"
	except Exception as e:
		status = str(e)
	return status
#emd bmStatus
