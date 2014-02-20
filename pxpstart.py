#/usr/bin/python
###################################
# this script starts all required #
# processes, initializes cameras  #
###################################

import camera, os, constants as c, time
# remove any old cameras that might have been active
try:
	camera.camOff()
except:
	pass

# remove any teradeks that were identified previously
try:
	os.remove(c.tdCamList)
except:
	pass
# start pxpservice (in case it wasn't started before)
# no harm here - it's a singleton, so it won't start more than one instance
if(os.path.exists(c.approot+"pxpservice.py")):
	os.system("/usr/bin/python "+c.approot+"pxpservice.py &")
else:
	os.system("/usr/bin/python "+c.approot+"pxpservice.pyc &")
#wait until pxpservice creates a new camera list
while(not os.path.exists(c.tdCamList)):
	time.sleep(1)
# activate all teradeks found
try:
	camera.camOn()
except:
	pass