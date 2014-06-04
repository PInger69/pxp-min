#!/usr/bin/python
#export all tags with a specified name from all events
import pxp, os, pxputil as pu

def clipTag(evtPath,tag,outName):
	# get time:
	tmStart = str(int(tag['starttime']))
	duration= str(int(tag['duration']))
	outFile = outName+'_'+(tag['name'].replace(' ','_'))+'.mp4'
	if(os.path.exists(evtPath+"/video/main.mp4")):
		# extract from mp4 file
		cmd = "ffmpeg -ss "+tmStart+" -i "+evtPath+"/video/main.mp4 -t "+duration+" -codec copy "+outFile
		pass
	print ".............."
	print cmd
	print tag['name'], tmStart, duration,'...'
	os.system(cmd)
	if(not os.path.exists(outFile)):
		# could not create file from the full mp4 game, try to extract it from the segments
		pass
	print ".............."
tagname = "goal"
# get all events in this folder:
evtDir = "/users/dev/Desktop/sacPXPfield.events/"
dirs = os.listdir(evtDir)
tagNum = 1
outPath = "/users/dev/Desktop/clips"
if(not os.path.exists(outPath)):
	pu.disk.mkdir(outPath)
for evt in dirs:
	evtPath = evtDir+evt
	if(not (os.path.exists(evtPath+"/pxp.db") and (os.path.exists(evtPath+"/video/main.mp4") or os.path.exists(evtPath+"/video/list.m3u8")))):
		continue #skip non-event folders
	db = pu.db(evtPath+"/pxp.db")
	if(not db):
		continue
	# print evtPath
	# get all tags, matching the specified one
	sql = "SELECT * FROM `tags` WHERE `name` LIKE ?"
	db.query(sql,("%"+tagname+"%",))# % are wildcards to make sure and grab all tags containing that word
	tags = db.getasc()
	for tag in tags:
		# extract clip from this tag and save it
		clipTag(evtPath,tag,outPath+"/"+tagname+str(tagNum).zfill(4))
		tagNum+=1
#end for evt in evtDirs