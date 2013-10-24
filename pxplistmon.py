#!/usr/bin/python

# pXp List monitor
# monitors list.m3u8 file for dropped connection/pause 
# and inserts discontinuities as appropriate

from twisted.internet import reactor, protocol, task
from twisted.protocols import basic

lastSegm = 0
listPath = "/var/www/html/events/live/video/list.m3u8"
# file monitor variable used for scheduling tasks
fm 	= None
monitoring = False

def dlog(text):
	print text

def sockRead(udpAddr="127.0.0.1", udpPort=2224, timeout=0.8, sizeToRead=1):
	import socket
	sock = socket.socket(socket.AF_INET, # Internet
						 socket.SOCK_DGRAM) # UDP
	sock.settimeout(timeout) #wait for 'timeout' seconds - if there's no response, server isn't running
	#bind to the port and listen
	try:
		sock.bind((udpAddr, udpPort))
		data, addr = sock.recvfrom(sizeToRead)
	except Exception as e:
		# print e
		#failed to bind to that port or timed out on receiving - no data sent
		data = 0
	#close the socket
	try:
		sock.close()
	except:
		#probably failed because bind didn't work - no need to worry
		pass
	# dlog(data)
	return data
# sends msg to the specified socket

# returns the last segment listed in the m3u8 file
def getLastSeg():
	global listPath
	import subprocess, re
	# get last few lines of the file (no need to iterate through the entire file)
	p = subprocess.Popen(['tail', listPath], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	lines, err = p.communicate()
	lastNum = 0
	# go through the last few lines of the file
	for line in lines.split("\n"):
		if (line[:4]=='segm'):
			# this line contains the segment name
			try:
				lastNum = int(re.search('[0-9]+', line).group())
			except:#could not extract number from the line (something wrong)
				pass
	return lastNum
#end getLastSeg

# monitors the file (when stream is paused)
def fileMon():
	import os
	global listPath, lastSegm, monitoring, fm
	if(not os.path.exists(listPath)):#the file does not exist - no live event
		return 
	if(getLastSeg()>lastSegm):
		lastSegm = getLastSeg()
		dlog("restarted streaming")
		os.system("echo '#EXT-X-DISCONTINUITY' >> "+listPath)
		fm.stop()
		monitoring = False
#end fileMon

# function called with ever timer tick that resends any unreceived events and deletes old ones
def onTimer():
	global listPath, monitoring, fm
	import os
	if (monitoring): #if already monitoring the segment file then don't start another monitor
		dlog("already monitoring")
		return
	if(int(sockRead())): #the data is streaming, do not do anything
		dlog("streaming")
		return
	# did not receive a packet, start monitoring list file
	if(not os.path.exists(listPath)):#the file does not exist - no live event
		dlog("no file")
		return 
	monitoring = True
	dlog("not streaming")
	# remember the segment where the video stopped
	lastSegm = getLastSeg()
	#start file monitor
	fm = task.LoopingCall(fileMon) #set up a function to execute periodically
	fm.start(0.5) #execute onTimer() every 1/2 seconds
#end on Timer

# reactor.listenTCP(2232, PubFactory()) #listen to socket connections on port 2232
l = task.LoopingCall(onTimer) #set up a function to execute periodically
l.start(2.0) #execute onTimer() every 2 seconds
reactor.run()