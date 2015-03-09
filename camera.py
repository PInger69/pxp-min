#!/usr/bin/python
import constants as c
from pxputil import disk as pdisk
from time import sleep

############################################
#	all encoder/camera-related functions  #
############################################


def getOnCams():
	""" Get a dictionary of all video sources that were detected in the system
		Args:
			none
		Returns:
			none
	"""
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

def camParam(param,camID=False,getAll=False):
	""" Returns a camera parameter
		Args:
			param(str): name of the parameter
			camID(str,optional): camera ID from which to get this parameter. if not set, default: False
			getAll(bool,optional): whether to get a list of values from all cameras
		Returns:
			none
	"""
	cams = getOnCams()
	# check if the specified camera exists in the list
	if(camID and not (camID in cams)):
		return False #specified camera doesn't exist
	cam = False
	if(getAll):
		result = []
	else:
		result = False
	if(camID): #get the specified camera
		cam = cams[camID]
	else: # user didn't specify a camera
		while(len(cams)>0): #look for cameras that have the requested parameter
			camID, cam = cams.popitem()
			if(param in cam and 'cameraPresent' in cam and cam['cameraPresent']): #found first camera that has the requested parameter defined
				if(getAll):
					result.append(cam[param])
				else:
					result = cam[param]
		#end while cams>0
	#end else (no camID)
	# the requested parameter doesn't exist
	return result
#end camParam

# start an encode from all cameras
def camStart():
	""" Sends 'start live event' command to the service 
		Args:
			none
		Returns:
			(bool): whether command succeeded
	"""
	import os
	try:
		# get active cameras
		cameras = getOnCams()
		if(len(cameras)<1): #no cameras active - can't start and encode
			return False
		pdisk.sockSend('STR|',addnewline=False)
		sleep(3) #wait for 3 seconds before returning result - to make sure streams start up properly
		return True
	except:
		return False
#end camStart
# pause cameras
def camPause(camID = False):
	""" Sends 'pause live event' command to the service 
		Args:
			none
		Returns:
			(bool): whether command succeeded
	"""
	pdisk.sockSend("PSE",addnewline=False)
	return True
#end camPause
#resume paused cameras
def camResume(camID = False):
	""" Sends 'resume paused live event' command to the service 
		Args:
			none
		Returns:
			(bool): whether command succeeded
	"""
	pdisk.sockSend("RSM",addnewline=False)
	return True
#end camResume
# sends the signal to stop the cameras from streaming (even if they weren't streaming)
def camStop():
	""" Sends 'stop live event' command to the service 
		Args:
			none
		Returns:
			(bool): whether command succeeded
	"""
	pdisk.sockSend("STP",addnewline=False)
	return True
#end camStop
