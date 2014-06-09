#!/usr/bin/python
import constants as c
from pxputil import disk as pdisk
from time import sleep

############################################
#    all encoder/camera-related functions  #
############################################


# gets a list of all enabled encoders/cameras
def getOnCams():
	cameras = pdisk.cfgGet(section="cameras")
	return cameras
#end getCameras

def getAllCams():
	import json, os
	# check if there are any teradek devices
	terainfo = json.loads(pdisk.file_get_contents(c.tdCamList))
	if(type(terainfo) is dict and len(terainfo)>0):
		return terainfo
	# no teradeks found
	return {}
	# # check if blackmagic device is connected
	# if(not os.path.exists("/Applications/pxpStream.app")):
	# 	# streaming app does not exist - this server was not configured for BlackMagic H.264 Pro Recorder
	# 	return {}
	# # the app exists, find out the status of the pro recorder
	# if (not pdisk.psOn("pxpStream.app")):
	# 	os.system("/usr/bin/open /Applications/pxpStream.app")
	# # wait for the app to update the status
	# timeout = 15 #wait for maximum of 15 seconds to get the bm status
	# while (_bmStatus()=='unknown' and timeout>0):
	# 	sleep(1)
	# 	timeout -= 1
	# return {'blackmagic':{'format':'mpegts','url':'udp://127.0.0.1:2290','status':_bmStatus()}}
#end allCameras

# looks up camID by camera index (e.g. cameras are indexed 0, 1, 2... camIDs are "192.168.1.110", "192.168.1.114"...)
# @param (int) camIndex
def getCamID(camIndex):
	cams = getOnCams() #only active cameras have camIndex
	# look for the right index in all cameras
	for cam in cams:
		if(cams[cam]['idx']==camIndex):
			return cam
	return False
#end getCamID

#looks up camera index(e.g. 0,1,2...) by camID(e.g. "192.168.1.110")
# @param (str) camID
def getCamIDX(camID):
	cams = getOnCams()
	for cam in cams:
		if(cam==camID):
			return cams[cam]['idx']
	return False
#end getCamIDX

# enables camera/encoder to stream
# if camera ID was not specified, enables all cameras
def camOn(camID = False):
	# get all the cameras
	camlist = getAllCams()
	if(camID): #enable 1 camera
		# make sure the specified camera exists
		if(not camID in camlist):
			return False
		cameras = getOnCams()
		if(camID in cameras):# this camera is already enabled - nothing to do
			return True
		camIndex = _nextIndex(cameras)
		cameras[camID] = camlist[camID]
		cameras[camID]['idx']=camIndex
		cameras[camID]['state']='stopped'
		# initialize ports (if any)
		if('port' in cameras[camID]):
			for portName in cameras[camID]['port']:
				port = int(cameras[camID]['port'][portName])
				if(port % 100):
					continue
				# if port ends in 00 (not initialized) set it to the index of the camera
				cameras[camID]['port'][portName] = port+camIndex
		#end if port
	#end if camID
	else:
		# camID was not specified - enable all cameras
		cameras = {}
		camIndex = 0
		# go through cameras and add them to the enabled cameras dictionary
		for camID in camlist:
			cameras[camID] = camlist[camID]
			cameras[camID]['idx']=camIndex
			cameras[camID]['state']='stopped'
			# initialize ports (if any)
			if('port' in cameras[camID]):
				for portName in cameras[camID]['port']:
					port = int(cameras[camID]['port'][portName])
					if(port % 100):
						continue
					# if port ends in 00 (not initialized) set it to the index of the camera
					cameras[camID]['port'][portName] = port+camIndex
			#end if port
			camIndex += 1
	#end else
	# save changes to the settings file
	pdisk.cfgSet(section="cameras",value=cameras)
	return True
#end enableCamera

# prevents camera from being able to stream (stops existing stream if it's started already)
def camOff(camID=False):
	cameras = getOnCams()# all enabled cameras
	if(camID):#disable one specific camera
		if(not camID in cameras): #this camera does not exist (may have been disabled previously)
			return False
		# remove camera from the 'enabled cameras' dictionary
		del cameras[camID]
	else:# disable all cameras
		cameras = {}
	pdisk.cfgSet(section="cameras",value=cameras)
	return True
#end disableCamera
#returns a camera parameter
def camParam(param,camIndex=0,camID=False):
	cams = getOnCams()
	if(not camID):#get the device ID (e.g. 192.168.1.101)
		camID = getCamID(camIndex)
	if(not camID in cams):
		return False
	if(param in cams[camID]):
		return cams[camID][param]
	return False
#end camParam

# sets a camera parameter
def camParamSet(param,value,camIndex=0,camID=False):
	cams = getOnCams() #get all enabled cameras
	# if neither camera index nor camID were set, apply this setting to all cameras
	if(camIndex or camID):
		if(not camID):#get the device ID (e.g. 192.168.1.101)
			camID = getCamID(camIndex)
		if(not camID in cams):
			return False
		cams[camID][param]=value
	else:
		#applying setting to every camera
		for cam in cams:
			cams[cam][param]=value
	return pdisk.cfgSet(section="cameras",value=cams)
#end camParamSet

# start an encode from all cameras
def camStart(quality='high'):
	import os
	try:
		# make sure encode is not already running
		current_status = camStatus()
		if(current_status=='live' or current_status=='paused'):
			return False
		# reset all cameras - in case some encoders changed their ip address
		camOff()
		sleep(1)
		camOn()
		# get active cameras
		cameras = getOnCams()
		if(len(cameras)<1): #no cameras active
			return False

		for devID in cameras:
			cameras[devID]['state'] = 'live'
		pdisk.sockSend('STR|'+quality,addnewline=False)
		# update camera statuses on the disk
		pdisk.cfgSet(section="cameras",value=cameras)
		sleep(3) #wait for 3 seconds before returning result - to make sure streams start up properly
		return True
	except:
		return False
#end camStart
# pause cameras
def camPause(camID = False):
	cameras = getOnCams()# all enabled cameras
	if(camID):#pause one specific camera
		if(not camID in cameras): #this camera does not exist (may have been disabled previously)
			return False
		#add paused state
		if(cameras[camID]['state']=='live'):
			cameras[camID]['state']='paused'
	else:# pause all cameras
		for camID in cameras:
			if(cameras[camID]['state']=='live'):
				cameras[camID]['state']='paused'
	pdisk.cfgSet(section="cameras",value=cameras)
	pdisk.sockSend("PSE",addnewline=False)
	return True
#end camPause
#resume paused cameras
def camResume(camID = False):
	cameras = getOnCams()# all enabled cameras
	if(camID):#pause one specific camera
		if(not camID in cameras): #this camera does not exist (may have been disabled previously)
			return False
		#set state to live (if it was paused)
		if(cameras[camID]['state']=='paused'):
			cameras[camID]['state']='live'
	else:# resume all cameras
		for camID in cameras:
			if(cameras[camID]['state']=='paused'):
				cameras[camID]['state']='live'
	pdisk.cfgSet(section="cameras",value=cameras)
	pdisk.sockSend("RSM",addnewline=False)
	return True
#end camResume
def camStatus(camID = False):
	cameras = getOnCams()# all enabled cameras
	if(camID):
		if(not camID in cameras): #this camera does not exist (may have been disabled previously)
			return False
		return cameras[camID]['status']
	#find status of all cameras:
	# if a single camera is live, return status is live
	# if no cameras are live, but at least one is paused - return status as paused
	# if no cameras are live or paused, then status is stopped
	status = False
	for camID in cameras:
		status = status or cameras[camID]['on']
		if(cameras[camID]['state']=='live' and cameras[camID]['on']):
			return 'live'
		if(cameras[camID]['state']=='paused' and cameras[camID]['on']):
			return 'paused'
	if(len(cameras)<1 or not status): #when no cameras present, return False as status
		return False
	#end for camID in cams
	return 'stopped'
#end camStatus
# stops the cameras from streaming (even if they weren't streaming)
def camStop():
	import os
	cams = getOnCams()
	for cam in cams:
		cams[cam]['state']='stopped'
	pdisk.sockSend("STP",addnewline=False)
	return pdisk.cfgSet(section="cameras",value=cams)
	# simply kill ffmpegs and segmenters (ffmpegs that are acquiring the RTSP streams will restart automatically)
	# this will also kill ffmpegs that are creating clip/thumbnail/etc - TOO BAD!
	# try:
	# 	success = not(os.system('killall '+c.ffname+' >/dev/null 2>/dev/null') or os.system('killall '+c.segname+' >/dev/null 2>/dev/null'))
	# except:
	# 	success = False
	# return success
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

# returns next available camera index that can be used 
# based on the camera list provided
def _nextIndex(camlist):
	camIDs = []
	# get a list of all camera IDs
	for cam in camlist:
		if('idx' in camlist[cam]):
			camIDs.append(camlist[cam]['idx'])
	# find any 'gaps' - next available id that can be used
	# e.g. active cameras might be in this order: cam0, cam2, cam3 (if cam1 was disbled previously)
	# so findGap will return 1
	# if no gaps exist, find the next available id
	return _findGap(sorted(camIDs))
#end nextIndex

# finds a gap or returns the next available number based on a list
def _findGap(numlist):
	idx = -1 #initialize it in case numlist is empty
	# consecutive search is on par or faster than binary search for N<16
	# for this case N will be no more than 8 (since it's number of cameras)
	for idx in xrange(len(numlist)):
		if(numlist[idx]!=idx):
			return idx
	return idx+1