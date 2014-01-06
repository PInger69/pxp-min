#!/usr/bin/python

# pXp List monitor
# monitors list.m3u8 file for dropped connection/pause 
# and inserts discontinuities as appropriate

from twisted.internet import reactor, protocol, task
from twisted.protocols import basic
from tendo import singleton

lastSegm = 0
lastModified = 0
listPath = "/var/www/html/events/live/video/list.m3u8"
# file monitor variable used for scheduling tasks
fm 	= None
monitoring = False

def dlog(text):
	print text
	pass

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
		if (line[:7]=='#EXTINF'):
			# this line contains time
			try:
				lastNum=float(re.search('[0-9\.]+', line).group())
			except:
				lastNum=-1
				pass
	return lastNum
#end getLastSeg

def onTimer():
	global lastSegm, listPath, lastModified
	import os
	# check if the file was modified
	if(not os.path.exists(listPath)):
		return
	finfo = os.stat(listPath)
	newModified = finfo.st_mtime
	dlog(newModified)
	if ((newModified-lastModified)<=0):
		# file was not changed
		return
	dlog('file changed')
	lastModified = newModified
	# FILE WAS CHANGED (probably just added a new segment)
	# get the new segment
	newSeg = getLastSeg()
	dlog(newSeg)
	dlog(lastSegm)
	# check if it's significantly different from the other segments
	if(abs(newSeg-lastSegm)>=0.01):
		#new segment is significantly different from the previous one - add discontinuity after it
		os.system("echo '#EXT-X-DISCONTINUITY' >> "+listPath)
	lastSegm = newSeg
	# dlog(newSeg)

me = singleton.SingleInstance() #make sure there is only 1 instance of this script running
l = task.LoopingCall(onTimer) #set up a function to execute periodically
l.start(0.25) #execute onTimer() every 1/4 seconds
reactor.run()