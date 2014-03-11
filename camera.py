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
	# check if blackmagic device is connected
	if(not os.path.exists("/Applications/pxpStream.app")):
		# streaming app does not exist - this server was not configured for BlackMagic H.264 Pro Recorder
		return {}
	# the app exists, find out the status of the pro recorder
	if (not pdisk.psOn("pxpStream.app")):
		os.system("/usr/bin/open /Applications/pxpStream.app")
	# wait for the app to update the status
	timeout = 15 #wait for maximum of 15 seconds to get the bm status
	while (_bmStatus()=='unknown' and timeout>0):
		sleep(1)
		timeout -= 1
	return {'blackmagic':{'format':'mpegts','url':'udp://127.0.0.1:2290','status':_bmStatus()}}
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

# start an encode from all cameras
def camStart():
	import os
	# make sure encode is not already running
	if(camStatus()=='live' or camStatus=='paused'):
		return False
	# make sure no cameras are active
	camStop()

	# reset all cameras - in case some encoders changed their ip address
	camOff()
	sleep(1)
	camOn()
	# get active cameras
	cameras = getOnCams()
	if(len(cameras)<1): #no cameras active
		return False


	# to acquire multiple streams, just add them with -i to ffmpeg and output with -map 0, -map 1, etc... e.g.:
	# ffmpeg -y -i rtsp://192.168.1.107/stream1 -i rtsp://192.168.1.107/quickview \
	# -map 0 -vcodec copy -acodec copy out.mp4 \
	# -map 1 -vcodec copy -an low.mp4

	# hls (media segmenter) parameters
	# & at the end puts it in the background mode - so that the execution won't halt because of it
	# -p 		: create VOD
	# -t 1s 	: segment duration (1 second)
	# -S 1 		: start first segment file at ______1.ts
	# -B segm 	: name segment files as segm*.ts
	# -i list  	: the list file will be named as list.m3u8
	# -f ... 	: directory to output the segments
	# -127.0.0.1:2222 	: listen on port 2222 of local host to incoming UDP packets
	#>/dev/null &		: throw all output to null, & at the end puts it in background process (so python doesn't stop)

	# ffmpeg parameters:
	# -f mpegts: format of the video
	# -i 'udp....':  input file/stream (the udp port is the one to which this app sends packets)
	# -re : maintain the frame rate
	# -y : overrite output file without asking
	# -strict experimental: needed to have proper mp4 output
	# -vcodec copy: do not reincode video
	# -f mp4: MP4 format
	# /var/www/.....mp4: output file
	# 2>/dev/null: redirect output to null, 2 since ffmpeg outputs to stderr not stdout
	# &: put the execution in background mode - do not stop python execution

	# first ffmpeg acquires rtsp stream from all teradeks 
	# and re-streams it to local udp ports for HLS segmenter (2200, 2201, 2202..., etc)
	# and to the second ffmpeg for mp4 recording (2210, 2211, 2212..., etc)
	# info on ports:
	# 220X - HLS segmenters listening here (MPEG-TS)
	# 221X - ffmpeg mp4 recording listening here (H.264)
	# 223X - socket communication pxpservice listens here
	# 224X - blue screen for mp4 when a camera drops off (ffmpeg sends blue screen video here in H.264 format)
	# 225X - blue screen for segmenter (ffmpeg sends blue screen video here in MPEG-TS format)
	# 227X - rtsp/rtmp stream is sent here for mp4 (H.264)
	# 228X - rtsp/rtmp stream is sent here for hls (MPEG-TS)
	# 229X - where BM streams its packets (pxpStream.app sends packets here in MPEG-TS format)
	# ffstreamIns = []
	# ffmp4Ins = c.ffbin+" -y "
	# ffmp4Out = ""
	# segmenters = []
	# streamid = 0
	for devID in cameras:
		cameras[devID]['state'] = 'live'
	pdisk.sockSend('STR',addnewline=False)
	# update camera statuses on the disk
	pdisk.cfgSet(section="cameras",value=cameras)
	sleep(3) #wait for 3 seconds before returning result - to make sure streams start up properly
	return True
	#for device in camras
	# success = True
	# # start the HLS segmenters
	# for cmd in segmenters:
	# 	success = success and not os.system(cmd)
	# for cmd in ffstreamIns:
	# 	success = success and not os.system(cmd)
	# # start the mp4 recording ffmpeg
	# success = success and not os.system(ffmp4Ins+ffmp4Out+" 2>/dev/null >/dev/null &")
	# # start an ffmpeg that outputs blue screen (as a fallback for losing encoder/camera)
	# # only needs 1 port for mp4 and segmenter since the individual camera ports will be forwarded in pxpservice
	# ffBlue = c.ffbin+" -loop 1 -y -re -i "+c.approot+"/bluescreen.jpg -r 30 -vcodec libx264 -an -shortest -f h264 udp://127.0.0.1:2240 -r 30 -vcodec libx264 -vbsf h264_mp4toannexb -f mpegts udp://127.0.0.1:2250"
	# success = success and not os.system(ffBlue+" 2>/dev/null >/dev/null &")

	# return success
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
	for camID in cameras:
		if(cameras[camID]['state']=='live'):
			return 'live'
		if(cameras[camID]['state']=='paused'):
			return 'paused'
	if(len(cameras)<1): #when no cameras present, return False as status
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