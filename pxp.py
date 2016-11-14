from time import sleep
from datetime import datetime as dt
import pxputil as pu, constants as c, os, json, re, shutil, sys, subprocess, time, glob
import pprint as pp
#from scipy.interpolate.interpolate import ppform
from test.test_socket import try_address
import threading
import dicttoxml
from xml.dom.minidom import parseString

#######################################################
#######################################################
################debug section goes here################
#######################################################
#######################################################
def alll():
	""" creates a bunch of random tags in the live event 
		Args:
			none
		API args:
			none
		Returns:
			none
	"""
	from random import randrange as rr
	# tags = ["MID.3RD", "OFF.3RD", "DEF.3RD"]
	tags = ["purple","teal","cyan","white","yellow","black","blue","red","pink"]
	colours = ["FF0000","00FF00","0000FF","FF00FF","00FFFF","FFFF00","333366","FFFFFF"]
	pu.sstr.pout("")
	vidlen = _thumbName(totalTime=True)
	for i in range(0,1000):
		col = colours[i % len(colours)]
		tstr = '{"name":"'+tags[i%len(tags)]+'","colour":"'+col+'","user":"356a1927953b04c54574d18c28d46e6395428ab","time":"'+str(rr(10,vidlen))+'","event":"live"}'
		print(tagset(tstr))
#######################################################
#######################################################
###################end of debug section################
#######################################################
#######################################################

def auth():
	""" Verify a customer authorization ID.
		Args:
			none
		API args:
			id(str): customer authorization ID given by the cloud to a device
		Returns:
			(dictionary): 
				success(bool): whether the user is authenticated
				config: pre-roll and post-roll time (Richard requested. June 14, 2016)
	"""
	try:
		# return _err("invalid id")
		pu.mdbg.log("-->auth")
		cfg = _cfgGet()
		if(not cfg):
			return {"success":False}
		authorization = cfg[1]
		customerID = cfg[2]
		resp = pu.uri.segment(3)
		if(not resp): #authorization ID wasn't passed through URL, check if it was passed as a form parameter
			queryID = pu.io.get('id')
		else:
			queryID = json.loads(resp)
			queryID = queryID['id']

		# added task to get pre-roll/post-roll time
		config = settingsGet()
		if ('tags' in config and 'preroll' in config['tags']):
			preroll = int(config['tags']['preroll'])
		if ('tags' in config and 'postroll' in config['tags']):
			postroll = int(config['tags']['postroll'])
		min_config = {'preroll':preroll, 'postroll': postroll}
		result = {}
		result['config'] = min_config
		result['success'] = customerID==queryID
		pu.mdbg.log("auth-->qid:{} result:{}".format(queryID, result))
		return result # {"success":customerID==queryID}
	except Exception as e:
		pu.mdbg.log("[---] error in auth: {}".format(str(sys.exc_info()[-1].tb_lineno)+' '+str(e)))
		return {"success":False, 'config':{}}
	
def checkspace():
	""" checks if there is enough space on the hard drive if there isn't, stops whatever encode is going on currently.
		Args: 
			none
		API args: 
			none
		Returns: 
			bool: true if there is enough free space, false otherwise.
	"""
	# find how much free space is available
	diskInfo = _diskStat(humanReadable=False)
	enoughSpace = diskInfo['free']>c.minFreeSpace
	# if there's not enough, stop the current encode
	if(not enoughSpace):
		encstop()
	return enoughSpace
#end checkspace

def coachpick(sess):
	""" creates a coach pick tag at live
		Args:
			sess(obj): session object passed by the controller - it's used to get the user information
		API args:
			none
		Returns:
			(dictionary): see _tagFormat description
	"""
	pu.mdbg.log("-->coachpick")
	import glob
	# make sure there is a live event
	if(not os.path.exists(c.wwwroot+'live/video')):
		return _err("no live event")
	if(_stopping()):
		return _stopping(msg=True)
	# get logged in user
	user = sess.data['user'] # user HID
	if(not os.path.exists(c.wwwroot+'_db/pxp_main.db')):
		return _err("not initialized")
	# get his tag colour from the database
	db = pu.db(c.wwwroot+'_db/pxp_main.db')
	sql = "SELECT `tagColour` FROM `users` WHERE `hid` LIKE ?"
	db.query(sql,(user,))
	users = db.getasc()
	# make sure this user is in the database
	if(len(users)<1):
		return _err("invalid user")
	colour = users[0]['tagColour']
	# get the total video time minus a couple seconds (to make sure that .ts file already exists)
	tagTime = _thumbName(totalTime=True)-2 
	try:
		tagnum = int(pu.uri.segment(3,"1"))
	except Exception as e:
		tagnum = 1
	# create tag
	tagStr = '{"name":"Coach Tag '+str(tagnum)+'","colour":"'+colour+'","user":"'+user+'","time":"'+str(tagTime)+'","event":"live","coachpick":"1"}'
	return dict(tagset(tagStr),**{"action":"reload"})

def _dbdump():
	""" PRIVATE. performs a pxp_main.db dump into a json 
		Args:
			none
		API args:
			none
		Returns:
			none
	""" 
	try:
		db = pu.db(c.wwwroot+"_db/pxp_main.db")
		output = {}
		# get events from database
		sql = "SELECT * FROM events"
		db.qstr(sql)
		output["events"] = db.getasc()

		sql = "SELECT * FROM leagues"
		db.qstr(sql)
		output["leagues"] = db.getasc()
		# get summary from database
		sql = "SELECT * FROM summary"
		db.qstr(sql)
		output["summary"] = db.getasc()
		# get teams from database
		sql = "SELECT * FROM teams"
		db.qstr(sql)
		output["teams"] = db.getasc()
		# get teamsetup from database
		sql = "SELECT * FROM teamsetup"
		db.qstr(sql)
		output["teamsetup"] = db.getasc()
		# get users from database
		sql = "SELECT * FROM users"
		db.qstr(sql)
		output["users"] = db.getasc()
		db.close()
		return {"data":output}
	except Exception as e:
		print "[---]dbdump",e,sys.exc_info()[-1].tb_lineno

#######################################################
# easter egg - prints the comparison features list 
#######################################################
def dlprogress():
	""" DEPRECATED. Gets download progress from the progress file, sums up all the individual progresses (if downloading to multiple ipads) and outputs a number
		Args:
			none
		API args:
			none
		Returns:
			(dictionary): 
				progress(int): total progress in percent
				status(int): numeric status of the download
	"""
	#get progress for each device
	progresses = pu.disk.file_get_contents("/tmp/pxpidevprogress")
	copyStatus = pu.disk.file_get_contents("/tmp/pxpidevstatus")

	totalPercent = 0
	numDevices   = 1 #number of devices connected - do not set this to zero to avoid 0/0 case
	# check if the idevcopy is running 
	if(not (pu.disk.psOn("idevcopy") or progresses or copyStatus)):
		return {"progress":0,"status":-1}
	if (not progresses): #file doesn't exist
		return {"progress":totalPercent, "status":copyStatus}
	progresses = progresses.strip().split("\n")
	numDevices = len(progresses)		
	#go through each one
	for progress in progresses:
		if(len(progress)<=5 or len(progress.split("-"))<2):
			continue #skip empty/erroneous lines in the file
		# extract percentage from the line (right before -)
		percentNum = int(progress.split("-")[0])
		totalPercent += percentNum
	pu.mdbg.log("-->dlprogress:{}/{}",format(totalPercent,numDevices))
	return {"progress":int(totalPercent/numDevices),"status":copyStatus}
#end dlprogress
#######################################################
# easter egg - prints the comparison features list 
#######################################################
def showlive():
	r = """
<button id="b1" onclick="myvid()">PLAY</button>

<table border="1">
       <tr>
           <td>
<video id="my_video1"></video>
           </td>
           <td>
<video id="my_video2"></video>
           </td>
       </tr>
       <tr>
           <td>
<video id="my_video3"></video>
           </td>
           <td>
<video id="my_video4"></video>
           </td>
       </tr>
</table>

<script src="./mon/jwplayer.js"></script>

<script>

var pxp_ip="127.0.0.1";

function play_vid() {
    jwplayer('my_video1').play(true);
}

function myvid() {
    jwplayer('my_video1').setup({
        file: 'http://' + pxp_ip + '/events/live/video/list_00hq.m3u8',
    });

    jwplayer('my_video2').setup({
        file: 'http://' + pxp_ip + '/events/live/video/list_01hq.m3u8',
    });

    jwplayer('my_video3').setup({
        file: 'http://' + pxp_ip + '/events/live/video/list_02hq.m3u8',
    });

    jwplayer('my_video4').setup({
        file: 'http://' + pxp_ip + '/events/live/video/list_03hq.m3u8',
    });

    jwplayer('my_video1').play(true);
    jwplayer('my_video2').play(true);
    jwplayer('my_video3').play(true);
    jwplayer('my_video4').play(true);

    // Add a custom callback for when user pauses playback
    jwplayer('my_video1').on('pause', function(event) {
        //alert('Why did my user pause their video instead of watching it?');
        var x = 1;
    });
}
</script>	
	"""
	return r
def msplayer():
	r = """
	<!DOCTYPE html>
	<html>
	<head>
	<meta charset="utf-8">
	<meta http-equiv="X-UA-Compatible" content="IE=edge">
	<title>Azure Media Player</title>
	<meta name="description" content="">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	
	<!--*****START OF Azure Media Player Scripts*****-->
	    <!--Note: DO NOT USE the "latest" folder in production. Replace "latest" with a version number like "1.0.0"-->
	    <!--EX:<script src="//amp.azure.net/libs/amp/1.0.0/azuremediaplayer.min.js"></script>-->
	    <!--Azure Media Player versions can be queried from //amp.azure.net/libs/amp/latest/docs/changelog.html-->
	<link href="http://amp.azure.net/libs/amp/latest/skins/amp-default/azuremediaplayer.min.css" rel="stylesheet">
	<script src="http://amp.azure.net/libs/amp/latest/azuremediaplayer.min.js"></script>
	<!--*****END OF Azure Media Player Scripts*****-->
	
	</head>
	<body>
	
	<video id="azuremediaplayer" class="azuremediaplayer amp-default-skin amp-big-play-centered" controls autoplay width="800" height="475" poster="" data-setup='{"logo": { "enabled": false}, "techOrder": ["azureHtml5JS", "flashSS", "silverlightSS", "html5"], "nativeControlsForTouch": true' tabindex="0">
	    <source src="http://mymedia2svc.streaming.mediaservices.windows.net/ce12a70c-d8e3-4274-be53-50cd2dc2ab16/main_00hq.ism/Manifest" type="application/vnd.ms-sstr+xml" />
	    <p class="amp-no-js">To view this video please enable JavaScript, and consider upgrading to a web browser that supports HTML5 video</p>
	</video>
	
	
	</body>
	</html>	"""	
	return r
def egg():
	r = """
	<div class="col_3">
		<!-- left-most side -->
	</div>
	<div class="col_6">
		<!-- center  -->
		<div class="row bold border-bottom large">
			<div class="col_6 bold">feature</div>
			<div class="col_3">NEW</div>
			<div class="col_3">OLD</div>
		</div>
		<div class="row">
			<div class="col_6 bold">UI/UX response speed</div>
			<div class="col_3"><1s</div>
			<div class="col_3">3-5s</div>
		</div>
		<div class="row">
			<div class="col_6 bold">App updates</div>
			<div class="col_3">simple</div>
			<div class="col_3">complex</div>
		</div>
		<div class="row">
			<div class="col_6 bold">UI design</div>
			<div class="col_3">clean</div>
			<div class="col_3">OMGWTHBBQ</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Encoder installation time</div>
			<div class="col_3">10 minutes (automatic)</div>
			<div class="col_3">2 - 4 hours (manual)</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Video bitrate (quality)</div>
			<div class="col_3">1 - 5 mbps (customizable)</div>
			<div class="col_3">1 mbps (fixed)</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Encode start time</div>
			<div class="col_3">2-4 seconds</div>
			<div class="col_3">2 minutes</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Post-encode delay</div>
			<div class="col_3">2-4 seconds</div>
			<div class="col_3">2-5 minutes</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Encoder computer access</div>
			<div class="col_3">not required</div>
			<div class="col_3">required</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Video source identification</div>
			<div class="col_3">automatic</div>
			<div class="col_3">manual</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Accidental camera disconnect</div>
			<div class="col_3">handled - resume</div>
			<div class="col_3">not handled - content lost</div>
		</div>
		<div class="row">
			<div class="col_6 bold">3hr-game file size</div>
			<div class="col_3">3gb</div>
			<div class="col_3">4-5gb</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Discrete clip export</div>
			<div class="col_3 green large"><i class="icon-ok"></i></div>
			<div class="col_3 red large"><i class="icon-remove"></i></div>
		</div>
		<div class="row">
			<div class="col_6 bold">Automatic encoder recognition</div>
			<div class="col_3 green large"><i class="icon-ok"></i></div>
			<div class="col_3 red large"><i class="icon-remove"></i></div>
		</div>
		<div class="row">
			<div class="col_6 bold">Audio</div>
			<div class="col_3 green large"><i class="icon-ok"></i></div>
			<div class="col_3 red large"><i class="icon-remove"></i></div>
		</div>
		<div class="row">
			<div class="col_6 bold">Timeline scrubbing</div>
			<div class="col_3 green large"><i class="icon-ok"></i></div>
			<div class="col_3 red large"><i class="icon-remove"></i></div>
		</div>
		<div class="row">
			<div class="col_6 bold">Pause encoding</div>
			<div class="col_3 green large"><i class="icon-ok"></i></div>
			<div class="col_3 red large"><i class="icon-remove"></i></div>
		</div>
		<div class="row">
			<div class="col_6 bold">Touch gestures</div>
			<div class="col_3 green large"><i class="icon-ok"></i></div>
			<div class="col_3 red large"><i class="icon-remove"></i></div>
		</div>
		<div class="row">
			<div class="col_6 bold">Airplay</div>
			<div class="col_3 green large"><i class="icon-ok"></i></div>
			<div class="col_3 red large"><i class="icon-remove"></i></div>
		</div>
		<div class="row">
			<div class="col_6 bold">Slow motion playback</div>
			<div class="col_3 green large"><i class="icon-ok"></i></div>
			<div class="col_3 red large"><i class="icon-remove"></i></div>
		</div>
		<div class="row">
			<div class="col_6 bold">Source code security</div>
			<div class="col_3">PYC - no access</div>
			<div class="col_3">PHP - open source</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Tag thumbnail delay</div>
			<div class="col_3">2-3 seconds</div>
			<div class="col_3">30 seconds</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Tag accuracy</div>
			<div class="col_3">0-1 seconds</div>
			<div class="col_3">*10-30 seconds</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Live video delay</div>
			<div class="col_3">5-6 seconds</div>
			<div class="col_3">12 seconds</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Encoder Compatibility</div>
			<div class="col_3">BM, Teradek, Matrox</div>
			<div class="col_3">BM</div>
		</div>
		<div class="row">
			<div class="col_6 bold">CPU cost</div>
			<div class="col_3">$600</div>
			<div class="col_3">$2000</div>
		</div>
		<div class="row">
			<div class="col_6 bold">OS Compatibility</div>
			<div class="col_3">OSX, Windows, Linux</div>
			<div class="col_3">Windows</div>
		</div>
		<div class="row">
			<div class="col_6 bold">Apple Approval</div>
			<div class="col_3 green large"><i class="icon-ok"></i></div>
			<div class="col_3 red large"><i class="icon-remove"></i></div>
		</div>
		* on 1s HLS fragment size
	</div>
	<div class="col_3">
		<!-- right-most side -->
	</div>
	"""
	return r
#end egg

def getlastlist(fname):
	try:
		line = ''
		f=file(fname,"rb")
		f.seek(-100,os.SEEK_END)
		line=f.readlines()[-1]
		return line
	except Exception as e:
		return line
	
def encstatsyncme(textOnly=True):
	""" Combination with syncme and encstatus
	""" 
	try:
		strParam = pu.uri.segment(3,"{}")
		jp = json.loads(strParam)
		if not ('user' in jp and 'event' in jp and 'device' in jp):
			return _err("Specify user, event, and device")
		param_print = pu.pxpconfig.check_webdbg('param') and pu.pxpconfig.check_webdbg('encoderstatus')
		
		if (param_print):
			pu.mdbg.log("-->encstatsyncme: param-->", strParam)

		#get user id
		usr = jp['user']
		#device ID
		dev = jp['device']
		#event
		evt = jp['event']
		if(_stopping(evt)):
			return _stopping(msg=True)

		#----------------------------------------------------------------
		
		txtStatus = pu.disk.file_get_contents(c.encStatFile)
		if(not txtStatus):#this will only happen if the encoder is not initialized (or someone deleted the config file)
			enc = {'status':'','code':0}
		else:
			enc = json.loads(txtStatus)
		if(not 'status' in enc):
			state = 0
			status = "pro recorder disconnected"
		else:
			state = enc['code'] #1+2+4#+8+16 #encoder + camera + streaming + ffmpeg + 
			status = enc['status']
		resp = pu.disk.sockSendWait(msg="SNF|", addnewline=False)
		if(not resp):
			data = {}
		else:
			data = json.loads(resp)

		if (textOnly):
			return status
		
		encstatus = {"status":status,"code":state}
		encstatus.update(data)

		#--------------------------------------------------
		sync = _syncTab(user=usr, device=dev, event=evt)
		result = {}
		result['encstatus'] = encstatus
		result['syncme'] = sync
		if (param_print):
			pu.mdbg.log("-->encstatsyncme: user:{}  device:{}  event:{}  result:{}".format(usr, dev, evt, result))
		return result
	except Exception as e:
		import sys
		errmsg = _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno))
		pu.mdbg.log("[---]encstatsyncme err:".format(errmsg))
		return errmsg
	
def encoderstatus(textOnly=True):
	""" Outputs the encoder status.
		Args:
			textOnly(bool, optional): whether to print the status as text only or as json. default: True.
		API args:
			none
		Returns:
			(mixed): -text status (if textOnly requested)
					 -dictionary:
						 status(str): text status
						 code(int): numeric encoder status (see pxpservice.py for different numeric statuses)
	"""
	try:
		txtStatus = pu.disk.file_get_contents(c.encStatFile)
		if(not txtStatus):#this will only happen if the encoder is not initialized (or someone deleted the config file)
			enc = {'status':'','code':0}
		else:
			enc = json.loads(txtStatus)
		if(not 'status' in enc):
			state = 0
			status = "pro recorder disconnected"
		else:
			state = enc['code'] #1+2+4#+8+16 #encoder + camera + streaming + ffmpeg + 
			status = enc['status']
		resp = pu.disk.sockSendWait(msg="SNF|",addnewline=False)
		if(not resp):
			data = {}
		else:
			data = json.loads(resp)
			
# 		l_hq_ts = []
# 		l_hq = []
# 		for i in xrange(1):
# 			l_hq_ts.append(getlastlist(c.wwwroot+'live/video/list_' + str(i).zfill(2) + 'hq.m3u8'))
# 			if (l_hq_ts[i]!=''):
# 				l_hq.append(l_hq_ts[i].split('.'))
# 			else:
# 				l_hq.append('')
			
		if (textOnly):
			return status
		result = {"status":status,"code":state}
		result.update(data)
		
		if (pu.pxpconfig.check_webdbg('param') and pu.pxpconfig.check_webdbg('encoderstatus')):			
			pu.mdbg.log("---->encoderstatus:{}".format(result))
		
		return result
	except Exception as e:
		import sys
		return _err(str(sys.exc_info()[-1].tb_lineno)+' '+str(e)+ ' '+str(txtStatus))
		
def ipad_log(params=False):
	"""
	Typical http request looks like this: http://localhost/min/ajax/rec_stat/{"sidx":"00hq","event":"live"}
		sidx can have "*" instead of specific feed index such as 00hq 
	"""
	ipad_log_param = params
	if (not params):
		ipad_log_param = pu.uri.segment(3,"{}") # always GET command
	result = {"success":False, "msg":"ok"}
	try:
		pu.mdbg.log("ipad_log-->param:{}".format(ipad_log_param))
		param = json.loads(ipad_log_param)
		result['success'] = True
		if (('title' in param) and param['title'] and (len(param['title'])>1)):
			pu.disk.file_set_contents("/tmp/"+param['title'], param['txt'])
		else:
			imsi = str(time.time())
			pu.disk.file_set_contents("/tmp/"+imsi, param['txt'])
		pu.pxp_mail.send_alert(param['title'], param['txt'])
	except Exception as e:
		result['success'] = False
		result['msg'] = str(e)
		pu.mdbg.log("[---] error in ipad_log: {}".format(str(sys.exc_info()[-1].tb_lineno)+' '+str(e)))
	return result
	
def rec_stat(params=False):
	"""
	Typical http request looks like this: http://localhost/min/ajax/rec_stat/{"sidx":"00hq","event":"live"}
		sidx can have "*" instead of specific feed index such as 00hq 
	
	This reads the segment file creation time to provide the difference between the streaming start time
	"""
	recstat_param = params
	if (not params):
		recstat_param = pu.uri.segment(3,"{}") # always GET command
	#param:{"sidx":"*", "event":"live", "srclen":2, "evtpath":"f1aa0f0e67930d6d3ae5ad129a1df421916bba2a_local"}
	result = {"success":False, "msg":""}
	sIdx = "00hq"
	event = 'live'
	srclen = 0
	try:
		# prepare input params for processing
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("rec_stat-->param:{}".format(recstat_param))
		param = json.loads(recstat_param)
		
		# sanity check for input params
		if (not "sidx" in param):
			sIdx = "*"
		else:
			sIdx = param['sidx']
		if (not "event" in param):
			event = 'live'
		else:
			event = param['event']
		if (not "srclen" in param):
			srclen = 0
		else:
			srclen = param['srclen']
		evt_path = param['evtpath']
		
		try:
			resp = pu.disk.sockSendWait(msg="FCT|"+event,addnewline=False) # get feed count
			pu.mdbg.log("rec_stat-->FCT:{}".format(resp))
			if (srclen==0):
				srclen = int(resp)
		except:
			srclen = 0
		
		# Find all of folder it needs to get time data  i.e ['/var/www/html/events/live/video/hq_00/', '/var/www/html/events/live/video/lq_00']
		videoPath = c.wwwroot + event + '/video/'
		if (isAngleFolder(event)):
			if (sIdx == "*"):
				dirs = glob.glob(videoPath + "?q_??")
				for i in xrange(len(dirs)):
					dirs[i] = dirs[i] + "/"
			else:
				dirs = [c.wwwroot + event + '/video/' + getlivefeedfolder(sIdx)]
		else:
			dirs = [videoPath]

		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("rec_stat-->{}".format(dirs))

		# if not live event, cannot proceed
		if (not os.path.exists(c.wwwroot + event + '/video')): # check if live now
			result['success'] = False
			result['msg'] = "event is not started"
			pu.mdbg.log("rec_stat-->event is not started yet??")
			return result

		# Find all of the creation time and access time in first segment file(s) and store into {result}
		count = 0
		for d in dirs:
			if (os.path.isdir(d)):
				if (len(glob.glob(d + "list_*.m3u8")) > 0):
					for f in glob.glob(d + "list_*.m3u8"):
						i1=f.find('list_')
						i2=f.find('.m3u8')
						if (i1>=0 and i2>=0):
							sidx=f[i1+5:i2]
							#if (not pu.pxpconfig.virtual_lq_enabled() and event=='live' and sidx.find('lq')>0):
							if (not pu.pxpconfig.virtual_lq_enabled() and sidx.find('lq')>0):
								continue
							info = os.stat(d + sidx + '_segm_0.ts')
							#result['atime-'+sidx]=info[7]
							result[str('ctime-'+sidx)]=info[9]
							count += 1			
							if (pu.pxpconfig.check_webdbg('param')):			
								pu.mdbg.log("rec_stat--> f:{} sidx:{}  videopath:{} info:{}".format(f, sidx, videoPath, result))
		#result['freedisk'] = pu.disk.diskusage()
		if (srclen>0):
			result["success"] = (srclen==count)
		else:
			result["success"] = True
		result["msg"] = "{} of result(s) found".format(count)

        #-----------------------------------------------------------------------------------------
		# Now we need to add rec_stat into database so downloaded events can use those data
		# Right now, 'extra' field in events table is used for save data.
		rec_stat_str = json.dumps(result) 
		try:
			db = pu.db(c.wwwroot+"_db/pxp_main.db")
			sql = "SELECT * FROM `events` WHERE `hid` LIKE ?"
			db.query(sql,(evt_path,))
			eventData = db.getasc()
			db.close()
			if(len(eventData)>0):
				#eventPath = c.wwwroot+eventData[0]['datapath']
				db = pu.db(c.wwwroot+"_db/pxp_main.db")
				sql = "UPDATE `events` SET `extra`=? WHERE `hid`=?"
				success = db.query(sql,(rec_stat_str, evt_path))
				db.close()
				if (success):
					pu.mdbg.log("{} rec_stat db updated...".format(rec_stat_str))
				else:
					pu.mdbg.log("{} rec_stat db update FAILED...".format(rec_stat_str))
		except Exception as e:
			pu.mdbg.log("[---] rec_stat db update FAILED...{}".format(str(sys.exc_info()[-1].tb_lineno)+' '+str(e)))
			pass
	except Exception as e:
		pu.mdbg.log("[---] error in rec_stat: {}".format(str(sys.exc_info()[-1].tb_lineno)+' '+str(e)))
	return result

def enc_stat():
	"""
	returns disk free space in server	
	"""
	result = {"success":False, "msg":""}
	try:
		#enoughSpace = diskInfo['free']>c.minFreeSpace
		result = _diskStat(humanReadable=False)
		result['msg'] = ""
		result['success'] = True
	except Exception as e:
		pu.mdbg.log("[---] error in enc_stat: {}".format(str(sys.exc_info()[-1].tb_lineno)+' '+str(e)))
	return result

def encoderstatjson():
	""" Outputs the encoder status in json format.
		Args:
			none
		API args:
			none
		Returns:
			(dictionary):
				status(str): text status
				code(int): numeric encoder status (see pxpservice.py for different numeric statuses)
	"""
	return encoderstatus(textOnly = False)
def encpause():
	""" Pauses a live encode.
		Args:
			none
		API args:
			none
		Returns:
			(dictionary): 
				success(bool): whether the command was successful
				msg(str): error message (if applicable)
	"""
	import camera
	msg = ""
	rez = False
	try:
		if(_stopping()):
			return _stopping(msg=True)
		camera.camPause()
		# add entry to the database that the encoding has paused
		msg = _logSql(ltype="enc_pause",dbfile=c.wwwroot+"live/pxp.db")
		pu.disk.sockSend(json.dumps({'actions':{'event':'live','status':'paused'}}))
	except Exception as e:
		msg = str(e)
		rez = True
	# rez = False
	return {"success":not rez,"msg":msg}
#end encpause
def encresume():
	""" Resumes a (paused) live encode.
		Args:
			none
		API args:
			none
		Returns:
			(dictionary): 
				success(bool): whether the command was successful
				msg(str): error message (if applicable)
	"""
	import os, camera
	msg = ""
	rez = False
	try:
		if(_stopping()):
			return _stopping(msg=True)
		# add entry to the database that the encoding has paused
		camera.camResume()
		msg = _logSql(ltype="enc_resume",dbfile=c.wwwroot+"live/pxp.db")
		pu.disk.sockSend(json.dumps({"actions":{'event':'live','status':'live'}}))
		rez = False
	except Exception as e:
		return _err(str(e))
	# rez = False
	return {"success":not rez, "msg":msg}
#end encresume
def encshutdown():
	""" Shutds down the server.
		Args:
			none
		API args:
			none
		Returns:
			(dictionary): 
				success(bool): whether the command was successful
				msg(str): error message (if applicable)
	"""
	import os
	msg = ""
	try:
		pu.mdbg.log("min-encoder is shutting down...")
		if(os.path.exists(c.wwwroot+"live/evt.txt")):
			encstop() #there is a live event - stop it before shut down
		while(_stopping()):
			sleep(1) #wait until the live stream is stopped
		rez = os.system("sudo /sbin/shutdown -h now")
	except Exception as e:
		rez = False
	# rez = False
	return {"success":not rez, "msg":rez}
#end encresume
def encstart():
	""" Starts a new encode.
		Args:
			none
		API args:
			hmteam(str): name of the home team
			vsteam(str): name of the visitor team
			league(str): name of the league
		Returns:
			(dictionary): 
				success(bool): whether the command was successful
				msg(str): error message (if applicable)
	"""
	import os, camera
	try:
		pu.mdbg.log("\n\n\nENC_START------------------------->BEGINS")		
		success = True
		if(not os.path.exists(c.wwwroot+'_db/pxp_main.db')):
			return _err("not initialized")
		# if an event is being stopped, wait for it
		while(_stopping()):
			sleep(1)
		# make sure there is enough free space
		if(not checkspace()):
			return _err("Not enough free space to start a new encode. Delete some of the old events from the encoder.")
		pp_done = pu.disk.sockSendWait(msg="PPD|",addnewline=False)
		if (not pp_done):
			pu.mdbg.log("checking postproc status: not finished")
			return _err("Please wait until post event recording process is done.")
		pu.mdbg.log("checking postproc status: {}".format(pp_done))
		
		# make sure not overwriting an old event
		if(os.path.exists(c.wwwroot+"live/evt.txt")): #there was a live event before that wasn't stopped proplery - end it
			encstop()
		#make sure the 'live' directory was initialized
		_initLive()
		io = pu.io
		# get the team and league informaiton
		hmteam = io.get('hmteam')
		vsteam = io.get('vsteam')
		league = io.get('league')
		if not (hmteam and vsteam and league):
			return _err("Please specify teams and league")
		# create new event in the database
		# get time for hid and for database in YYYY-MM-DD HH:MM:SS format
		timestamp = _time()
		stampForFolder = timestamp.replace(":","-").replace(" ","_")

		minEvtHid = pu.enc.sha(_time(timeStamp=True))+'_local' #local event hid (temporary, will be updated when the event goes up to .Max)
		db = pu.db(c.wwwroot+"_db/pxp_main.db")
		#the name of the directory will be YYYY-MM-DD_HH-MM-SS_EVENTHID
		evtName = stampForFolder+'_'+minEvtHid#'_H'+hmteam[:3]+'_V'+vsteam[:3]+'_L'+league[:3]
		sql = "INSERT INTO `events` (`hid`,`date`,`homeTeam`,`visitTeam`,`league`,`datapath`) VALUES(?,?,?,?,?,?)"
		db.query(sql,(minEvtHid,timestamp,hmteam,vsteam,league,evtName))
		#store the event name (for processing when it's stopped)
		pu.disk.file_set_contents(c.wwwroot+"live/evt.txt",evtName)

		# get hid of the teams
		# home team
		sql = "SELECT `hid` FROM `teams` WHERE `name` LIKE ?"
		db.query(sql,(hmteam,))
		hmteamHID = db.getasc()
		hmteamHID = hmteamHID[0]['hid']
		# visitor team
		sql = "SELECT `hid` FROM `teams` WHERE `name` LIKE ?"
		db.query(sql,(vsteam,))
		vsteamHID = db.getasc()
		# return {"success":0,"msg":str(vsteamHID)+' -- '+vsteam}
		vsteamHID = vsteamHID[0]['hid']
		# get hid of the leagu
		sql = "SELECT `hid` FROM `leagues` WHERE `name` LIKE ?"
		db.query(sql,(league,))
		leagueHID = db.getasc()
		leagueHID = leagueHID[0]['hid']
		db.close()
		# add entry to the database that the encoding has started
		msg = _logSql(ltype="enc_start",lid=(hmteamHID+','+vsteamHID+','+leagueHID),dbfile=c.wwwroot+"live/pxp.db")
		pu.disk.sockSend(json.dumps({"actions":{'event':'live','status':'live'}}))
		# start encoder (run ffmpeg, segmenter, etc)
		success = success and camera.camStart(minEvtHid)
		evtHid=""
		if success:
			evtHid = minEvtHid
			# save the event ID
			pu.disk.file_set_contents(c.wwwroot+"live/eventid.txt",evtHid)
		#if success
		msg = ""
		pu.mdbg.log("ENC_START------------------------->DONE")		
	except Exception as e:
		import sys
		return _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno))
	return {"success":success,"msg":msg,"evthid":evtHid}
#end encstart
def encstop():
	""" Stops a live encode.
		Args:
			none
		API args:
			none
		Returns:
			(dictionary): 
				success(bool): whether the command was successful
				msg(str): error message (if applicable)
				bookmarking(bool): true if there are bookmarks (MyClip's) being generated
	"""
	import camera
	msg = ""
	try:
		pu.mdbg.log("ENC_STOP------------------------->BEGINS")		
		if(not os.path.exists(c.wwwroot+'live')):
			return _err('no live event to stop')
		timestamp = _time(timeStamp=True)
		rez = camera.camStop()
		
		# close any duration tags (lines, periods, etc.): set their duration to the end of the video
		# get the length of the video
		totalVidLength = _thumbName(totalTime=True)
		# update all the odd-type (start) tags to proper duration
		sql = "UPDATE `tags` SET `duration`=CASE WHEN (?-`time`)>0 THEN (?-`time`) ELSE 0 END, `type`=`type`+1 WHERE (NOT (`type`=3)) AND ((`type` & 1)=1)"
		db = pu.db(c.wwwroot+'live/pxp.db')
		db.query(sql,(totalVidLength,totalVidLength))
		db.close()

		# make sure nobody creates new tags or does other things to this event anymore
		os.system("echo '"+timestamp+"' > "+c.wwwroot+"live/stopping.txt")
		pu.disk.sockSend(json.dumps({"actions":{'event':'live','status':'stopped'}}))
		
		msg = _logSql(ltype="enc_stop",dbfile=c.wwwroot+"live/pxp.db")
		
		# rename the live directory to the proper event name
		_postProcess()
		# check if there are clips being generated
		# bookmarking = pu.disk.psOn("ffmpeg -ss") or pu.disk.psOn("handbrake") or pu.disk.psOn("ffmpeg -i")
		bookmarking = False
		pu.mdbg.log("ENC_STOP------------------------->DONE")		
	except Exception as e:
		bookmarking = False
		rez = False
		msg=str(e)
	return {"success":not rez,"msg":msg,"bookmarking":bookmarking}
#end encstop

def evtbackup():
	""" Sends a request to the service to backup specified event. The backup process itself takes place in pxpservice.py
		Args:
			none
		API args:
			event(str): name of the event to back up
		Returns:
			(dictionary): 
				success(bool): whether the command was successful
	"""
	try:
		pu.mdbg.log("-->evtbackup")
		# get id of the event to back up
		evtHID = pu.io.get('event')
		pu.mdbg.log("-->evtbackup:"+str(evtHID))
		_dbgLog("backup event:"+str(evtHID))
		if(re.search("[^A-z0-9]",str(evtHID))): #found non-alphanumeric characters
			_dbgLog("invalid characters in event HID")
			return _err("invalid event")
		# send request to service script to back up the event
		_sockData(data="BKP|"+evtHID+"|")
		return {"success":True}
	except Exception as e:
		return _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno))
def evtbackuplist():
	""" Request a list of events that were backed up locally
		Args:
			none
		API args:
			none
		Returns:
			(dictionary):
				events(list): list of backed up events with their backup paths
	"""
	try:
		pu.mdbg.log("-->evtbackuplist")
		# request events from the services
		resp = pu.disk.sockSendWait(msg="LBE|",addnewline=False)
		_dbgLog("answer:"+resp)
		# return them
		return {"events":json.loads(resp)}
	except Exception as e:
		return _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno))
def evtbackupstatus():
	""" Get status of an event that is being backed up (or restored)
		Args:
			none
		API args:
			event(str): hid of the event that is being backed up or recovered
		Returns:
			(list):
				[0]: copy status
				[1]: percent copied
	"""
	try:
		# get id of the event to back up
		evtHID = pu.io.get('event')
		_dbgLog("backup status:"+str(evtHID))
		if(re.search("[^A-z0-9]",str(evtHID))): #found non-alphanumeric characters
			_dbgLog("invalid characters in event HID")
			return _err("invalid event")
		resp = pu.disk.sockSendWait(msg="CPS|"+evtHID+"|",addnewline=False)
		_dbgLog("answer:"+str(resp))
		return json.loads(resp)
	except Exception as e:
		return _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno))
def evtrestore():
	""" Sends a request to the service to restore specified event. The process itself takes place in pxpservice.py
		Args:
			none
		API args:
			event(str): hid of the event to restore
		Returns:
			(dictionary): 
				success(bool): whether the command was successful
	"""
	try:
		pu.mdbg.log("-->evtrestore")
		# get id of the event to back up
		evtHID = pu.io.get('event')
		_dbgLog("restore event:"+str(evtHID))
		if(re.search("[^A-z0-9]",str(evtHID))): #found non-alphanumeric characters
			_dbgLog("invalid characters in event HID")
			return _err("invalid event")
		_sockData(data="RRE|"+evtHID+"|")
		#end for drive in drives
		return {"success":True}
	except Exception as e:
		return _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno))
  
def serverinfo():
	""" Get info about the encoder
		Args:
			none
		API args:
			none
		Returns:
			(dictionary): 
				version(str): encoder version
				settings(dictionary): dictionary containing settings available on this encoder
				master(bool): whether this device is master
				down(bool): this will be added when service is down, and it'll be set to true
				alarms(list): returns list of cameras that have alarm triggered
	"""
	pu.mdbg.log("-->serverinfo")
	result = {"version":c.ver}
	try:
		resp = json.loads(pu.disk.sockSendWait(msg="SNF|",addnewline=False,timeout=3))
		settings = pu.disk.cfgGet(section="sync")
		result.update(resp)
		result['settings']=settings		
	except:
		result["settings"]={}
		result["master"]=False
		result['down']=True
	return result
	# return {"settings":settings,"master":resp}
#end serverinfo
def evtsynclist():
	""" Get a list of files to sync for a specified event
		Args:
			none
		API args:
			event(str): hid of the event to back up
			full(bool): whether to return full directory tree (segments and thumbnails) or just thumbnails
		Returns:
			(dictionary): 
				entries(list): list of relative paths to each file
	"""
	try:
		pu.mdbg.log("-->evtsynclist")
		# get id of the event to back up
		evtHID = pu.io.get('event')
		fullView = pu.io.get('full')
		if(fullView):
			fullView = int(fullView) #if fullview was set, convert it to a number to determine if user actually wants fullview
		if(re.search("[^A-z0-9]",str(evtHID))): #found non-alphanumeric characters
			_dbgLog("invalid characters in event HID")
			return _err("invalid event")
		# get the directory for this event
		db = pu.db(c.wwwroot+"_db/pxp_main.db")
		sql = "SELECT * FROM `events` WHERE `hid` LIKE ?"
		db.query(sql,(evtHID,))
		eventData = db.getasc()
		db.close()
		if(len(eventData)<=0):#there is no data
			return _err("invalid event")
		path = eventData[0]['datapath']
		# prepare the event.json file
		eventString = json.dumps(eventData[0])
		if(not os.path.exists(c.wwwroot+path)): #the event path does not exist
			tree = []
		else:#the path exists
			pu.disk.file_set_contents(c.wwwroot+path+"/event.json",eventString)
			if(fullView):
				# return full directory tree
				tree = pu.disk.treeList(c.wwwroot+path,prefix="/events/"+path+'/')
			else:
				# return only data directory tree
				# thumbnails
				tree = pu.disk.treeList(c.wwwroot+path+'/thumbs',prefix="/events/"+path+'/thumbs/')
				# data
				tree.append('/events/'+path+'/pxp.db')
				# event info
				tree.append('/events/'+path+'/event.json')
		return {"entries":tree}
	except Exception as e:
		return _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno))

def ejectusbdrv():
	"""
	Send EJT command to the service (Eject USB) - not used anymore
	"""
	try:
		io = pu.io
		name = io.get('name')
  		pu.mdbg.log("ejectusbdrv--> name:", name)
		#os.system('diskutil eject /Volumes/NO\ NAME')
		resp = pu.disk.sockSendWait(msg="EJT|")
	except Exception as e:
		pu.mdbg.log("[---]ejectusbdrv-->{0}".format(e))

def ejtprogress():
	"""
	USB eject callback (via EJS) - not used anymore
	"""
	try:
		io = pu.io
		stat = io.get('a1') # input arg1,arg2
		name = io.get('a2')
		status = -1;
		#{'status':T/F, 'progress':n, 'msg':'ejecting usb drive'}
		resp = pu.disk.sockSendWait(msg="EJS|",addnewline=False)
		return {"results":json.loads(resp)}
	except Exception as e:
		res = {'status':False, 'progress':9999, 'msg':'ejecting usb drive'}
		return {"results":json.loads(res)}

def usbmounted():
	"""
	Check USB storage status attached for backup/restore purpose  
	"""
	resp = '{"status":False}'
	try:
		resp = pu.disk.sockSendWait(msg="USB|",addnewline=False)
		#return {"results":json.loads(resp)} #json.dumps(resp)
		s = "{'results':"+json.dumps(resp)+"}"
		return json.JSONEncoder().encode(json.loads(s.replace("'", "\"")))
	except Exception as e:
		pu.mdbg.log("[---] usbmounted:{}".format(e))		
		return json.JSONEncoder().encode(json.loads(resp.replace("'", "\"")))

def retry_pxpcmd(cmd=False,param=False,resp=False,sockWait=True):
	try:
		if (not cmd or not resp):
			return resp 
		# check if message is such as 1452091728646|{"actions": {"status": 261, "event": "live"}}
		loopCount = 3
		while (not type(resp) is dict and loopCount>0):
			d = resp.split('|')
			if (len(d)>=2):
				rsp = json.loads(d[1])
				if (not "actions" in rsp):
					break
				else:
					if (sockWait):
						resp = pu.disk.sockSendWait(msg=cmd+"|"+param, addnewline=False) # retry
					else:
						pass
					pu.mdbg.log("retry_pxpcmd[{}]--> cmd:{} param:{}...resp1:{}".format(loopCount,cmd, param,resp))
			else: 
				break
			loopCount -= 1
		return resp
	except Exception as e:
		pu.mdbg.log("[---] retry_pxpcmd-->cmd:{}  param:{}  resp:{}".format(cmd, param,resp))
		return False

def past_check_status():
	"""
	pastpage html context checker: it checks all of status such as backup,mp4 fix, export XML and USB status
	"""
	resp = {'results':{'status':False}}
	try:
		io = pu.io
		param = io.get('param')
		bkp_hid = io.get('bkp_hid')
		fix_hid = io.get('fix_hid')
		xpt_hid = io.get('xpt_hid')
		if (bkp_hid==None):
			bkp_hid = ''
		if (fix_hid==None):
			fix_hid = ''
		if (xpt_hid==None):
			xpt_hid = ''
		webdbg = pu.pxpconfig.check_webdbg('param')
		if (webdbg):			
			pu.mdbg.log("past_check_status-->param:{}  bkp_hid:{}  fix_hid:{}  xpt_hid:{}".format(param, bkp_hid, fix_hid, xpt_hid))
		resp = pu.disk.sockSendWait(msg="PCS|"+param+"|"+bkp_hid+"|"+fix_hid+"|"+xpt_hid, addnewline=False) # PCS returns string via json.dumps()
		resp = retry_pxpcmd('PCS',param,resp)
		if (resp):
			d = json.loads(resp)
			b1 = len(d['results']['fix']['status'])>0
			b2 = len(d['results']['bkp']['status'])>0
			b3 = d['results']['usb']['status']==True
			b4 = len(d['results']['xpt']['status'])>0
			if (webdbg and d['results']['status']==True and (b1 or b2 or b3 or b4)):
				pu.mdbg.log("past_check_status--> resp1:", resp)
			return json.JSONEncoder().encode(d)
		return json.JSONEncoder().encode(json.loads({'results':{'status':False}})) # failed
	except Exception as e:
		pu.mdbg.log("[---] past_check_status:{} param:{} resp:{}".format(e, param, resp))		
		return json.JSONEncoder().encode(json.loads({'results':{'status':False}}))

def past_check_progress():
	"""
	pastpage html progress handler
	"""
	res = '{"progress":100}'
	try:
		resp = pu.disk.sockSendWait(msg="PCP|", addnewline=False)
		s = "{'results':"+json.dumps(resp)+"}"
		return json.JSONEncoder().encode(json.loads(s.replace("'", "\"")))
	except Exception as e:
		pu.mdbg.log("[---] past_check_progress:{}".format(e))		
		return json.JSONEncoder().encode(json.loads(res.replace("'", "\"")))

#######################################################
# Fix MP4
def mp4rebuild():
	"""
	mp4 rebuild hanlder: entry for re-creating mp4 file when the recording was not successful. This will creates new mp4 with segment files.
	"""
	try:
		pu.mdbg.log("-->mp4rebuild begins")
		evt_hid = pu.io.get('event')
		vq = pu.io.get('vq')
		sIdx = pu.io.get('sidx')
		_dbgLog("mp4rebuild ---> event:"+str(evt_hid)+"  vq:"+str(vq)+"  sIdx:"+str(sIdx))
		if (vq!="HQ" and vq!="LQ" ):
			_dbgLog("mp4rebuild --> invalid VQ")
			return _err("mp4rebuild --> invalid vq")
		if (sIdx.find("_")<= 0):
			_dbgLog("mp4rebuild --> invalid SIDX")
			return _err("mp4rebuild --> invalid sidx")
		evt_word = evt_hid.split("_") # 2015-12-23_09-50-00_c3737664be0efdb9a5f7277457cd3f2243fa4b92_local
		if (len(evt_word) == 4):
			if(re.search("[^A-z0-9]",str(evt_word[2]))): #found non-alphanumeric characters
				_dbgLog("mp4rebuild --> invalid characters in event HID")
				return _err("mp4rebuild --> invalid event")
		sidx = sIdx.split('_')[1]
		resp = pu.disk.sockSendWait(msg="FIX|"+evt_hid+"|"+sidx+"|"+vq,addnewline=False)
		pu.mdbg.log("-->mp4rebuild ends answer:{}".format(resp))		
		return json.loads(resp)
	except Exception as e:
		return _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno))

def mp4rebuildstatus():
	"""
	rebuild mp4 status handler: not used anymore
	"""
	pass

#------------------------
# Tag to XML exporting
#------------------------

class Tag2XML(object):
	def __init__(self):
		self.tags = []
	def add(self, p_start, p_end, p_code, p_ID):
		from collections import OrderedDict
		v = OrderedDict()
		v['ID']=p_ID
		v['start']=p_start
		v['end']=p_end
		v['code']=p_code
		self.tags.append(v)
	def makeXML(self):
		sxml = ""
		for tag in self.tags:
			sxml += "<instance>"
			sxml += dicttoxml.dicttoxml(tag,attr_type=False, root=False)
			sxml += "</instance>"
		xmldoc="<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
		xmldoc+="<file><ALL_INSTANCES>"
		xmldoc+=sxml
		xmldoc+="</ALL_INSTANCES>"
		xmldoc+="<ROWS>"
		xmldoc+="<row><code>N/A</code><R>0</R><G>0</G><B>0</B></row>"
		xmldoc+="<row><code>N/A</code><R>0</R><G>0</G><B>0</B></row>"
		xmldoc+="</ROWS>"
		xmldoc+="</file>"
		return xmldoc
	def prettyXML(self, xml):
		s = ''
		dom = parseString(xml)
		s = dom.toprettyxml()
		return s

# export all of tags to XML file

def exportevt():
	try:
		# exportevt/?event=2016-06-01_11-10-29_ca1a59ffd98847917d80d9a8a60d5c4ca473fa84_local&vq=HQ&sidx=s_00		
		pu.mdbg.log("-->exportevt begins")
		evt_hid = pu.io.get('event')
		vq = pu.io.get('vq')
		sIdx = pu.io.get('sidx')
		pu.mdbg.log("exportevt ---> event:"+str(evt_hid)+"  vq:"+str(vq)+"  sIdx:"+str(sIdx))
		if (vq!="HQ" and vq!="LQ" ):
			pu.mdbg.log("exportevt --> invalid VQ")
			return _err("exportevt --> invalid vq")
		if (sIdx.find("_")<= 0):
			pu.mdbg.log("exportevt --> invalid SIDX")
			return _err("exportevt --> invalid sidx")
		evt_word = evt_hid.split("_") # 2015-12-23_09-50-00_c3737664be0efdb9a5f7277457cd3f2243fa4b92_local
		if (len(evt_word) == 4):
			if(re.search("[^A-z0-9]",str(evt_word[2]))): #found non-alphanumeric characters
				pu.mdbg.log("exportevt --> invalid characters in event HID")
				return _err("exportevt --> invalid event")
		sidx = sIdx.split('_')[1]

		# TEST --- REMOVE BELOW 
# 		evt_hid = "2016-06-01_09-47-42_c6ceff0ce68b4d764b08a50c24841db9d6de7aed_local"
# 		sidx = "00"
# 		vq = "HQ"
		#-----------------------

		event = evt_hid
		user = ''
		device = ''
		from collections import OrderedDict

		db = pu.db(c.wwwroot+event+"/pxp.db")
		sql = "SELECT * FROM `tags` WHERE NOT `type`=3 ORDER BY `starttime`, `duration`"
		db.qstr(sql)
		tags = db.getasc()
		db.close()

		count = 0
		t2xml = Tag2XML()
		for tag in tags:
			# only even type tags are sent (normal, telestration, period/half/zone/line end tags)
			# also deleted tags are sent - to delete them from other tablets
			# if ((int(tag['type'])&1) and (not int(tag['type'])==3)):
			#	 continue
			if(str(tag['time'])=='nan'):
				tag['time']=0
			#tagJSON = _tagFormat(tag=tag, event=event, user=user, db=db)
			count += 1
			t2xml.add(p_ID=count, p_start=tag['starttime'], p_end=str(float(tag['starttime'])+float(tag['duration'])), p_code=tag['name'])
			
		# convert tags into XML fomrat	
		xml = t2xml.makeXML()
		formatted_xml = t2xml.prettyXML(xml)
		#pu.disk.file_set_contents("/tmp/"+event+".xml", xml)
		pu.disk.file_set_contents(c.wwwroot+event+"/"+event+".xml", xml)
		
		pu.mdbg.log("tags to xml:")
		pu.mdbg.log(formatted_xml)

		resp = {"success":True, "msg": "event:" + event +" xml is exported"} #, "tags_xml":xml}		
		r = pu.disk.sockSendWait(msg="XVT|"+evt_hid+"|"+sidx+"|"+vq,addnewline=False)
		#r['msg'] = "event:" + event
		pu.mdbg.log("-->exportevt.ends  r_answer:{}".format(r))		
		pu.mdbg.log("-->exportevt.ends  answer:{}".format(resp))		
		return resp
	except Exception as e:
		return _err(str(e)+'[---] '+str(sys.exc_info()[-1].tb_lineno))

#######################################################
# removes an event (sets deleted = 1)
# delets all content associated with it
#######################################################

def evtdelete():
	""" Mark an event as deleted in the database (subsequently removes the files associated with it).
		Args:
			none
		API args:
			event(str): hid of the event to back up
			full(bool): whether to return full directory tree (segments and thumbnails) or just thumbnails
		Returns:
			(dictionary): 
				success(bool): whether the command was successful
				msg(str): error message (if applicable)
	"""
	import subprocess
	try:
		pu.mdbg.log("-->evtdelete")
		########################### REMOVE THIS!!!
		#return {"success":True, "msg":""} # TEST
		##########################################
		
		# check to make sure the database event exists
		if(not os.path.exists(c.wwwroot+'_db/pxp_main.db')):
			return _err("not initialized")
		io = pu.io
		event  = io.get('event') #hid of the event  stored in the database
		if (pu.pxpconfig.check_webdbg('param')):			
			pu.mdbg.log("-->evtdelete param:{}".format(event))
		
		if(re.search("[^A-z0-9]",event)):
			#either event was not specified or there's invalid characters in the name 
			#e.g. user tried to get clever by deleting other directories
			return _err("Invalid event")
		# mark the event as deleted in the database (it'll be removed in pxpservice.py)
		db = pu.db(c.wwwroot+"_db/pxp_main.db")
		sql = "UPDATE `events` SET `deleted`=1 WHERE `hid` LIKE ?"
		db.query(sql,(event,))
		db.close()
	except Exception as e:
		return {"success":False,"msg":str(e)+' '+str(sys.exc_info()[-1].tb_lineno)}
	return {"success":True, "msg":""}
#end evtdelete

def getvideoinfo():
	""" Gets resolutions for each camera and encoder status
		Args:
			none
		API args:
			none
		Returns:
			(dictionary): 
				success(bool): whether the command was successful
				msg(str): list of cameras' resolutions
				encoder(str): encoder status in text format
	"""	
	import camera
	cams = camera.getOnCams()
	result = {}
	if(len(cams)>0):
		result = {"success":True,"msg":', '.join(camera.camParam('resolution',getAll=True)),"encoder":encoderstatus()}
		if (pu.pxpconfig.check_webdbg('param') and pu.pxpconfig.check_webdbg('getvideoinfo')):			
			pu.mdbg.log("getvideoinfo-->{}".format(result))
		return result
	return {"success":True,"msg":"N/A","encoder":encoderstatus()}
#end getcamera

def getcameras():
	""" Gets all detected cameras
		Args:
			none
		API args:
			none
		Returns:
			(dictionary): 
				camlist(dictionary): a dictionary of cameras with their IP addresses as indecies
	"""
	import camera
	return {"camlist":camera.getOnCams()}
#end getcameras

def getpastevents():
	""" Gets resolutions for each camera and encoder status
		Args:
			none
		API args:
			none
		Returns:
			(dictionary): 
				events(list): see _listEvents description
	"""
	return {"events":_listEvents(showSizes=False)} #send it in dictionary format to match the sync2cloud format
#end getpastevents

def gametags():
	""" Gets all the tags for a specified event
		Args:
			none
		API args:
			user(str): hid of the user requesting data
			event(str): event name
			device(str): hid of the device requesting data
		Returns:
			(dictionary): see _syncTab description
	"""
	strParam = pu.uri.segment(3,"{}")
	#strParam = '{"requesttime":162225.6877625417,"user":"ae1e7198bc3074ff1b2e9ff520c30bc1898d038e","device":"BBA687B2-B54F-4E91-B4D0-586E7FAF9670","event":"2015-09-29_17-39-34_85d686d1cd49c96cde17e65be0df3191672fba51_local"}'

	jp = json.loads(strParam)
	if not ('user' in jp and 'event' in jp and 'device' in jp):
		return _err("Specify user, event, and device")

	if (pu.pxpconfig.check_webdbg('param')):
		pu.mdbg.log("-->gametags: param-->", strParam)
		
	#get user id
	usr = jp['user']
	#device ID
	dev = jp['device']
	#event
	evt = jp['event']
	if(_stopping(evt)):
		return _stopping(msg=True)
	return _syncTab(user=usr, device=dev, event=evt, allData = True)

def login(sess=False, email=False, passw=False):
	""" Authenticates a user and saves his info in a session
		Args:
			sess(obj): session object
			email(str): user's email (in plain text)
			passw(str): plain text password
		API args:
			email(str): user's email (in plain text)
			passw(str): plain text password
		Returns:
			(dictionary):
				success(bool): whether the login was successful
	"""
	try:
		io = pu.io
		if(not(email and passw)):
			email = io.get("email")
			passw = io.get("pass")
		if not (email and passw):
			return _err("Email and password must be specified")
		pu.mdbg.log('--> trying login as', email)		
		encEm = pu.enc.sha(email)
		encPs = _hash(passw)
		# make sure the encoder has been initialized
		if not _inited():
			# it wasn't initialized yet - activate it in the cloud
			res = _init(email,passw)
			if (not res==1):
				return _err(res)
			# activation was successful, perform a sync
			resp = _syncEnc(encEm,encPs)
			if(not 'success' in resp):
				return resp
		#if not inited

		result = {"success":False}

		# check if user is in the database
		db = pu.db(c.wwwroot+"_db/pxp_main.db")
		sql = "SELECT `hid` FROM `users` WHERE `email` LIKE ? AND `password` LIKE ?"
		db.query(sql,(email,encPs))
		rows = db.getrows()
		if(len(rows)<1):
			pu.mdbg.log('login error--> Invalid email or password')
			return _err("Invalid email or password")
		pu.mdbg.log('--> login exists', len(rows))
		# log him in
		if(sess):
			#first, make sure there are no old session variables
			sess.destroy()
			sess.start(expires=24*60*60,cookie_path="/")
			usrData = rows[0]
			sess.data['user']=usrData[0] #user hid
			# store plain text email in the session (to display logged in user)
			sess.data['email']=email
			# encrypted email
			sess.data['ee']=encEm
			# encrypted password
			sess.data['ep']=encPs
			if (pu.pxpconfig.check_webdbg('param')):
				pu.mdbg.log('--> login session created', sess.data['user'], sess.data['email'], sess.data['ee'], sess.data['ep'])
			result = {"success":True}
	except Exception as e:
		import sys
		return _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno))
	# return {io.get("email"):io.get("pass")}
	return result

def logout( sess):
	""" Authenticates a user and saves his info in a session
		Args:
			sess(obj): session object
		API args:
			none
		Returns:
			(dictionary):
				success(bool): whether the command was successful
	"""
	pu.mdbg.log('--> logged out', sess.data['user'], sess.data['email'])
	sess.data['user']=False
	sess.data['email']=False
	return {"success":True}
#end logout

def prepbackup():
	""" 
		Args:
			none
		API args:
			event(str): name of the event to download
			appid(str,optional): id of the app to which to download. default: com.avocatec.Live2BenchNative
			source(str,optional): download video from this source. default: first source will be used
		Returns:
			success(bool): whether the command was successful
	"""
	io = pu.io
	event = io.get('event')
	appid = io.get('appid')
	sIdx = io.get('source') #e.g. 00hq, 01lq, etc...

	pu.mdbg.log("prepbackup--> event:", event)
	pu.mdbg.log("prepbackup--> appID:", appid)
	pu.mdbg.log("prepbackup--> sIdx:", sIdx)
	
	try:
		return {"success":True}
	except Exception as e:
		import sys
		em = str(sys.exc_info()[-1].tb_lineno)+' '+str(e) 
		_slog(str(sys.exc_info()[-1].tb_lineno)+' '+str(e))
		pu.mdbg.log("[---] prepbackup -- {0}  event:{1}".format(em, event))				
		return _err(em)

def prepdown():
	""" DEPRECATED. Prepares the event download - converts tags to a plist and starts the idevcopy process
		Args:
			none
		API args:
			event(str): name of the event to download
			appid(str,optional): id of the app to which to download. default: com.avocatec.Live2BenchNative
			source(str,optional): download video from this source. default: first source will be used
		Returns:
			(dictionary):
				success(bool): whether the command was successful
	"""
	io = pu.io
	event = io.get('event')
	appid = io.get('appid')
	sIdx = io.get('source') #e.g. 00hq, 01lq, etc...

	pu.mdbg.log("PREPDOWN--> event:", event)
	pu.mdbg.log("PREPDOWN--> appID:", appid)
	pu.mdbg.log("PREPDOWN--> sIdx:", sIdx)
	
	try:
		if not event: #event was not specified
			return _err()
		# make sure it has no : or / \ in the name
		if('/' in event or '\\' in event): #invalid name
			return _err()
		if(_stopping(event)):
			return _stopping(msg=True)

		pu.mdbg.log("PREPDOWN--> step_01:")
		
		db = pu.db(c.wwwroot+event+'/pxp.db')
		# select all even-type tags (deleted are odd, so won't be downloaded)
		db.qstr('SELECT * FROM `tags` WHERE  (`type` & 1) = 0')
		xmlOutput = '<?xml version="1.0" encoding="UTF-8"?>\n'+\
					'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'+\
					'<plist version="1.0">\n<dict>\n'
		# get each tag, format it and output to xml
		tags = db.getasc()
		
		pu.mdbg.log("PREPDOWN--> step_02:")		
		
		# add playing teams
		# get the teams playing
		sql = "SELECT `id` FROM `logs` WHERE `type` LIKE 'enc_start'"
		db.qstr(sql)
		teamHIDs = db.getasc()
		
		pu.mdbg.log("PREPDOWN--> step_03:")		
		
		if (len(teamHIDs)>0): #this will be the case when there is a blank db in the event (encode was not started)
			teamHIDs = teamHIDs[0]['id'].split(',')
		if(len(teamHIDs)>2):#in case this is an old event, and the league HID is not listed along with team HIDs (comma-delimeted) in the log table, add empty value for the league
			leagueHID = teamHIDs[2]
			del(teamHIDs[2]) #remove league id from the teams list
		else:
			leagueHID = ""
		#close the database (so that log can use it)
		db.close()

		pu.mdbg.log("PREPDOWN--> step_04:")		

		for t in tags:
			# format the tag (get thumbnail image, telestration url, etc.)
			tag = _tagFormat(event=event,tag=t)
			xmlOutput+=_xmldict(tag,tag['id'],1)
			pu.mdbg.log("PREPDOWN--> step_05: tag:{0}".format(t))
		# finish the xml

		xmlOutput += '</dict>\n</plist>'
		# remove old plist if it exists
		if(os.path.exists(c.wwwroot+event+'/tags.plist')):
			os.remove(c.wwwroot+event+'/tags.plist')

		pu.mdbg.log("PREPDOWN--> step_06:")		
		
		
		# plist file is ready, write it out:
		pu.disk.file_set_contents(c.wwwroot+event+'/tags.plist',xmlOutput)

		# create extra.plist file
		xmlOutput = '<?xml version="1.0" encoding="UTF-8"?>\n'+\
					'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'+\
					'<plist version="1.0">\n<dict>\n'
		# for now extra only contains teams info (will add other stuff later if needed)
		xmlOutput+=_xmldict(teamHIDs,"teams",1)
		xmlOutput+='</dict>\n</plist>'
		# remove old extra.plist if it exists
		if(os.path.exists(c.wwwroot+event+'/extra.plist')):
			os.remove(c.wwwroot+event+'/extra.plist')
		# plist file is ready, write it out:
		pu.disk.file_set_contents(c.wwwroot+event+'/extra.plist',xmlOutput)

		pu.mdbg.log("PREPDOWN--> step_07:")				
		
		# event folder has to have spaces escaped (otherwise it'll break the command)
		eventFolder = event.replace(" ","\ ")
		# make sure kill idevcopy isn't running (otherwise the ipads used by it will be unresponsive)
		os.system("killall -9 idevcopy 2>/dev/null &")
		# make sure the pipe for getting idevcopy output doesn't exist before starting
		progressPipe = "/tmp/pxpidevprogress"
		try: #put it in try...except block in case unlink fails, do not terminate the download process
			if(os.path.exists(progressPipe)):
				os.unlink(progressPipe)
			pu.mdbg.log("PREPDOWN--> step_08:")				
		except:
			pu.mdbg.log("PREPDOWN--> progress_cuaght")				
			pass	

		pu.mdbg.log("PREPDOWN--> step_09:")				

		if(appid):
			#make sure appid only contains alphanumerics, dot, and dash
			if(re.search("[^A-z0-9\-\.]",appid)):
				appid="com.avocatec.Live2BenchNative" #user probably tried to 'hack' the system, submitted a separate command
			else:
				appid=" "+appid
		else:
			appid="com.avocatec.Live2BenchNative"

		pu.mdbg.log("PREPDOWN--> step_10:")				


		# start the download
		if(not sIdx): #this is for old-style systems
			# THIS IS A PATCH FOR OLD BUILD! DO NOT RELEASE!!!!! #
			sIdx = _firstSourceIdx(event)
			mp4Name = 'main_'+sIdx+'.mp4'
			cmd = c.wwwroot+"_db/idevcopy -a "+appid+" -e "+eventFolder+" -d "+c.wwwroot+eventFolder+" -f "+mp4Name+" -r main.mp4 -m >/dev/null &"
			# END PATCH #
		else:
			# for description of each parameter, run idevcopy with no arguments
			cmd = c.wwwroot+"_db/idevcopy -a "+appid+" -e "+eventFolder+" -d "+c.wwwroot+eventFolder+" -f main_"+sIdx+".mp4 -m >/dev/null &"
		os.system(cmd)
		
		pu.mdbg.log("PREPDOWN--> step_11: cmd:{0}".format(cmd))				
		return {"success":True}
	except Exception as e:
		import sys
		em = str(sys.exc_info()[-1].tb_lineno)+' '+str(e) 
		_slog(str(sys.exc_info()[-1].tb_lineno)+' '+str(e))
		pu.mdbg.log("[---] PREPDOWN -- {0}  event:{1}".format(em, event))				
		return _err(em)

def _slog(text):
	""" Logs a string to file
		Args:
			text(str): text to record to a log file
		API args:
			none
		Returns:
			none
	"""
	# generate timestamp
	timestamp = _time()
	os.system("echo '"+timestamp+": "+text+"' >> "+c.wwwroot+"_db/log.txt")

def rtmpcast():
	try:
		#if (pu.mdbg.check(pu.c_dbg.DBG_CTRL)):
		#	pydevd.settrace()										
		io = pu.io
		pp=""
		src=""
		if(not(pp)):
			pp = io.get("pp")
			src = io.get("src")	
		#arg = pu.uri.segment(3, "s_02")
		pu.mdbg.log("-->rtmpcast:{0}    src:{1}".format(pp, src))
		resp = pu.disk.sockSendWait(msg="RTM|"+src+"|"+pp, addnewline=False)
	except Exception as e:
		import sys
		return _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno))	
	return {"success":True} # dict("", **{"action":"reload"})
	
def settingsRtmpGet():
	resp = pu.disk.sockSendWait(msg="CML|", addnewline=False)
	#pu.mdbg.log("-->settingsRtmpGet-->", pp.pformat(resp))
	d = json.loads(resp)
	return d

def getRtmpStat():
	return json.loads(pu.disk.sockSendWait(msg="RTS|", addnewline=False))

def settingsGet():
	""" retreives the encoder settings (file is in json format)
		Args:
			none
		API args:
			none
		Returns:
			(dictionary):
				tags(dictionary): settings for prerol/postroll
				sync(dictionary): x-sync settings
				clips(dictionary): quality settings for MyClip
				video(dictionary): stream settings
				uploads(dictionary): cloud upload settings
	"""
	from collections import OrderedDict
	import camera
	pu.mdbg.log("============= settingsGet---------------------->begins")
	settings = pu.disk.cfgGet(c.pxpConfigFile)
	# return settings
	try:
		# go through each section and assign possible values for it
		# make sure the setting section is available (if it's not, add it)
		# return {}		
		# video settings
		# get current bitrate (if its available from the encoder)
		bitrate = camera.camParam('bitrate')
		ccBitrate = camera.camParam('ccBitrate') #can change bitrate
		allparams = camera.camParam('url', getAll=True)
		pu.mdbg.log("settingsGet urls---->{}".format(allparams)) # i.e [u'rtsp://192.168.5.115:17200/pxpstr', u'rtsp://192.168.5.115:17100/pxpstr']
		settings['urls'] = allparams

		#default bitrate
		settings['video']={'bitrate':5000}
		#default video input type (Delta Encoder Only)
		if (pu.pxpconfig.support_cam('dt')):
			settings['video']={'vit':3}
		try:
			if(ccBitrate): #this camera allows changing the bitrate
				# verify bitrate is a valid number
				val = int(bitrate)
				if(val>=1000 and val<=5000):
					settings['video']['bitrate']=bitrate
			else:#cannot set bitrate on this camera
				settings['video']['bitrate'] = False
		except Exception as e:
			pu.mdbg.log("[---] settingsGet...{}".format(e))
			pass
		settings['video']['bitrate_options']=OrderedDict([
			(5000,"Very high (5Mbps)"),
			(3000,"High (3Mbps)"),
			(2500,"Medium (2.5Mbps)"),
			(2000,"Low (2Mbps)"),
			(1500,"Very low (1.5Mbps)"),
			(1000,"Poor (1Mbps)")
		])
		if (pu.pxpconfig.support_cam('dt')):
			settings['video']['bitrate_options']=OrderedDict([
				(5000,"Very high (5Mbps)"),
				(3000,"High (3Mbps)"),
				(2000,"Medium (2.0Mbps)"),
				(1000,"Low (1Mbps)"),
			])
			settings['video']['vit_options']=OrderedDict([
				(0,"CVBS/SDI Auto Detect"),
				(1,"CVBS"),
				(2,"SDI"),
				(3,"DVI"),
				(4,"Test Pattern"),
			])
			vit = camera.camParam('vit')
			settings['video']['vit'] = vit
			
		# MyClip settings
		if(not 'clips' in settings):
			settings['clips']={'quality':1}
		try:
			# check that quality is a valid number
			val = int(settings['clips']['quality'])
			if(val<1):
				settings['clips']['quality']=8
		except:
			settings['clips']['quality']=8
		settings['clips']['quality_options']=OrderedDict([
			(1,"Very high"),
			(3,"High"),
			(6,"Medium"),
			(8,"Low"),
			(10,"Very low"),
		])
		# Tags settings
		if(not 'tags' in settings):
			settings['tags']={'preroll':5,'postroll':5}
		if(not 'preroll' in settings['tags']):
			settings['tags']['preroll']=5
		if(not 'postroll' in settings['tags']):
			settings['tags']['postroll']=5
		try:
			# check that preroll and postroll are valid numbers
			val1 = int(settings['tags']['preroll'])
			if(val1<0):
				settings['tags']['preroll']=10
			val2 = int(settings['tags']['postroll'])
			if(val2<0):
				settings['tags']['postroll']=10
			if((val1+val2)<5):
				settings['tags']['postroll']=10
				settings['tags']['preroll']=10
		except:
			settings['tags']['postroll']=10
			settings['tags']['preroll']=10

		settings['tags']['preroll_options']=OrderedDict([
			(0,"0s"),
			(1,"1s"),
			(2,"2s"),
			(5,"5s"),
			(10,"10s"),
			(20,"20s")
		])
		settings['tags']['postroll_options']=OrderedDict([
			(0,"0s"),
			(1,"1s"),
			(2,"2s"),
			(5,"5s"),
			(10,"10s"),
			(20,"20s")
		])
		# misc -----
		if(not 'misc' in settings):
			settings['misc']={}
		settings['misc']['use_splited_feed']=pu.pxpconfig.use_split_event_folder()
		settings['misc']['use_postproc']=pu.pxpconfig.use_mp4align()
		settings['misc']['use_virtual_lq_enabled']=not pu.pxpconfig.virtual_lq_enabled()
		settings['misc']['use_proxy']=pu.pxpconfig.use_proxy()
		settings['misc']['use_tcp']=pu.pxpconfig.use_tcp()
		settings['misc']['use_segment_later']=pu.pxpconfig.use_segment_later()
		settings['misc']['use_mp4tcp']=pu.pxpconfig.use_mp4tcp()
		settings['misc']['use_ping_camcheck']=pu.pxpconfig.use_ping_camcheck()
		settings['misc']['show_webplayer']=pu.pxpconfig.show_webplayer()
		settings['misc']['show_tcpopt']=pu.pxpconfig.show_tcpopt()
		settings['misc']['show_option']=pu.pxpconfig.show_option()
	
	except Exception as e:
		settings["err"]=str(e)+' '+str(sys.exc_info()[-1].tb_lineno)
		pu.mdbg.log("[---] settingsGet_2...{}".format(settings["err"]))
		# could not get/parse some settings, download the config file from the cloud
		pass
	pu.mdbg.log("============= settingsGet---------------------->ends")
	return settings
#end settingsGet

def settingsSet():
	""" Updates an encoder settings
		Args:
			none
		API args:
			section(str): name of the section to set
			setting(str): name of the setting to set
			value(mixed): the new value to set
		Returns:
			(dictionary):
				success(bool): whether the command was successful
	"""
	io = pu.io
	try:
		# get the parameter that user is trying to set
		secc = io.get("section")
		sett = io.get("setting")
		vals = io.get("value")
		pu.mdbg.log("============= settingsSet---------------------->begins.sect:{}  sett:{}  value:{}".format(secc, sett, vals))
		if(secc=='video' and sett=='vit'):
			#the following 2 commands are for blackmagic only
			# changing video stream quality
			pu.disk.file_set_contents(c.wwwroot+"_db/.cfgenc",vals)
			# reset the streaming app
			pu.disk.file_set_contents("/tmp/pxpcmd","2")
			# this is for teradek/matrox - set bitrate for camera index -1: meaning all cameras
			pu.disk.sockSend("VIT|"+str(vals)+"|-1",addnewline=False)
			# add an event to live stream to indicate that the bitrate was changed
			_logSql(ltype="changed_bitrate",lid=str(vals),dbfile=c.wwwroot+"live/pxp.db")
		if(secc=='video' and sett=='bitrate'):
			#the following 2 commands are for blackmagic only
			# changing video stream quality
			pu.disk.file_set_contents(c.wwwroot+"_db/.cfgenc",vals)
			# reset the streaming app
			pu.disk.file_set_contents("/tmp/pxpcmd","2")
			# this is for teradek/matrox - set bitrate for camera index -1: meaning all cameras
			pu.disk.sockSend("BTR|"+str(vals)+"|-1",addnewline=False)
			# add an event to live stream to indicate that the bitrate was changed
			_logSql(ltype="changed_bitrate",lid=str(vals),dbfile=c.wwwroot+"live/pxp.db")

		if(secc=='misc' and sett=='use_postproc'):
			pu.pxpconfig.change_value("enable_mp4_convert", str(vals))
			pu.pxpconfig.change_value("use_mp4align", str(vals))

		if(secc=='misc' and sett=='use_virtual_lq_enabled'):
			if (str(vals)=='1'):
				pu.pxpconfig.change_value("virtual_lq_enabled", str(0))
			else:
				pu.pxpconfig.change_value("virtual_lq_enabled", str(1))

		if(secc=='misc' and sett=='use_proxy'):
			pu.pxpconfig.change_value("use_proxy", str(vals))

		if(secc=='misc' and sett=='use_tcp'):
			pu.pxpconfig.change_value("use_tcp", str(vals))

		if(secc=='misc' and sett=='use_mp4tcp'):
			pu.pxpconfig.change_value("use_mp4tcp", str(vals))

		if(secc=='misc' and sett=='use_segment_later'):
			pu.pxpconfig.change_value("use_segment_later", str(vals))

		if(secc=='misc' and sett=='restart'):
			pu.mdbg.log("============= settingsSet----> RESTART!!")
			cmd = "killall -9 python"
			os.system(cmd)
				
		if(secc=='misc' and sett=='find_delta'):
			pu.mdbg.log("============= settingsSet----> find_delta")
		
		
		# will be true or false depending on success/failure
		success = pu.disk.cfgSet(c.pxpConfigFile,section=secc,parameter=sett,value=vals)
		
		pu.mdbg.log("============= settingsSet---------------------->ends")
	except Exception as e:
		pu.mdbg.log("[---] settingsSet err:".format(e))
	return {"success":success}
#end settingsSet



def sumget(strParam=False):
	""" returns summary for the month or game
		Args:
			none
		API args:
			user(str): hid of the user
			id(str): id of the event
			type(mixed): type of summary (game or month)
		Returns:
			(dictionary):
				summary(str): summary text (if available)
	"""
	try:
		if (not strParam):
			strParam = pu.uri.segment(3,"{}")
		jp = json.loads(strParam) #json params
		if not ('user' in jp and 'id' in jp and 'type' in jp):
			return _err("Specify event or month")
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("-->sumget-->parameter:{}".format(strParam))
		
		# select the proper summary from the table
		sql = "SELECT * FROM `summary` WHERE `type` LIKE ? AND `id` LIKE ?"
		db = pu.db(c.wwwroot+"_db/pxp_main.db")
		db.query(sql,(jp['type'],jp['id']))
		# fetch the data
		summary = db.getasc()
		db.close()
		# return the summary if it's in the database
		if(len(summary)>0):
			return summary[0]
		return {"summary":""}
	except Exception as e:
		import sys 
		return _err(str(sys.exc_info()[-1].tb_lineno)+' '+str(e))

def sumset(strParam=False):
	# sets summary for month or game
	""" Updates (or adds a new) summary
		Args:
			none
		API args:
			user(str): hid of the user
			id(str): id of the event
			type(mixed): type of summary (game or month)
			summary(str): summary text
		Returns:
			(dictionary):
				success(bool): whether the command was successful
	"""
	try:
		# get the information from url
		if (not strParam):
			strParam = pu.uri.segment(3,"{}")
		jp = json.loads(strParam) #json params
		if not ('user' in jp and 'summary' in jp and 'id' in jp and 'type' in jp):
			return _err("Specify event or month and summary")
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("-->sumset-->parameter:{}".format(strParam))
			
		#add the info or update it (if already exists)
		sql = "INSERT OR REPLACE INTO `summary`(`summary`,`type`,`id`) VALUES(?,?,?)"
		db = pu.db(c.wwwroot+"_db/pxp_main.db")
		db.query(sql,(jp['summary'],jp['type'],jp['id']))
		db.close()
		return {"success":True}
	except Exception as e:
		import sys 
		return _err(str(sys.exc_info()[-1].tb_lineno)+' '+str(e))

def sync2cloud(sess):
	""" Gets up to date information from the cloud for this customer(teams, leagues, users), updates local database.
		Args:
			sess(obj): session object
		API args:
			none
		Returns:
			(dictionary):
				success(boolean): whether the command was successful
	""" 
	try:
		pu.mdbg.log("-->sync2cloud")
		
		if not ('ee' in sess.data and 'ep' in sess.data):
			return _err("Not logged in")
		#the dict({},**{}) is to combine 2 dictionaries into 1: 
		#{"success":True/False} and {"action":"reload"})
		#_syncEncUp(sess.data['ee'],sess.data['ep'])
		syncResponse = _syncEnc(sess.data['ee'],sess.data['ep'])
		if ('success' in syncResponse):
			return syncResponse
		return dict(syncResponse,**{"action":"reload"})
	except Exception as e:
		import sys
		return _err("Error occurred please contact technical support. "+str(e)+' -- '+str(sys.exc_info()[-1].tb_lineno))

def synclevel():
	""" Returns sync level of the current encoder (w.r.t cloud)
		Args:
			none
		API args:
			none
		Returns:
			none
	""" 
	cfg = _cfgGet()
	if(len(cfg)>3):
		level = cfg[3]
	else:
		level = 0
	pu.mdbg.log("-->synclevel:",level)
	return {"level":level}

def syncme():
	""" Get any new events that happened since the last update (e.g. new tags, removed tags, etc.)
		Args:
			none
		API args:
			user(str): see _syncTab description
			device(str): see _syncTab description
			event(str): see _syncTab description
		Returns:
			(dictionary): see _syncTab description
	""" 
	try:
		strParam = pu.uri.segment(3,"{}")
		jp = json.loads(strParam)
		if not ('user' in jp and 'event' in jp and 'device' in jp):
			return _err("Specify user, event, and device")
		
		if (pu.pxpconfig.check_webdbg('syncme')):
			pu.mdbg.log("-->syncme: param-->", strParam)
		
		#get user id
		usr = jp['user']
		#device ID
		dev = jp['device']
		#event
		evt = jp['event']
		if(_stopping(evt)):
			return _stopping(msg=True)
		if (pu.pxpconfig.check_webdbg('syncme')):
			pu.mdbg.log("-->syncme: user:{0}  device:{1}  event:{2}".format(usr, dev, evt))
		tags = _syncTab(user=usr, device=dev, event=evt)
		return tags
	except Exception as e:
		import sys
		return _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno))

def teamsget():
	""" Return list of teams in the system with team setups
		Args:
			none
		API args:
			none
		Returns:
			(dictionary): 
				leagues(dictionary): a dictionary of leagues with league HIDs as keys
				teamsetup(dictionary): a dictionary of players and their positions for each team. keys are team HIDs
				teams(dictionary): a dictionary of teams (includes name and sport), keys are team HIDs
	""" 
	try:
		pu.mdbg.log("============= teamsget---------------------->begins")
		if(not os.path.exists(c.wwwroot+'_db/pxp_main.db')):
			return _err("not initialized")
		db = pu.db(c.wwwroot+'_db/pxp_main.db')
		result = {"teams":{},"teamsetup":{},"leagues":{}}
		# get the teams from the database
		sql = "SELECT * FROM `teams`"
		db.qstr(sql)
		#convert this data to json-readable:
		# will be similar to : 
		# "0ade7c2cf97f75d009975f4d720d1fa6c19f4897": {"txt_name": "Real_Madrid", "hid": "0ade7c2cf97f75d009975f4d720d1fa6c19f4897", "name": "Real Madrid"}
		for team in db.getasc():
			result['teams'][team['hid']] = {}
			for field in team:
				if(team[field] == None):
					team[field] = ""
				result['teams'][team['hid']][field] = team[field]

		# get team setup (players, positions, etc.)
		sql = "SELECT * FROM `teamsetup` ORDER BY `team`, `jersey`"
		db.qstr(sql)
		# get players for each team
		# will be {"team_HID":[{p1},{p2},{p3}]} where pX is {'player':'13','jersey':55,....}
		idx = 0
		for player in db.getasc():
			# if the team was not added to the array yet, add it
			if(not player['team'] in result['teamsetup']):
				result['teamsetup'][player['team']] = []
			# create a blank player setup for this team (an empty dictionary - will be populated in the for loop after)
			result['teamsetup'][player['team']].append({})
			# simply populate the player setup dictionary that was just added
			for field in player:
				#index of the last player (the new one)
				lastPlayerIdx = len(result['teamsetup'][player['team']])-1
				result['teamsetup'][player['team']][lastPlayerIdx][field] = player[field]

		sql = "SELECT * FROM `leagues`"

		db.qstr(sql)
		for league in db.getasc():
			result['leagues'][league['hid']] = {}
			for field in league:
				result['leagues'][league['hid']][field] = league[field]
		db.close()
		
		pu.mdbg.log("============= teamsget---------------------->ends")
		
	except Exception as e:
		import sys
		return _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno))
	return result
#end teamsget

class PXPWorker(threading.Thread):
	"""
	pxp thread wrapper for background processing: for now, tagset, tagmod, sumset,sumget are supported
	"""
	def __init__(self, cmd, cookie, param):
		threading.Thread.__init__(self)
		self.cmd = cmd
		self.cookie = cookie
		self.param = param
		self.thread_name = "worker-{}-{}".format(cookie, cmd)
	
	def run(self):
		ans = {}
		pu.mdbg.log("PXPWORKER started ------>cmd:{} cookie:{}".format(self.cmd, self.cookie))
		if (self.cmd=='tagset'):
			ans = tagset(self.param)
		elif (self.cmd=='tagmod'):		
			ans = tagmod(self.param)
		elif (self.cmd=='teleset'):		
			ans = teleset(self.param)
		elif (self.cmd=='sumset'):		
			ans = sumset(self.param)
		elif (self.cmd=='sumget'):		
			ans = sumget(self.param)
			
		ans['cookie'] = self.cookie
		resp = pu.disk.sockSendWait("AUP|"+json.dumps(ans), addnewline=True, timeout=3)
		pu.mdbg.log("PXPWORKER finished ------>cmd:{} cookie:{}".format(self.cmd, self.cookie))

def taglive(name,user):
	""" Create a tag in a live event 'at live'
		Args:
			name(str): name of the tag
			user(str): hid of the user
		API args:
			N/A
		Returns:
			(dictionary): see _tagFormat description
	""" 
	try:
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("tagalive-->name:{} user:{}".format(name, user))
		# get maximum available time:
		# get all streams
		streams, firstStream = _listEvtSources("live")
		if(not streams): #there are no video sources in this event - do nothing
			return False
		# assume there's zero video right now
		liveTime = 0
		# go through each stream and find the live time
		for s in streams:
			# get the stream index (stream name is s_XX where XX is a two-digit index)
			q = 'hq' if('hq' in streams[s]) else 'lq'
			sIdx = s.split('_')[1]+q
			# get the time at live (less 2 seconds)
			liveTime = max(liveTime,_thumbName(totalTime=True,sIdx=sIdx,maxOnFail=True)-2)
		# end for s in streams
		# create a tag at live
		tagStr = json.dumps({"name":name,"colour":"#FF0000","user":user,"time":liveTime,"event":"live"})
		result = tagset(tagStr)
	except Exception, e:
		result = False
	return result

def tagmod(tagmodStr=False):
	""" Modify a tag - set as coachpick, bookmark, etc
		Args:
			none
		API args:
			user(str): hid of the user who is requesting info
			event(str): hid of the event
			id(int): tag id
		Returns:
			(dictionary): see _tagFormat description
	""" 
	try:
		strParam = tagmodStr
		if (not tagmodStr):
			strParam = pu.uri.segment(3,"{}")

		if (pu.pxpconfig.check_webdbg('param')):
			import inspect
			pu.mdbg.log("tagmod begins-->caller:{} Param:{}".format(inspect.stack()[1][3], strParam))
		
		#TEST ONLY -----
		#download: strParam={"bookmark":"1","sidx":"s_00hq","id":"8","name":"HEAD SHOT","user":"ae1e7198bc3074ff1b2e9ff520c30bc1898d038e","requesttime":"543791.738451","event":"live","requestime":"543791.738640"}
		#closetag: strParam={"id":"10","deviceid":"B983D5BA-B7D9-48BA-BB43-F1D39D5931A5","starttime":"4286.692356","time":"4286.692356","type":"1006","event":"live","colour":"3AF20F","rating":"","user":"ae1e7198bc3074ff1b2e9ff520c30bc1898d038e","name":"Concussion","comment":"","displaytime":"1:11:27","requestime":"1018261.377870"}
		#id should be matched with previous returned tagset new id. 'time' should have some difference previously sent tagset 'time' to give duration. 'duration' should not be!		
		#strParam=json.dumps(strParam)
		#---------------
		
		jp = json.loads(strParam)
		if not ('user' in jp and 'event' in jp and 'id' in jp):
			return _err("Specify user, event, and tag id")
		#determine the info that user wants to update
		params = ()
		sqlInsert = []
		tid = jp['id']
		user = jp['user']
		event = jp['event']
		
		jp_closetime = False
		if ('closetime' in jp):
			jp_closetime = True
		

		# make sure event is not being stopped
		if(_stopping(event)):
			return _stopping(msg=True)
		if('sidx' in jp):
			sIdx = jp['sidx']
			del jp['sidx']
		else:
			sIdx = _firstSourceIdx(event)
		#user info, tag id and event name are not modifications - remove those from the dictionary
		del jp['id']
		del jp['user']
		del jp['event']
		# go through all json parameters (tag mod's) and check 
		# which modifications should be applied
		bookmark = False
		# fields that are present in the database (everything else goes in the 'meta')
		dbFields = ('name', 'user', 'starttime', 'type', 'time', 'colour', 'duration', 'comment', 'rating', 'extra')
		if ('bookmark' in jp):
			bookmark = (str(jp['bookmark'])=='1')
			del jp['bookmark']
		meta = {}
		
		# TEST 
		#del jp['duration'] #JCHOI
		#jp['time'] = str(float(jp['time']) + 40.0)
		
		# check if manually closing a duration tag:
		if(('type' in jp) and (int(jp['type'])&1)==0 and int(jp['type'])>0): # and (not ('duration' in jp))
			if(not 'time' in jp):
				return _err("Specify time when closing duration tag")
			# closing a duration tag
			sqlInsert.append("`duration`=CASE WHEN (?-`time`)>0 THEN (?-`time`) ELSE 0 END")
			params += (jp['time'],jp['time']) # 2nd jp['time'] will add to 9 secs below...
			del jp['time']
			jp['modified']=0 #close duration tags do not have modified status
		else:
			jp['modified']=1
		if (bookmark):
			jp['modified']=1
		for mod in jp:
			if (mod=='starttime' and float(jp[mod])<0):#modifying starttime (extending the beginning of the tag)
				value = 0
			if (mod=='delete'):	#when deleting a tag, simply change type to 3
				sqlInsert.append("`type`=?")
				params +=(3,)
			elif (mod!='requesttime'):#any other modifications, just add them to the sql query
				#flag to check if this is a bookmark ("my clip")
				if(not mod in dbFields):
					meta[mod]=jp[mod]
				else:
					sqlInsert.append("`"+mod+"`=?")
					if(type(jp[mod]) is dict):
						params +=(json.dumps(jp[mod]),)
					else:
						params +=(jp[mod],)
		#end for mod in jp
	
		#make sure the database exists and user is not trying to get at other folders
		if(('/' in event) or ('\\' in event) or (not os.path.exists(c.wwwroot+event+'/pxp.db'))):
			return _err()
		db = pu.db(c.wwwroot+event+'/pxp.db')

		# add metadata params
		# select existing metadata params
		sql = "SELECT `meta` FROM `tags` WHERE id=?"
		db.query(sql,(tid,))
		tag = db.getasc()
		if(len(tag)<1):
			return _err("tag "+str(tid)+" does not exist")
		metaOld = json.loads(tag[0]['meta'])
		# add all the old meta fields that were not changed to the meta field
		for field in metaOld:
			if(not field in meta):
				meta[field]=metaOld[field]
		#pu.mdbg.log("=============>>>> meta={}".format(meta))		
				
		# add the metadata field
		sqlInsert.append("`meta`=?")
		params += (json.dumps(meta),)
		if len(sqlInsert)<1:#nothing was specified 
			return _err()
		if(bookmark and not checkspace()):
			return _err("Not enough free space. Delete some of the old events from the encoder.")
		# parameters to add to the sql - tag id (no need to check user at the moment)
		params += (tid,)
		#update the tag
		sql = "UPDATE `tags` SET "+(', '.join(sqlInsert))+" WHERE id=?"
		# if(not bookmark):#do not mark as bookmark in the database - only give the user the ability to download it, no need for everyone else to get this file				

		try:
			if ('type' in jp and ((int(jp['type'])&1)==0)): #((int(jp['type'])==100) or (int(jp['type'])==1006))): # 100: for old app, 1006: for new app
				pu.mdbg.log("tagmod param1:{}".format(params))
				xp = list(params) # convert tuple to list
				pu.mdbg.log("tagmod param2:{}".format(xp))
 				xp[1] = unicode(str(float(xp[1]) + 9.0), "utf-8") # 2nd 'time' is added JCHOI
				params = tuple(xp) # convert list to tuple back
				pu.mdbg.log("tagmod param3-> sql:{} parma:{}".format(sql,params))
				pu.mdbg.log("tagmod params changed manually... 9 secs are added")
		except:
			pass

		#update the tag info in the database		
		success = db.query(sql,params)
		if success:
			#add an entry to the event log that tag was updated or deleted
			success = _logSql(ltype='mod_tags',lid=tid,uid=user,db=db)
		if success:
			db.close() #close db here because next statement will return
			if (bookmark):
				# user wants to make a bookmark - extract the video
				success = success and _extractclip(tagid=tid,event=event, sIdx = sIdx)
			return _tagFormat(event=event, user=user, tagID=tid, sockSend=True)
		db.close()
		return {'success':success}
	except Exception as e:
		import sys
		errstr = str(sys.exc_info()[-1].tb_lineno)+' '+str(e)
		pu.mdbg.log("[---]tagmod err:{}".format(errstr))
		return _err(errstr)

#######################################################

def tagset(tagStr=False, sendSock=True):
	""" Creates a new tag

		Args:
			tagStr(str, optional): json string with tag info. if not passed as argument, it must be passed in a URL as last segment. possible parameters: 
				name(str): name of the tag 
				time(float): time of the tag in seconds 
				event(str): HID of the event (or 'live' for live)
				user(str): user HID 
				deviceid(str): HID of the device (to be able to end duration tags on per-tablet basis)
				duration(float,optional): tag duration. default: whatever is set in the settings page for pre-roll and post-roll
				type(int,optional): type of tag. default:0
					tag types:
						0: default				: a generic tag around a certain time (any sport)

						3: deleted				: this one shouldn't happen on tagSet (any sport)
						4: telestration		 : a regular telestration: still frame with hand drawing on it (any sport)
						40: televideo			 : same as telestration, except there's a video associated with it instead of an image - you can see the progress of the telestration (any sport)

						1: start o-line		 : hockey - start of offence line
						2: stop o-line			  : hockey - end of offence line
						5: start d-line			 : hockey - start of defence line
						6: stop  d-line			 : hockey - end of defence line	
						7: period start			 : hockey - beginning of period
						8: period	stop		: hockey - end of period
						9: strength start		 : hockey - start of a strength tag (e.g. 5vs4)
						10: strength stop		 : hockey - end of a strength tag (e.g. when 5vs4 goes back to 5vs5)
						11: opp. o-line start	 : hockey - opposition offence line start
						12: opp. o-line stop	 : hockey - opposition offence line end
						13: opp. d-line start	 : hockey - opposition defence line start
						14: opp. d-line stop	 : hockey - opposition defence line end

						15: zone start			 : soccer - offence zone, defence zone, etc. start
						16: zone stop			 : soccer - zone end
						17: half start			 : soccer - half start (same as period in hockey)
						18: half stop			 : soccer - half end

						19: down start			 : football
						20: down stop			 : football
						21: quarter start		 : football
						22: quarter stop		 : football

						23: group start		 : football training
						24: group stop			 : football training

						25: half start		   : rugby
						26: half stop			 : rugby
				<custom>: any other parameter that is passed will be returned in exactly the same format with syncme, gametags or tagmod
			sendSock(bool,optional) - send the tag to socket. default: True
		API args:
			tagStr(str,optional): must be either passed here as a last url segment or as parameter.
		Returns:
			(dictionary): see _tagFormat description
	""" 
	import math
	import json, os, sys
	try:
		config = settingsGet()
		if (not tagStr):
			tagStr = pu.uri.segment(3)
		#just making sure the tag was supplied
		if(not tagStr):
			return _err("Tag string not specified")

		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("tagset started-->param:{}".format(tagStr))
		
		sql = ""
		db = pu.db()
		# pre-roll - how long before the tag time to start playing back a clip
		tagVidBegin = int(config['tags']['preroll'])
		# duration is preroll+postroll
		tagVidDuration = int(config['tags']['postroll'])+tagVidBegin
		
		
		# convert the json string to dictionary
		t = json.loads(tagStr)

		if ('starttime' in t and 'duration' in t):
			tagVidBegin = t['starttime']
			tagVidDuration = t['duration']+tagVidBegin
			pu.mdbg.log("-->tagset starttime and duration used as given:{} {}", tagVidBegin, tagVidDuration)

		# t might be an array of dictionaires (size 1) or a dictionary it
		if (len(t)>0 and (not 'name' in t)):
			t = t[0] # this is an array of dictionaries - get the first element
		# make sure event is valid
		eventName = t['event']
		userhid = t['user']
		if (not 'event' in t or '/' in eventName or '\\' in eventName):
			return _err("Specify event") #event was not defined or is invalid - can't open the database
		del t['event']
		if('requesttime' in t):
			del t['requesttime'] #this is just to make sure http request does not get cashed
		# make sure event is not being stopped
		if(eventName=='live' and _stopping()):
			return _stopping(msg=True)
		if(not os.path.exists(c.wwwroot+eventName+'/video/')):
			return _err("Event does not exist")
		if (not os.path.exists(c.wwwroot+eventName+'/pxp.db')):
			# this is the first tag in the event 
			pu.disk.mkdir(c.wwwroot+eventName)
			# copy the template db for tags
			pu.disk.copy(c.wwwroot+'_db/event_template.db', c.wwwroot+eventName+'/pxp.db')
		if(not 'type' in t):
			t['type'] = 0 #if type is not defined set it to default
		else:
			t['type'] = int(t['type'])
		tagType = t['type']
		if(tagType==3):
			return _err("Attempting to create deleted tag")

		progress = 20
		cookie = False
		if ('cookie' in t):
			cookie = t['cookie']
			#resp = pu.disk.sockSendWait("APR|"+str(progress)+":"+cookie, addnewline=True, timeout=3)
			pu.disk.sockSend("APR|"+str(progress)+":"+cookie, addnewline=True)
		
		# remove any temporary id that might be associated with the tag
		if ('id' in t):
			del t['id']
		success = 1
		db.open(c.wwwroot+eventName+'/pxp.db')
		db.transBegin() #in case we need to roll it back later

		if(not 'time' in t and eventName=='live'):#time was not specified - set it to live
			t['time'] = _thumbName(totalTime=True)

		if(math.isnan(float(t['time']))):
			t['time'] = 0
		#a new tag was received - add it
		
		if (cookie):
			progress = 30
			#resp = pu.disk.sockSendWait("APR|"+str(progress)+":"+cookie, addnewline=True, timeout=3)
			pu.disk.sockSend("APR|"+str(progress)+":"+cookie, addnewline=True)
			
		if(tagType==99):
			pu.mdbg.log("-->tagset tagtype---99")			
			# type 99 is a duration tag - these ones auto-close only if from the same tablet, otherwise just create a new one
			# get device id
			if (not 'deviceid' in t): #old app builds don't have the deviceid - 'fake it' by using the user id instead, this will only work if different users are signed in on different ipads
				t['deviceid']=userhid
			devID = t['deviceid']
			# find last duration tag sent from this tablet 
			sql = "SELECT * FROM `tags` WHERE `type`=? AND `meta` LIKE ?"
			db.query(sql,(tagType,'%"deviceid": "'+devID+'"%'))
			prevTags = db.getasc()
			# auto-close previously opened duration tag from this tablet
			if(len(prevTags)>0):
				sql = "UPDATE `tags` SET `starttime`=`time`, `duration`=CASE WHEN (?-`time`)>0 THEN (?-`time`) ELSE 0 END, `type`=`type`+1 WHERE `type`=?  AND `meta` LIKE ?"
				success = success and db.query(sql,(t['time'],t['time'],tagType,'%"deviceid": "'+devID+'"%'))
				success = success and _logSql(ltype="mod_tags",lid=prevTags[-1]['id'],uid=t['user'],db=db)
				# send the closed tag to socket
				_tagFormat(event=eventName, user=userhid, tagID=prevTags[-1]['id'], db=db, checkImg=False, sockSend=True)
			# default duration for the 'start' tag is zero - it will be set when next one is laid
			t['duration']= 0				
			# regardless of preroll time, duration tags must start when the tag is laid
			t['starttime'] = t['time']
		elif(tagType&1): #odd types are tag 'start'
			# check where user is adding the start tag:
			# if it's after the last 'start' tag of the same type, simply add it and close the previous tag
			# if it's somewhere in the middle, this tag type will be automatically closed and the tag duration set
			# get all the tags of the same type that start before the current one
			sql = "SELECT * FROM `tags` WHERE (`starttime`<?) and ((`type`=?) or (`type`=?+1)) ORDER BY `starttime`"
			db.query(sql,(t['time'],tagType,tagType))
			prevTags = db.getasc()

			startTime = float(t['time'])
			if(len(prevTags)>0):
				# there are tags of the same type before this one
				# see if the last tag is odd type
				if(int(prevTags[-1]['type']) & 1):
					# last tag was odd type - just close that tag and start a new one
					# this only happens when there are no other tags of the same type after this one
					# simply update the duration and the type of the start tag
					# also set the starttime to begin when user tagged it, not at the usual -10 seconds
					# update a tag (duration will be current time minus start time). if duration is negative (user seeked back and hit tag) it will be set to zero
					sql = "UPDATE `tags` SET `starttime`=`time`, `duration`=CASE WHEN (?-`time`)>0 THEN (?-`time`) ELSE 0 END, `type`=`type`+1 WHERE `type`=?"
					success = success and db.query(sql,(t['time'],t['time'],tagType))
					success = success and _logSql(ltype="mod_tags",lid=prevTags[-1]['id'],uid=t['user'],db=db)
					# send the closed tag to socket
					_tagFormat(event=eventName, user=userhid, tagID=prevTags[-1]['id'], db=db, checkImg=False, sockSend=True)

					# default duration for the 'start' tag is zero - it will be set when next one is laid
					t['duration']= 0
				else:
					# the last tag of this type was even
					# must be adding in the middle of the event somewhere, 
					# update the duration of the last tag
					sql = "UPDATE `tags` SET `duration`=CASE WHEN (?-`time`)>0 THEN (?-`time`) ELSE 0 END WHERE `id`=?"
					success = success and db.query(sql,(t['time'],t['time'],prevTags[-1]['id']))
					success = success and _logSql(ltype="mod_tags",lid=prevTags[-1]['id'],uid=t['user'],db=db)
					# select the next tag that would follow the inserted one
					sql ="SELECT * FROM `tags` WHERE (`starttime`>=?) AND ((`type`=?) OR (`type`=?+1)) ORDER BY `starttime`"
					db.query(sql,(startTime,tagType,tagType))
					nextTag = db.getasc()
					if(len(nextTag)>0):
						# set the proper duration of the inserted tag (to be between now and the next tag)
						t['duration']=nextTag[0]['time']-startTime
						# set the new tag as even type (close it automatically)
						tagType=tagType+1
					else: #this case would only happen if there was some sort of messup with the database
						t['duration']=0
			else:#there are no tags of the same type before this one
			# either this is the first of its kind or the first tag starts after
				# check if there are any tags after the new one
				# select the next tag that would follow the inserted one (if there are any)
				sql ="SELECT * FROM `tags` WHERE (`starttime`>=?) AND ((`type`=?) OR (`type`=?+1)) ORDER BY `starttime`"
				db.query(sql,(startTime,tagType,tagType))
				nextTag = db.getasc()
				if(len(nextTag)>0):
					# there are tags of this type after - update duration of the current one
					t['duration']=nextTag[0]['time']-startTime
					# and close it automatically
					tagType=tagType+1
				elif(eventName!='live'):
					#this is the first time the tag of this type is being sent
					# and this is not a live event
					# so, close the tag since we know the duration of the video
					pass
			# regardless of preroll time, 'start' tags must start when the tag is laid
			t['starttime'] = t['time']
		#end if type is odd
		else: #for normal (event tags) the startTime will be tag time minus the pre-roll
			t['starttime'] = float(t['time'])-tagVidBegin
			if ((not 'duration' in t) or (float(t['duration'])<=0)):
				t['duration']=tagVidDuration
		#end if type is odd ... else

		#make sure starttime is not below 0
		if (t['starttime'] < 0):
			t['starttime'] = 0
		# database fields that should all be set
		tagFields = ('name', 'user', 'starttime', 'type', 'time', 'colour', 'duration', 'comment', 'rating')
		#add the tag to the database
		# set standard tag fields (that are fields in the database)
		sqlVars = ()
		for field in tagFields:
			if(not field in t):
				t[field]=""
			sqlVars += (t[field],) #each field should be added as a tuple
			del t[field] #remove the field so it doesn't get added to the extras
		# add all the other fields as json dictionary to the meta field
		meta = {}
		# the rest of the fields can be dumped as json into meta field
		sqlVars += (json.dumps(t),)
		# create a query to add the new tag
		sql = "INSERT INTO tags(name, user, starttime, type, time, colour, duration, comment, rating, meta) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
		#run it
		success = success and db.query(sql,sqlVars)
		#get the id of the newly created tag
		lastID = db.lastID()
		newTagID = lastID

		if(not success):#something went wrong, roll back the sql statement
			db.rollback()
			return _err()

		# get all the details about the tag that was created (or last line/period/etc. if a new line/period was started)
		db.commit()
		# #get the time of the current tag
		# tagTime = t['time']
		tagOut = False

		#create a thumbnail for the tag video - only do this when a tag is created
		#i.e. tagStart is not technically a "tag" - wait till the Stop is set, then make a thumbnail
		#this only happens when it's a first 'start' tag - since every other 'start' tag will 
		#automatically stop the previous start 'tag'

		# get the tag information
		tagOut = _tagFormat(event=eventName, user=userhid, tagID=lastID, db=db, checkImg=False)
		if 'success' in tagOut:
			if not tagOut['success']:
				return tagOut
		tagtime = tagOut['time']
		# a = int(tagOut)
		tagOut['newTagID']=newTagID
		#create a tag image if it doesn't exist already
		pathToEvent = c.wwwroot+eventName+'/'
		# get a list of all streams
		streams, firstStream = _listEvtSources(eventName)
		if(not streams): #there are no video sources in this event - do nothing
			return _err("there is no video in the event")
		
		if (cookie):
			progress = 50
			#resp = pu.disk.sockSendWait("APR|"+str(progress)+":"+cookie, addnewline=True, timeout=3)
			pu.disk.sockSendWait("APR|"+str(progress)+":"+cookie, addnewline=True)
			progressStep = (90-progress)/len(streams)
		
		oldStyleEvent = os.path.exists(pathToEvent+'/video/main.mp4')
		if(oldStyleEvent):
			sIdx = False
			sPrefix = ""
			sSuffix = ""
		for s in streams:
			# create a thumbnail for each stream
			# get the stream index (stream name is s_XX where XX is a two-digit index)
			q = 'hq' if('hq' in streams[s]) else 'lq'
			if(not oldStyleEvent): #new events (regardless of single or multicam) will have the format of 00lq_segmXXX.ts for segment files and list_01hq.m3u8 or main_02lq.mp4 for playlist and mp4 files
				sIdx = s.split('_')[1]+q
				sPrefix = sIdx+"_"
				sSuffix = "_"+sIdx
			imgFile = pathToEvent+"thumbs/"+sPrefix+"tn"+str(lastID)+".jpg"
			thumbAttempt = 0
			while(not os.path.exists(imgFile) and tagOut['type']!=40 and thumbAttempt<10):
				thumbAttempt += 1
				if(eventName=='live'): 
					# for live event, extract frames from .TS file
					# problem: by itself a single .TS file may not have any i-frames
					# this function will concatenate a few .ts files to ensure there's a couple i-frames there
					res = _mkThumbPrep(eventName,tagtime,sIdx)
					vidFile = res['file']
					sec = res['time']
				else:
					# for past events, the thumbnail can be extracted from the main.mp4
					vidFile = pathToEvent+"video/main"+sSuffix+".mp4"
					sec = tagtime
				if(tagOut['type']==4):
					# telestrations require full size image as well as a thumbnail
					fullimgFile = pathToEvent+"thumbs/"+sPrefix+"tf"+str(lastID)+".jpg"
					_mkThumb(vidFile, fullimgFile, sec, width=0)

				_mkThumb(vidFile, imgFile, sec) 
				if(eventName=='live'):
					try:
						# remove the (temporary) concatenated .TS file
						if (pu.pxpconfig.check_webdbg('param')):
							tmpcmd = "mv -f vidfile /tmp"
							os.system(tmpcmd)
						else:
						#----------------- no harm???
							os.remove(vidFile)
					except:
						pass
				if(not os.path.exists(imgFile)):
					sleep(2) #wait for a couple seconds before trying to create the thumbnail again - if it fails, possibly because the segments weren't written yet
			if (cookie):
				progress += progressStep
				#resp = pu.disk.sockSendWait("APR|"+str(progress)+":"+cookie, addnewline=True, timeout=3)
				pu.disk.sockSendWait("APR|"+str(progress)+":"+cookie, addnewline=True)
			#end while(no imgFile)
		#end for s in streams

		#log that a tag was created
		success = success and _logSql(ltype="mod_tags",lid=lastID,uid=userhid,db=db)
		# add to the events array to send to the socket updater
		gameEvents = [{}]
		if(tagType & 1):
			# delete last current_<type> entry
			sql = "DELETE FROM `logs` WHERE `type` LIKE ?"
			db.query(sql,('current_'+str(tagType),))
			gameEvents = [{'id':tagOut['name'], 'type':'current_'+str(tagType)}]
			success = success and _logSql(ltype="current_"+str(tagType),lid=tagOut['name'],uid=userhid,db=db)
			# success = success and _logSql(ltype="current_"+str(tagType),lid=lastID,uid=userhid,db=db)
		db.close()
		#if lastID
		if not 'id' in tagOut: #tag will not be returned - happens when line/zone/etc. is tagged for the first time
			tagOut["success"]=success
		tagOut['islive']=eventName=='live'
		if(sendSock):
			_sockData(event=eventName,tag=tagOut,gameEvents=gameEvents)

		if (cookie):
			progress = 100			
			#resp = pu.disk.sockSendWait("APR|"+str(progress)+":"+cookie, addnewline=True, timeout=3)
			pu.disk.sockSend("APR|"+str(progress)+":"+cookie, addnewline=True)
			
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("tagset -->tagOut:{}".format(tagOut))
			
		return tagOut
	except Exception as e:
		db.rollback()
		msgstr = str(sys.exc_info()[-1].tb_lineno)+str(e)
		pu.mdbg.log(msgstr)
		return _err(msgstr)

def teleset(tagStr=False):
	""" Creates a telestration
		Args:
			none
		API args:
			tag(str): json string, same as tagSet with additional parameter: sidx - index of the stream (e.g. 00hq, 01hq, etc.)
			file(file): png file with the drawing, passed as a POST form parameter
		Returns:
			(dictionary): see _tagFormat description
	""" 	
	import sys, Image
	io = pu.io
	try:
		if (not tagStr):
			tagStr = str(io.get("tag"))

		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("teleset-->param_form:{}".format(io.frm))
			#pu.mdbg.log("teleset-->tagstr:{}".format(tagStr))
			
		jsonTag = json.loads(tagStr)
		event = jsonTag['event']
		if(event=='live' and _stopping()):
			return _stopping(msg=True)
		
		# create a tag first
		t = tagset(tagStr=tagStr,sendSock=False)
		if('success' in t and not t['success']):
			return t
		if('sidx' in jsonTag):
			sIdx = jsonTag['sidx']
		else:
			sIdx = _firstSourceIdx(event)
		if(os.path.exists(c.wwwroot+event+'/video/main.mp4')):
			#this is an old style event
			sPrefix = ""
		else: #this is a new style event
			sPrefix = sIdx+'_'
			
		#upload a file with the tag name
		imgID = str(t['id'])
		io.upload(c.wwwroot+event+"/thumbs/"+sPrefix+"tl"+imgID+".png")
		# update the thumbnail with the telestration overlay
		# thumbnail image as background for telestration thumbnail
		bgFile = c.wwwroot + event+"/thumbs/"+sPrefix+"tn"+imgID+".jpg"
		# full image background as bg for telestration screenshot
		bfFile = c.wwwroot + event+"/thumbs/"+sPrefix+"tf"+imgID+".jpg"
		# overlay is the png telestration
		olFile = c.wwwroot + event+"/thumbs/"+sPrefix+"tl"+imgID+".png"
		
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("teleset-->imgID:{0}".format(imgID))		
					
		# open the image files
		bf = Image.open(bfFile) #full background
		bg = Image.open(bgFile) #thumbnail background
		ol = Image.open(olFile) #overlay - telestration

		bf = bf.convert("RGBA")
		ol = ol.convert("RGBA")
		bg = bg.convert("RGBA")

		# get the size of telestration
		(telew,teleh) = ol.size
		# resize full video to match telestration size
		bf.resize((telew,teleh),Image.ANTIALIAS)
		bf.paste(ol, (0, 0), ol)
		# save full size telestration
		bf.save(bfFile,quality=100)
		
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("teleset-->telew:{0} teleh:{1}".format(telew, teleh))		

		# get the size of the thumbnail
		(wd,hg) = bg.size
		# resize the overlay to match thumbnail
		ol = ol.resize((wd, hg), Image.ANTIALIAS)
		
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("teleset-->wd:{0} hg:{1}".format(wd, hg))		
		
		# overlay the tags
		# ol = ol.convert("RGBA")
		bg.paste(ol, (0, 0), ol)
		bg.save(bgFile,quality=100)
		sleep(2)
		_sockData(event=event,tag=t)
		
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("telelset -->output:{}".format(t))
		
		return t #already contains telestration url
	except Exception as e:
		msgstr = "No tag info specified (error: "+str(sys.exc_info()[-1].tb_lineno)+' - '+str(e) + " - " + str(imgID)
		pu.mdbg.log(msgstr)
		return _err(msgstr)

def televid(tagStr=False):
	""" Creates a video telestration
		Args:
			none
		API args:
			tag(str): see teleset description
			file(file): mp4 file with the drawing and background, passed as a POST form parameter
		Returns:
			(dictionary): see _tagFormat description
	""" 
	io = pu.io
	try:
		if (not tagStr):
			tagStr = str(io.get("tag"))

		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("televid-->tagStr:{}".format(tagStr))

		tag = json.loads(tagStr)
		event = tag['event']
		if(event=='live' and _stopping()):
			return _stopping(msg=True)
		
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("televid-->tagStr:{0} tag:{1} event:{2}".format(tagStr, tag, event))		
		
		# create a tag first
		t = tagset(tagStr=tagStr,sendSock=False)
		if('success' in t and not t['success']):
			return t
		if('sidx' in tag):
			sIdx = tag['sidx']
		else:
			sIdx = _firstSourceIdx(event)
		if(os.path.exists(c.wwwroot+event+'/video/main.mp4')):
			#this is an old style event
			sPrefix = ""
		else: #this is a new style event
			sPrefix = sIdx+'_'
		#upload a file with the tag name
		#upload a file with the tag name
		imgID = str(t['id'])
		vidFile = c.wwwroot+event+"/thumbs/tv"+imgID+".mp4"
		thmFile = c.wwwroot+event+"/thumbs/tn"+imgID+".jpg"
		io.upload(vidFile)
		while(not os.path.exists(thmFile)):
			_mkThumb(vidFile,thmFile,float(tag['duration'])-0.5)
		# create a thumbnail from the telestration
		_sockData(event=event,tag=t)
		
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("televid -->output:{}".format(t))
		
		return t #already contains telestration url
	except Exception as e:
		import sys
		msgstr = "No tag info specified (error: "+str(sys.exc_info()[-1].tb_lineno)+' - '+str(e)
		pu.mdbg.log(msgstr)
		return _err(msgstr)

def thumbcheck(dataStr=False):
	""" Verifies that a thumbnail was created, if it wasn't attempts to re-create it.
		Args:
			dataStr(str, optional): json string containing the url to the thumbnail. If unspecified, the function will attempt to extract it from the url itself. e.g.: {"url":"http://192.168.1.111/events/live/video/01hq_tn3.jpg"}. default: False
		Returns:
			(dictionary): a dictionary with "success" set to either True (if thumbnail exists or was successfully created) and False if could not re-create thumbnail. e.g.: {"success":True}
	"""
	try:
		# get image 
		if(not dataStr):
			dataStr = pu.uri.segment(3)
			
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("thumbcheck-->dataStr:{}".format(dataStr))
			
		data = json.loads(dataStr)
		# url is in the format http://192.168.1.111/events/live/video/01hq_tn3.jpg
		# get the event and the thumbnail name
		thumbName = data["thumb"]
		eventName = data["event"]
		# get the tag id associated with it
		tagID = _exNum(text=thumbName,startAtIdx=thumbName.rfind('_'))
		# path to the image file
		imgFile = c.wwwroot+eventName+'/thumbs/'+thumbName
		# id of the video source (e.g. 01hq)
		sIdx = thumbName[0:thumbName.find('_')]
		sSuffix = sIdx+'_'
		sPrefix = '_'+sIdx
		# get tag time from the event database:
		db = pu.db()
		db.open(c.wwwroot+eventName+'/pxp.db')
		sql = "SELECT `time` FROM `tags` WHERE `id`=?"
		db.query(sql,(tagID,))
		row = db.getrow()
		tagtime = row[0]
		db.close()
		# check that this image exists and attempt to re-create it if it doesn't
		thumbAttempt = 0
		while(not os.path.exists(imgFile) and thumbAttempt<10): #try 10 times to re-create it
			thumbAttempt += 1
			if(eventName=='live'): 
				# for live event, extract frames from .TS file
				# problem: by itself a single .TS file may not have any i-frames
				# this function will concatenate a few .ts files to ensure there's a couple i-frames there
				res = _mkThumbPrep(eventName,tagtime,sIdx)
				vidFile = res['file']
				sec = res['time']
			else:
				# for past events, the thumbnail can be extracted from the main.mp4
				pathToEvent = "" # jchoi: added for avoiding missing var, need to change properly
				vidFile = pathToEvent+"video/main"+sSuffix+".mp4"
				sec = tagtime
			_mkThumb(vidFile, imgFile, sec) 
			if(eventName=='live'):
				try:
					# remove the (temporary) concatenated .TS file
					os.remove(vidFile)
				except:
					pass
			if(not os.path.exists(imgFile)):
				sleep(1) #wait before trying to create the thumbnail again - if it fails, possibly because the segments weren't written yet
		#end while(no imgFile)
		return {"success":os.path.exists(imgFile)}
	except Exception, e:
		msgstr=str(e)+' '+str(sys.exc_info()[-1].tb_lineno)+' '+dataStr
		pu.mdbg.log(msgstr)
		return _err(msgstr)

def version():
	""" Retreives server version
		Args:
			none
		API args:
			none
		Returns:
			(dictionary): 
				version(str): server version
	""" 
	return {"version":c.ver}
###############################################
##			   utility functions			 ##
###############################################

def _cfgGet(cfgDir=c.wwwroot+"_db/"):
	""" Retrieves server initliaziation config file
		Args:
			cfgDir(str,optional): path to the config file (if custom).
		API args:
			N/A
		Returns:
			(list): each element is a line from the config file
	""" 
	# this function uses a simple string exclusive OR to 'encrypt' the file
	cfgFile = cfgDir+".cfg"
	saltedKey = "3b2b2bcfee23d8377a3828fe3c155a868377a38"
	# remove last 7 characters from the key
	# this is in case someone disassembles the python and finds the key
	# and tries to use the key string as they key to the config file
	key = saltedKey[:-7]
	# check if file exists
	if(not os.path.exists(cfgFile)):
		return ""
	# get the encrypted text
	encText = pu.disk.file_get_contents(cfgFile)
	# make the key and the string equal length
	key = pu.enc.repeat_str(key,len(encText))
	# xor it to decrypt the file
	decLines = pu.enc.sxor(encText,key).split("\n")
	# return the string
	if (decLines[0]==".min config file"):
		return decLines
	return ""

def _cfgSet(lines=[],cfgDir=c.wwwroot+"_db/"):
	""" Sets the lines in the config file
		Args:
			lines(list,optional): each element is a single line that will be stored to the config file. default:[]
			cfgDir(str,optional): see _cfgSet description
		API args:
			N/A
		Returns:
			(bool): whether the operation was successful
	""" 
	cfgFile = cfgDir+".cfg"
	saltedKey = "3b2b2bcfee23d8377a3828fe3c155a868377a38"
	key = saltedKey[:-7] #leave last 7 characters of the key out - if someone disassembles the code and gets this code won't be able to use it
	try:
		# merge the list items together as a single string with end-line characters
		decText = ".min config file\n"+"\n".join(lines)
		# make the key and the string equal length
		key = pu.enc.repeat_str(key,len(decText))
		# encrypt the text
		encText = pu.enc.sxor(decText,key)
		# overwite the config file
		f = open(cfgFile,"w")
		f.write(encText)
		f.close()
		return True
	except Exception as e:
		return False

def _cln(text):
	""" Cleans a string for sqlite query (doubles " quotes)
		Args:
			text(str): text to clean
		API args:
			N/A
		Returns:
			(str): sanitized text
	""" 
	import string
	return string.replace(text,'"','""')
#end cln	
def _dbgLog(msg, timestamp=True, level=0):
	""" Output debug info 

		Args:
			msg(str): message to display
			timestamp(bool,optional): display timestamp before the message. default: True
			level (int, optional): debug level (default - 0):
				0 - info
				1 - warning
				2 - error
		API args:
			N/A
		Returns:
			none
	"""
	try:
		debugLevel = 0 #the highest level to output
		if(level<debugLevel):
			return
		# if the file size is over 1gb, delete it
		logFile = "/tmp/pxp.py.log"
		with open(logFile,"a") as fp:
			fp.write(dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"))
			fp.write(msg)
			fp.write("\n")
	except Exception as e:
		pass

def _deleting():
	""" Checks if there is a delete process happening (will need to figure out later how to check what exactly is being deleted)
		Args:
			none
		API args:
			N/A
		Returns:
			(bool): whether there is a delete operation in progress
	""" 
	return pu.disk.psOn("rm -rf") or pu.disk.psOn("-exec rm {}")
#list all available mounted disks
def _diskStat( humanReadable=True, path="/"):
	""" Retrieves disk information
		Args:
			humanReadable(bool,optional): whether to return human readable sizes (e.g. Mib, Gib, etc.)
			path(str,optional): path to the mount point of the disk. default: /
		API args:
			N/A
		Returns:
			(dictionary): 
				total(str): total bytes on disk
				free(str): total bytes available on disk
				used(str): total bytes used on disk
				percent(str): percentage of total space used
	""" 
	import os
	st = os.statvfs(path)
	diskFree = st.f_bavail * st.f_frsize
	diskTotal = st.f_blocks * st.f_frsize
	diskUsed = diskTotal-diskFree
	diskPrct = int(diskUsed*100/diskTotal)
	if(humanReadable):
		 return {"total":pu.disk.sizeFmt(diskTotal),"free":pu.disk.sizeFmt(diskFree),"used":pu.disk.sizeFmt(diskUsed),"percent":str(diskPrct)}
	return {"total":diskTotal,"free":diskFree,"used":diskUsed,"percent":str(diskPrct)}

def _err( msgText=""):
	""" Creates a dictionary with an error message
		Args:
			msgText(str,optional): error message text. default: blank
		API args:
			N/A
		Returns:
			(dictionary): 
				success(bool): false
				msg(str): msgText
				action(str): popup - this is used for javascript on encoder home page
	""" 
	return {"success":False,"msg":msgText,"action":"popup"}
def _exNum( text, floatPoint=False, startAtIdx=0):
	""" Extract first number from the string

		Args:
			text (str): text to search
			floatPoint (bool, optional): whether to extract a floating point number or integer. default: False
			startAtIdx (int, optional): start searching in the text starting at this index. default: 0
		Return:
			(mixed): either float or int based on what was requested. if a number is not found, returns 0.
	"""
	import re
	try:
		# regular expression to match digits
		if floatPoint:
			return float(re.search('[0-9\.]+', text[startAtIdx:]).group())
# 		t = text.split('_')
# 		if (len(t)>2):
# 			return int(t[2].split('.')[0])
		return int(re.search('[0-9]+', text[startAtIdx:]).group())
	except:
		return 0
	
def getsidx(s):	
	if (s[0]=='s' and s[1]=='_'):		
		s = s.split('_')[1]
	return s

def isAngleFolder(event='live'):
	"""
	check if the angle folder is existing
	"""
	try:
		if (pu.pxpconfig.use_split_event_folder() and os.path.isdir(c.wwwroot+event+'/video/hq_00')):
			return True
	except:
		pass
	return False

def getlivefeedfolder(s):
	try:
		if (s==False or s==""):
			return ""
		if (not pu.pxpconfig.use_split_event_folder()):
			return ""
		if (s.find('_')>0):
			if (s[0]=='s' and s[1]=='_'):		
				s = s.split('_')[1] # i.e 00hq
		if (len(s)>=4):
			return s[2:4] + "_" + s[0:2] + "/" # hq_00/
	except:
		pass
	return ""
	
def _extractclip( tagid, event, sIdx=""):
	""" Extracts video clip and saves it as mp4 file (for bookmarks)
		Args:
			tagid(int): id of the tag to exctract as a clip
			event(str): name of the event
			sIdx(str,optional): index of the source (i.e. camera 'angle' from which to get the clip). default: use first available one
		API args:
			N/A
		Returns:
			(bool): whether the command was successful
	""" 
	from random import randrange
	import glob
	# the process is as follows:
	# 1) grab .ts files that encompass the tag duration
	# 2) concatenate them
	# 3) resize and convert to 540xHHH (keeping aspect ratio) mp4 file
	# 4) convert it back to .ts file 
	# 5) concatenate the 540x ad and the 540x video clip into one .ts
	# 6) convert the resulting .ts into mp4 file
	# get tag ID
	try:
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("_extractclip-->tagid:{} event:{} sIdx:{}".format(tagid, event, sIdx))
		
		if('/' in event or '\\' in event):
			return _err("invalid event")

		db = pu.db(c.wwwroot+event+'/pxp.db')
		# get the time from the database
		sql = "SELECT starttime, duration FROM tags WHERE id=?"
		db.query(sql,(tagid,))
		row = db.getrow()
		db.close()
		event = event.replace(' ','\ ').replace('\'','\\\'')
		# start time of the clip
		startTime = float(row[0])
		# duration of the clip (needed for extraction from .MP4)
		duration = float(row[1])


		sid = getsidx(sIdx)
		sSuffix = '_'+sid
		sPrefix = sid+'_'
#	    sSuffix = '_'+sIdx
#	    sPrefix = sIdx+'_'
		
		videoPath = c.wwwroot + event + '/video/'
		if (isAngleFolder(event)):
			if (sIdx==""):
				videoPath = c.wwwroot + event + '/video/hq_00'
			else:
				videoPath = c.wwwroot + event + '/video/' + getlivefeedfolder(sid)

		pu.mdbg.log("_extractclip =============> row:{}  videoPath:{}".format(row, videoPath))		
		
		mainMP4File = videoPath + 'main'+sSuffix+'.mp4'
		if(not os.path.exists(mainMP4File)):
			mainMP4File = c.wwwroot+event+'/video/main.mp4'
			sPrefix = ""
		bigTsFile = videoPath+"vid"+str(tagid)+".ts" #temporary .ts output file containing all .ts segments 
		bigMP4File = c.wwwroot+event+'/video/'+sPrefix+"vid_"+str(tagid)+".mp4" #converted mp4 file (low res), Need to put on live_video folder...
		tempTs = videoPath+"/int_"+str(tagid)+".ts" #TS file containing resized video clip

		# re-create existing bookmarks 
		# if (os.path.exists(bigMP4File)):
		#	 return True # no need to re-create bookmarks that already exist
		if(event!='live'):
			# for past events, the mp4 file is ready for processing, extract clip from it
			cmd = c.ffbin+" -ss "+str(startTime)+" -i "+mainMP4File+" -t "+str(duration)+" -codec copy -bsf h264_mp4toannexb "+bigTsFile
			pu.mdbg.log("-->mp4 extract:", cmd)
			os.system(cmd)
		if(not os.path.exists(bigTsFile) or event=='live'):
			# either this is a live event or failed to extract a clip from the main.mp4 (may be corrupted)
			# end time of the clip (needed for extraction from .TS fragments)
			endTime   = startTime+duration
			# pad the startTime in order to accommodate 1-2 segments that may not have video
			startTime -= 2
			if(startTime<0):#make sure it wasn't overshot
				startTime = 0
			pu.mdbg.log("_extractclip start time:{}".format(startTime))		
			strFile = _thumbName(startTime,number=True, event=event, sIdx=sIdx) #index of the starting .ts file
			pu.mdbg.log("_extractclip end time: {}".format(endTime))		
			endFile = _thumbName(endTime, number=True, event=event, sIdx=sIdx) #index of the ending   .ts file
			pu.mdbg.log("_extractclip =============>>>> startTime={}  endTime={}  | strFile={}  endFile={}".format(startTime, endTime, strFile, endFile))		
			
			
			
			# only way to extract video for live events is to concatenate .ts segments
			vidFiles = "" #small .ts files to concatenate
			#select .ts files that should be merged
			for i in range(int(strFile),int(endFile)):
				vidFiles = vidFiles+videoPath+sPrefix+"segm_"+str(i)+".ts "
			# concatenate the videos
			cmd = "/bin/cat "+vidFiles+">"+bigTsFile
			if (pu.pxpconfig.check_webdbg('param')):
				pu.mdbg.log("-->live extract:", cmd)
			os.system(cmd)
		cmd = c.ffbin+" -y -i "+bigTsFile+" -codec copy -bsf:a aac_adtstoasc "+bigMP4File
		os.system(cmd)
		if (pu.pxpconfig.check_webdbg('param')):		
			pu.mdbg.log("-->extract:", cmd)
		#remove the temporary ts file
		os.remove(bigTsFile)

		#FIGURE OUT HOW TO COMPRESS VIDEOS WITH ADS
		# randomy select an ad to add to the video
		# this list contains all the ads videos in the directory
		# adFiles = glob.glob(c.wwwroot+"/ads/*.ts")
		# if(len(adFiles)<1):#there are no ad videos to choose from - just return after creating the video mp4 file
		#	 return True

		# adFile = adFiles[randrange(0,len(adFiles))] #TS file containing small size ad video (random ad)
		# #convert small mp4 back to .ts for merging with an ad
		# cmd = "/usr/local/bin/ffmpeg -i "+bigMP4File+" -b:v 8000k -f mpegts "+tempTs #use high bitrate to ensure high ad quality
		# os.system(cmd)
		# # remove the mp4
		# os.remove(bigMP4File)
		# # merge the ad and the video file
		# cmd = "/bin/cat "+adFile+" "+tempTs+" >"+bigTsFile
		# os.system(cmd)
		# # remove temporary ts:
		# os.remove(tempTs)
		# # convert the result to an mp4 file again:
		# cmd = "/usr/bin/handbrake -q 1 -i "+bigTsFile+" -o "+bigMP4File
		# os.system(cmd)
		# # remove the temporary ts file
		# os.remove(bigTsFile)
		return True
	except Exception as e:
		import sys
		msgstr=str(sys.exc_info()[-1].tb_lineno)+' '+str(e)
		pu.mdbg.log(msgstr)
		return _err(msgstr)

def _firstSourceIdx(event):
	""" Retrieves the index of the first available video source from an event
		Args:
			event(str): name of the event
		API args:
			N/A
		Returns:
			(str): index of the source (e.g. '01hq')
	""" 
	try:
		sources, firstSource = _listEvtSources(event)
		keys = sources.keys()  # { 's_00', 's_01' ... }
		keys.sort()
		q = 'hq' if ('hq' in sources[keys[0]]) else 'lq'
		sIdx = keys[0].split('_')[1]+q
	except Exception as e:
		msgstr=str(sys.exc_info()[-1].tb_lineno)+' '+str(e)
		pu.mdbg.log(msgstr)				
		sIdx = ""
	return sIdx

#######################################################
#return salted hash sha256 of the password
#######################################################
def _hash(password):
	""" Computes a salted sha256 hash of a string
		Args:
			password(str): text to hash
		API args:
			N/A
		Returns:
			(str): hashed string
	""" 
	import hashlib
	s = hashlib.sha256(password+"azucar")
	return s.hexdigest()
#end hash

#######################################################
#initializes the encoder
#######################################################
def _init( email, password):
	""" Performs initial setup of the encoder: authenticates with cloud, gets all the information, performs first sync, downloads needed files.
		Args:
			email(str): plain text user's email
			password(str): plain text user's password
		API args:
			N/A
		Returns:
			(mixed): TRUE/FALSE whether sync was successful or not, in the event of an error, error message will be returned
	""" 
	import platform
	from uuid import getnode as mymac
	import subprocess
	# make sure the credentials were supplied
	url = "http://www.myplayxplay.net/max/activate/ajax"
	# this only works on a mac!
	serialNum = pu.osi.SN
	params = {
		'v0':pu.enc.sha('encoder'),
		'v1':pu.enc.sha(email),
		'v2':_hash(password),
		'v3':platform.uname()[1],
		'v4':str(hex(mymac()))[2:]+' - '+serialNum
	}
	resp = pu.io.send(url, params, jsn=True)
	if(resp):
		if(resp['success']):
			#create all the necessary directories
			pu.disk.mkdir(c.wwwroot+"_db")
			#save the config info
			_cfgSet([resp['authorization'],resp['customer'],"0"]) #the lines of the cfg file are: authorization, customer HID, syncLevel
			#download encoder control scripts
			# os.system("curl -#Lo "+c.wwwroot+"_db/encpause http://myplayxplay.net/.assets/min/encpause")
			# os.system("curl -#Lo "+c.wwwroot+"_db/encstart http://myplayxplay.net/.assets/min/encstart")
			# os.system("curl -#Lo "+c.wwwroot+"_db/encstop http://myplayxplay.net/.assets/min/encstop")
			# os.system("curl -#Lo "+c.wwwroot+"_db/encresume http://myplayxplay.net/.assets/min/encresume")
			os.system("curl -#Lo "+c.wwwroot+"_db/idevcopy http://myplayxplay.net/.assets/min/idevcopy.v09") #download the rquired version of idevcopy!!
			#add execution privileges for the scripts
			os.system("chmod +x "+c.wwwroot+"_db/*")
			#download the blank database files
			os.system("curl -#Lo "+c.wwwroot+"_db/event_template.db http://myplayxplay.net/.assets/min/event_template.db")
			os.system("curl -#Lo "+c.wwwroot+"_db/pxp_main.db http://myplayxplay.net/.assets/min/pxp_main.db")
			# os.system("curl -#Lo "+c.wwwroot+"_db/pxpservice.sh http://myplayxplay.net/.assets/min/pxpservice.sh")
			# os.system("curl -#Lo "+c.wwwroot+"_db/spacecheck.sh http://myplayxplay.net/.assets/min/spacecheck.sh")
			#download the config file
			os.system("curl -#Lo "+c.pxpConfigFile+" http://myplayxplay.net/.assets/min/pxpcfg.v1")
			return 1
		#there was a response but it was an error with a message
		return resp['msg']
	#either response was not received or it was a 404 or some other unexpected error occurred
	return 0
#end init
def _inited():
	""" Determines if the encoder has been initialized already
		Args:
			none
		API args:
			N/A
		Returns:
			(bool)
	""" 
	# LATER ON: check if server is online. if so, check auth code against the cloud
	cfg = _cfgGet()
	return (len(cfg)>1 and cfg[0]=='.min config file')
#end inited
#######################################################
#initializes the live directory (creates it and subfolders)
#######################################################
def _initLive():
	""" Creates live directory with required subdirectories
		Args:
			none
		API args:
			N/A
		Returns:
			none
	""" 
	pu.disk.mkdir(c.wwwroot+"live/thumbs")
	pu.disk.mkdir(c.wwwroot+"live/video")
	if(os.path.exists(c.wwwroot+"live/pxp.db")):
		os.system("rm -f "+c.wwwroot+"live/pxp.db")
	if(_stopping()):
		os.system("rm -f "+c.wwwroot+"live/stopping.txt")
	pu.disk.copy(c.wwwroot+'_db/event_template.db', c.wwwroot+'live/pxp.db')
#end initLive
#######################################################
#######################################################
def _listEvents( showDeleted=True, onlyDeleted=False, showSizes=True):
	""" Returns a list of events in the system
		Args:
			showDeleted(bool,optional): determines if the list should contain events marked as deleted. default: True
			onlyDeleted(bool,optional): will only return deleted events. this option supercedes showDeleted. default: False
			showSizes(bool,optional): show event sizes. default: True
		API args:
			N/A
		Returns:
			(list): each element is a dictioanry:
				league(str): abbreviated league name
				dateFmt(str): unformatted date
				name(str): full event name (including date and HID)
				vid(str, deprecated): url to the first available source
				vid_2(dict): dictionary of all video sources.
				deleted(bool): whether the event is marked as deleted
				homeTeam(str): name of the home team
				visitTeam(str): name of the visitor team
				datapath(str): name of the folder where event is located on the disk (relative to the events/ folder).
				date(str): formatted date and time
				sport(str): name of the sport (or event type)
				md5(str): md5 hash of the database file
				size(int): (approximate) size of all the video files for this event in bytes
	""" 
	import hashlib
	try:
		# list all all events in the local DB
		query = "" if showDeleted else ' WHERE events.deleted=0' 
		query = ' WHERE events.deleted=1' if onlyDeleted else query
		sql = "SELECT IFNULL(events.homeTeam,'---') AS `homeTeam`, \
					  IFNULL(events.visitTeam,'---') AS `visitTeam`, \
					  IFNULL(events.league,'---') AS `league`, \
					  IFNULL(events.date,'2000-01-01') AS `date`, \
					  IFNULL(events.hid,'000') AS `hid`, \
					  strftime('%Y-%m-%d_%H-%M-%S',events.date) AS `dateFmt`, \
					  leagues.sport AS `sport`, events.datapath, \
					  events.deleted AS `deleted`, \
					  IFNULL(events.extra,'{\"success\":0, \"msg\":\"\"}') AS `extra` \
				FROM `events` \
				LEFT JOIN `leagues` ON events.league=leagues.name \
				" + query + "\
				ORDER BY events.date DESC"
		if(not os.path.exists(c.wwwroot+"_db/pxp_main.db")):
			return []
		db = pu.db(c.wwwroot+"_db/pxp_main.db")		
		db.qstr(sql)
		result = db.getasc()
		if (pu.mdbg.checkscf2(pu.SCF_SHOWEVENT)):
			pu.mdbg.log("-->_listEvents:sql-->", result)		
		# go through events and check if they have videos
		i = 0
		# get the name of the live event, if it exists, like 2015-07-23_15-30-25_bddc55e16a6617be235357dce97e0ad2606a841a_local
		if(os.path.exists(c.wwwroot+'live/evt.txt')):
			liveName = pu.disk.file_get_contents(c.wwwroot+"live/evt.txt").strip()
		else:
			liveName = ""
		# get all events that exist in the database but are still being backed up (e.g. events that were just created and are being backed up remotely)
		resp = pu.disk.sockSendWait(msg="LBP|",addnewline=False)
		if(resp):
			backingup = json.loads(resp)
		else:
			backingup = { }
		for row in result:
			if(row['hid'] in backingup):
				continue #do not list events that are still being 'created'
			if(onlyDeleted):
				if(('deleted' in row) and \
					(int(row['deleted'])) and \
					(not (('datapath' in row) and os.path.exists(c.wwwroot+row['datapath'])))):
					#this event was deleted from the database and disk - remove all references
					#delete the event from the database
					sql = "DELETE FROM `events` WHERE `hid` LIKE ?"
					db.query(sql,(row['hid'],))
				#if event_is_gone
			#if onlyDeleted
			# event name
			evtName = str(row['datapath'])
			evtDir = c.wwwroot+evtName
			result[i]['name']=evtName
 			rec_stat_str = str(row['extra'])
 			if (rec_stat_str==""):
 				z = json.loads('{\"success\":0, \"msg\":\"\"}')
 			else:
 			 	z = json.loads(rec_stat_str)
			result[i]['rec_stat'] = z
			pu.mdbg.log("_listEvents------> extra_rec_stat:{}".format(rec_stat_str))
			
			# check if there is a streaming file (playlist) exists
			# add any stream playlists to the sources in this format:

			# find all cameras and qualities and add them to the array of streaming sources
			sources, firstSrc = _listEvtSources(evtName)
			if(sources):
				result[i]['vid'] = firstSrc
				result[i]['vid_2'] = sources
				result[i]['num_vid'] = len(sources)
				
			# find all mp4 files and add them to the list of downloadable files
			sources, firstSrc = _listEvtSources(evtName,srcType='main')
			if(sources):
				result[i]['mp4'] = firstSrc
				result[i]['mp4_2'] = sources
				result[i]['num_mp4'] = len(sources)

			# check if this is a live event
			if(evtName==liveName):
				sources, firstSrc = _listEvtSources('live')
				if(sources):
					result[i]['live'] = firstSrc
					result[i]['live_2'] = sources
					result[i]['num_live'] = len(sources)

			# get full folder size
			if(evtName==liveName):
				evtDir = c.wwwroot+'live'
			if(os.path.exists(evtDir) and os.path.exists(evtDir+'/pxp.db') and showSizes):
				# a quicker way to get the event size than this:
				# result[i]['size'] = pu.disk.dirSize(evtDir)
				# is this(although only approximate):
				# get all mp4 files, double their size and that will be the size of the event (approximately)
				if('mp4_2' in result[i]):
					result[i]['size'] = pu.disk.quickEvtSize(result[i]['mp4_2'])
					result[i]['size_fmt'] = pu.disk.sizeFmt(result[i]['size'])
				else:
					result[i]['size'] = 0
					result[i]['size_fmt'] = 'n/a'
			else:
				result[i]['size'] = 0
			if(os.path.exists(evtDir+'/pxp.db')):
				# get md5 checksum of the data file
				result[i]['md5'] = hashlib.md5(open(evtDir+'/pxp.db', 'rb').read()).hexdigest()
			else:
				result[i]['md5'] = ''
			#if (pu.mdbg.checkscf2(pu.SCF_SHOWEVENT)):
			#pu.mdbg.log("-->index:{0} {1}".format(i, pp.pformat(result[i])))
			i+=1
		#end for row in result
		db.close()
		return result
	except Exception as e:
		import sys
		pu.mdbg.log("[---] _listEvents:", str(e)+' '+str(sys.exc_info()[-1].tb_lineno))
		#print "listeevents--------------------------------------------------------\n\n\n\n\n\n"
		#print e,sys.exc_traceback
		return _err(str(e)+' '+str(sys.exc_info()[-1].tb_lineno)+" -- listEvents")

def _listEvtSources(evtName, srcType='list'):
	""" Gets a list of video sources for an event, puts the sources in the 'vid' element of the 'output' - for old style app; new apps will use vid_2 and mp4_2. Video files can have a suffix containing source index and quality, e.g. list_00hq.m3u8
		Args:
			evtName(str): name of the event
			srcType(str,optional): the kind of sources to list (list or main). list: m3u8 files, main: mp4 files
		API args:
			N/A
		Returns:
			(tuple): 
				[0]: list of sources
				[1]: first source
	""" 
	try:
		# [1] this is one way to get all sources (it may fail if there is a source with index > c.maxSources, but it's much faster than [2] )
		if(srcType=='list'): #looking for list*.m3u8 files			
			fName = 'list_'
			fExt = 'm3u8'
		elif(srcType=='main'): #looking for main*.mp4 files
			fName = 'main_'
			fExt = 'mp4'
		# generate a list of possible file names that may contain video:
		# this will generate names like list_00hq.m3u8, list_01lq.m3u8, etc...
		#['list_00hq.m3u8', 'list_01hq.m3u8', 'list_02hq.m3u8', .....
		fileNames = map(lambda x: fName+str(x).zfill(2)+'hq.'+fExt,range(0,c.maxSources))+map(lambda x: fName+str(x).zfill(2)+'lq.'+fExt,range(0,c.maxSources))
		# go through each file and see if it exists, if it does, that'll be a video source
		vidfiles = []
		vidsize = {}
		vidsize2 = {}
		
		# Need to check file size to see if it is completed
		video_path = c.wwwroot+evtName+'/video/'
		folder_splitted = video_path
		if (os.path.exists(video_path+'hq_00')):
			for dirname, dirnames, filenames in os.walk(video_path):
				folder_splitted = dirnames
				break
		for d in folder_splitted:
			for fn in fileNames:
				fpath = video_path + d + "/" + fn
				if(os.path.exists(fpath)):
					vidfiles.append(fn)
					fsize = os.path.getsize(fpath)
					vidsize2[fn] = str(fsize)
					if (fsize/1000000.0 > 999.9):
						vidsize[fn] = str("{:8.2f}GB".format(fsize/1000000000.0))
					else:	
						vidsize[fn] = str("{:8.2f}MB".format(fsize/1000000.0)) #<<1, should I double the size??
						
#       OLD WAY... (REPLACED due to download transmission error) - need to check file size to see if it is completed  
# 		for fn in fileNames:
# 			fpath = video_path+fn
# 			if(os.path.exists(fpath)):
# 				vidfiles.append(fn)
# 				fsize = os.path.getsize(fpath)
# 				if (fsize/1000000.0 > 999.9):
# 					vidsize[fn] = str("{:8.2f}GB".format(fsize/1000000000.0))
# 				else:	
# 					vidsize[fn] = str("{:8.2f}MB".format(fsize/1000000.0)) #<<1, should I double the size??
		# [2] this method is 100% reliable for finding correct files (*.m3u8 or *.mp4) but it's waaaaay too slow for cgi python - basically unusable without proper timeouts in the URL requests
		# vidfiles = glob.glob(c.wwwroot+evtName+'/video/*.m3u8')
		# if(len(vidfiles)<1): #there are no sources in this folder matching the search pattern
		#	 return (False, "no files")
		# return (False, "no files")
		sources = { }
		lowestIndex = 999 #this is lowest index of the stream. (e.g. if there's 00, 01, 02, it'll be set to 00 after the loop)
		firstSource = ""
		for vid in vidfiles:
			vname = vid
			vid = vid[vid.rfind('/')+1:]
			# get the source number
			nums = re.findall('\d+',vid[:vid.rfind('.')])
			if(len(nums)<1):
				# there is no number on this source, set this source index to '00'
				# most likely this is a single-source event 
				# it only contains list.m3u8 and main.mp4 files (both assumed to be HQ files)
				n = '00'
				q = 'hq'
			else:
				n = nums[0]
				# get quality (if specified)
				q = vid[vid.find(n)+len(n):vid.rfind('.')]
			if(not q):# quality isn't specified - assume it's high quality
				q = 'hq' 
			# create entry in the dictionary (if it doesn't exist yet)
			if(not ('s_'+n) in sources):
				sources['s_'+n]={ }
			# add this source to the dictionary
			if(not pu.uri.host):
				pu.uri.host=pu.io.myIP()
			sources['s_'+n][q]='http://'+pu.uri.host+'/events/'+evtName+'/video/'+vid
			
			#if (pu.pxpconfig.use_split_event_folder()):
			if (os.path.exists(c.wwwroot+evtName+'/video/hq_00')):
				if (q=='hq'):			
					sources['s_'+n][q]='http://'+pu.uri.host+'/events/'+evtName+'/video/hq_'+n+"/"+vid
					check_path = c.wwwroot+evtName+'/video/hq_'+n+"/"+vid
				else:
					sources['s_'+n][q]='http://'+pu.uri.host+'/events/'+evtName+'/video/lq_'+n+"/"+vid
					check_path = c.wwwroot+evtName+'/video/lq_'+n+"/"+vid
			else:
				sources['s_'+n][q]='http://'+pu.uri.host+'/events/'+evtName+'/video/'+vid
				check_path = c.wwwroot+evtName+'/video/'+vid
			# if one of old events didn't use split folder structure, fix path here...
			if (not os.path.exists(check_path)): 
				hq_start_idx = sources['s_'+n][q].find("/hq_")
				lq_start_idx = sources['s_'+n][q].find("/lq_")
				if (hq_start_idx>=0 or lq_start_idx>=0):
					if (hq_start_idx>=0):
						sources['s_'+n][q] = sources['s_'+n][q].replace(sources['s_'+n][q][hq_start_idx:hq_start_idx+6],"") # remove /hq_xx
					else:
						sources['s_'+n][q] = sources['s_'+n][q].replace(sources['s_'+n][q][lq_start_idx:lq_start_idx+6],"") # remove /lq_xx
			if (pu.pxpconfig.check_webdbg('param')):
				pu.mdbg.log("_listEvtSources--->SRC:{}".format(sources['s_'+n][q]))
			
			#sources['s_'+n]['vq'] = q
			sources['s_'+n]['vidsize_'+q] = vidsize[vname]			
			sources['s_'+n]['vidsize2_'+q] = vidsize2[vname]			
			#if (pu.mdbg.checkscf(pu.SCF_SHOWEVENT)):
			#pu.mdbg.log("-->_listEvtSources: s_", n, q, sources['s_'+n][q])
			if(int(n)<lowestIndex):
				lowestIndex = int(n)
				firstSource = 's_'+n
			#pu.mdbg.log("_listEvtSources--->{0} {1} firstSource:{2} n->{3} q->{4}".format(vid, nums, firstSource, n, q))
		# end for vid
		# set url (for web-based viewer) as the first source in the list
		# srcKeys = sources.keys() # list of sources
		#ORGINAL---------
		#qs = sources[firstSource].keys() # list of qualities in the 1st source
		#return (sources,sources[firstSource][qs[0]]) #return a tuple - dictionary of all found sources and the first available source (for old system compatibility)
		#----------------
		qs = sources[firstSource].keys() # list of qualities in the 1st source
		# output[key] = sources[srcKeys[0]][qs[0]] #get the first quality in the first source (usually it'll be hq)
		# output[key+'_2'] = sources.copy()
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("-->listEvtSources-->", pp.pformat(sources))
		#xq = sources['s_00']['vq']
		return (sources,sources[firstSource]['hq']) #return a tuple - dictionary of all found sources and the first available source (for old system compatibility)
	except Exception as e:
		em = str(e) + ' ' + str(sys.exc_info()[-1].tb_lineno)
		pu.mdbg.log("[---] _listEvtSources:done (reason:{}  firstSource:{})".format(em, firstSource))
		#pu.mdbg.log("[---] _listEvtSources:", em)
		#pu.mdbg.log("[---] _listEvtSources: evtName:{}  firstSource:{}  sources:{}".format(evtName, firstSource, sources))
		return (False, _err(em + " -- listEvtSources"))

#######################################################
#returns a list of teams in the system
#######################################################
def _listLeagues():
	sql = "SELECT * FROM `leagues` ORDER BY `name` ASC"
	if(not os.path.exists(c.wwwroot+"_db/pxp_main.db")):
		return []
	db = pu.db(c.wwwroot+"_db/pxp_main.db")
	db.qstr(sql)
	result = db.getasc()
	db.close()
	return result
#end _listLeagues
#######################################################
#returns a list of teams in the system
#######################################################
def _listTeams():
	sql = "SELECT * FROM `teams` ORDER BY `name` ASC"
	if(not os.path.exists(c.wwwroot+"_db/pxp_main.db")):
		return []
	db = pu.db(c.wwwroot+"_db/pxp_main.db")
	db.qstr(sql)
	result = db.getasc()
	db.close()
	return result
#end listTeams

def _log(string):

	print(string)
	os.system("echo '"+string+"' >>"+c.wwwroot+"convert.txt")
def _logSql( ltype,lid=0,uid=0,dbfile="",db=False,ms=False):
	""" Logs an entry in the sqlite database for the event (or global)
		Args:
			ltype(str): type of event to log (e.g. enc_start, sync_tablet, etc.)
			lid(int,optional): log id (e.g. device id, tag id, etc.). default: 0
			uid(str,optional): user's hid. default: 0
			dbfile(str,optional): path to the database file. default: "". NB: one of dbfile or db must be specified
			db(obj,optional): reference to the open database object. default: False. NB: one of dbfile or db must be specified
			ms(bool,optional): whether to log time in milliseconds. default: False
		API args:
			N/A
		Returns:
			(bool): whether the command was successful
	""" 
	import os
	try:
		if db:
			autoclose = False
		else:
			autoclose = True
			if(not os.path.exists(dbfile)):
				return False
			db = pu.db(dbfile)
		if (not ms):
			import time
			ms = int(round(time.time() * 1000))
		#logging an event - delete the last identical event (e.g tag_mod for specific tag id by the same user, but make sure enc_start doesn't get deleted)
		sql = "DELETE FROM `logs` WHERE (`type` LIKE ?) AND (`user` LIKE ?) AND (`id` LIKE ?) AND NOT(`type` LIKE 'enc_start')"
		db.query(sql,(ltype,uid,lid))
		#add it again
		sql = "INSERT INTO `logs`(`type`,`id`,`user`,`when`) VALUES(?,?,?,?)";
		success = db.query(sql,(ltype,lid,uid,ms))
		if(autoclose):
			# db was opened in this function - close it
			db.close()
		return success
	except Exception as e:
		return False

def _mkThumb( videoFile, outputFile, seconds, width=190, height=106):
	""" Creates a thumbnail from 'videoFile' at 'seconds' and puts it in 'outputFile' using ffmpeg
		Args:
			videoFile(str): full path to the video file
			outputFile(str): full path to the output file that will contain the image
			seconds(float): time in seconds at which to extract the image
			width(int,optional): width of the generated image in pixels. default: 190
			height(int,optional): height of the generated image in pixels. default: 106
		API args:
			N/A
		Returns:
			none
	""" 
	import os
	if not os.path.exists(videoFile):
		#there is no video for this event
		return False
	if not os.path.exists(os.path.dirname(outputFile)):
		pu.disk.mkdir(os.path.dirname(outputFile))
	
	if (pu.pxpconfig.check_webdbg('param')):
		pu.mdbg.log("_mkThumb begins-->videoFile:{} outputFile:{} seconds:{} w:{} h:{}".format(videoFile,outputFile,seconds,width,height))
		
	#make the thumbnail
	cmd = c.ffbin
	# only scale if the width is not 0
	if(width<=0):
		vidscale = ""
	else:
		vidscale = " -vf scale="+str(width)+":ih*"+str(width)+"/iw "
	# adjust seconds based on the type of video processed
	ffparams = str(seconds)+"  -i "+videoFile.replace(' ','\ ').replace('\'','\\\'')+" -vcodec mjpeg -vframes 1 -an "+vidscale+outputFile.replace(' ','\ ').replace('\'','\\\'')
	#automatically calculates height based on defined width:
	if(videoFile[-3:]=='.ts'):#exctracting frame from a stream .ts file
		# -itsoffset is slower than -ss but it allows exact seeking (past keyframes) and speed is insignificant for small files
		params = " -itsoffset -"+ffparams
	else:
		params = " -ss "+ffparams
		
	if (pu.pxpconfig.check_webdbg('param')):
		pu.mdbg.log("_mkThumb-->cmd:{0}".format(cmd+params))		
		
	os.system(cmd+params) # need to wait for response otherwise the tablet will try to download image file that does not exist yet

def _mkThumbPrep(event,seconds,sIdx=""):
	""" Prepares video file to extract thumbnail (required for live events with .ts files). 
		Must concatenate several .ts files (with at least a couple of i-frames) since just one .ts file may not have any
		
		Args:
			event (str): name of the event (path, relative to the events/ directory).
			seconds (float): absolute time in the event.
			sPrefix (mixed): stream prefix - contains index of the stream (if any). used for multicam. if unspecified, the function assumes single camera. default: empty string.
		API args:
			N/A
		Returns:
			(dictionary):
				file(str): the name of the video file containing the requested time,
				time(float): relative time to the required frame - time from the beginning of this video file
	"""
	if (pu.pxpconfig.check_webdbg('param')):
		pu.mdbg.log("_mkThumbPrep begins-->event:{} seconds:{} sIdx:{}".format(event,seconds,sIdx))
	tmBuffer = 7 #  7 #how many seconds of video to grab on each side of the specified time to extract a frame
	# get length of the video (to make sure not trying to tag at the very end of segments (won't be enough video))
	liveTime = _thumbName(totalTime=True,sIdx=sIdx,maxOnFail=True)
	if(liveTime-(seconds+tmBuffer)<2): #too close to live - the thumbnail will be garbled - wait for 2 seconds
		sleep(2)
		# seconds = max(0,seconds-2)

	strTime = seconds-tmBuffer
	if(strTime<0): 
		strTime=0
	if(sIdx):
		sPrefix = sIdx+'_'
	else:
		sPrefix = ''
		
	videoPath = c.wwwroot + event + '/video/'
	if (isAngleFolder(event)):
		if (sIdx=="" or sIdx==False):
			videoPath = c.wwwroot + event + '/video/hq_00/'
		else:
			videoPath = c.wwwroot + event + '/video/' + getlivefeedfolder(sIdx)
		
	bigTsFile = videoPath+sPrefix+"v_"+str(seconds)+".ts"
	endTime = seconds+tmBuffer
	res = {}
	strFile = _thumbName(strTime, number=True, event=event, results=res, sIdx=sIdx, maxOnFail=True) #index of the starting .ts file
	endFile = _thumbName(endTime, number=True, event=event, sIdx=sIdx, maxOnFail=True) #index of the ending .ts file

	if(strFile==endFile):
		strFile = max(int(strFile)-5,0)
		res['startTime']=2
	# print "start,end:",strFile,endFile
	# this is where the concatenated video 'actually' starts
	trueStartTime = res['startTime']
	vidFiles = "" #small .ts files to concatenate
	#select .ts files that should be merged
	for i in range(int(strFile),int(endFile)):
		filePath = videoPath+sPrefix+"segm_"+str(i)+".ts"
		filePath2 = videoPath+sPrefix+"segm_-"+str(i)+".ts"#for compatibility with some Linux segmenters (they insist on forcing a dash)
		if(os.path.exists(filePath)):
			vidFiles += filePath + " "
		elif(os.path.exists(filePath2)):
			vidFiles += filePath2 + " "
	# concatenate the video segments
	cmd = "cat "+vidFiles+">"+bigTsFile
	# print "mkthumbprep:",cmd
	os.system(cmd)
	pu.mdbg.log("_mkThumbPrep--> start file:{}  end file:{}  dur:{}".format(strFile, endFile, (int(endFile)-int(strFile))))
	pu.mdbg.log("cmd:{}".format(cmd))
	
	if (pu.pxpconfig.check_webdbg('param')):
		pu.mdbg.log("_mkThumbPrep ends-->event:{} start:{} end:{} sidx:{}".format(event,strFile,endFile,sIdx))
	
	# the required frame will be 4 seconds into the file
	return {"file":bigTsFile,"time":seconds-trueStartTime}
#end mkThumbPrep

def _postProcess():
	""" Renames live directory to its proper event name. this is done after encode has stopped
		Args:
			none
		API args:
			N/A
		Returns:
			none
	""" 
	try:
		# get the name of what the new directory should be called
		content = pu.disk.file_get_contents(c.wwwroot+"live/evt.txt")
		if (content):
			event = content.strip()
			#pu.mdbg.log("stopping event.................>>>{}".format(event))
		else:
			event = ""
		#delete the file containing the name of the event (not needed anymore)
		os.remove(c.wwwroot+"live/evt.txt")
		# rename the live to that directory
		os.rename(c.wwwroot+"live",c.wwwroot+event)
		pu.mdbg.log("live event rename to --> {}".format(c.wwwroot+event))
		# remove the stopping.txt file
		os.system("rm "+c.wwwroot+event+"/stopping.txt")
		
		# Re-create the mp4 file links after renaming the live folder
		try:
			if (pu.pxpconfig.use_split_event_folder()):
				for f in glob.glob(c.wwwroot + event + "/video/main*.mp4"):
					if (os.path.islink(f)):
						pu.mdbg.log("re-create link main --> link:{}".format(f))
		# old maiin.mp4 is not needed. This gives confusion making multi angle tag				
		# 				if (f.find('main.mp4')>0):
		# 					os.system("rm " + f)
		# 					mp4path = c.wwwroot + event + "/video/hq_00/main_00hq.mp4"
		# 					os.system("ln -s " + mp4path + " " + c.wwwroot + event + "/video/" + "main.mp4 >/dev/null 2>/dev/null")
		# 					continue
						i1 = f.find("main_")
						i2 = f.find(".mp4")
						if (i1>0 and i2>0):
							pu.mdbg.log("BEFORE f:{} --> realpath:{}".format(f, os.path.realpath(f)))
							cfeed = f[i1+5:i2]
							sidx = cfeed[0:2]
							cvq = cfeed[2:4]
							cfeedpath = c.wwwroot + event + "/video/" + cvq + "_" + sidx
							mp4path = cfeedpath + "/" + "main_" + sidx + cvq + ".mp4"
							#pu.mdbg.log("re-create link --> sidx:{} vq:{}  path:{}".format(sidx, cvq, mp4path))
							os.system("rm " + f)
							cmd = "ln -s " + mp4path + " " + c.wwwroot + event + "/video/" + "main_" + sidx + cvq + ".mp4 >/dev/null 2>/dev/null"
							os.system(cmd)
							pu.mdbg.log("AFTER f:{} --> realpath:{}".format(f, os.path.realpath(f)))
			for f in glob.glob(c.wwwroot + event + "/video/vid*.mp4"):
				pu.mdbg.log("re-create link vid--> link:{}".format(f))
				if (os.path.islink(f)): # ln -s /var/www/html/events/live/video/00hq_vid_5.mp4 vid_5.mp4
					pu.mdbg.log("{} ".format(f))
					i1 = f.find("/vid_")
					i2 = f.find(".mp4")
					if (i1>0 and i2>0):
						pu.mdbg.log("BEFORE f:{} --> realpath:{}".format(f, os.path.realpath(f)))
						i1 = f.find("/"+event)
						i2 = f.find("/video")
						pu.mdbg.log("{}  {}  {} ".format(f, i1, i2))
						if (i1>0 and i2>0):
							realpath = os.path.realpath(f)
							i1 = realpath.find("/live")
							i2 = realpath.find("/video")
							src_path = realpath[0:i1] + "/" + event + realpath[i2:]
							os.system("rm " + f)
							os.symlink(src_path, f)
							pu.mdbg.log("AFTER f:{} --> realpath:{}".format(f, os.path.realpath(f)))
			# add EXT-X-ENDLIST in the playlist					
			try:
				fc = glob.glob(c.wwwroot+event+"/video/list_*.m3u8")
				if (fc):
					for f in fc:
						if (os.path.isfile(f)):
							zstr = os.path.basename(f).split("_")
							sidx = zstr[1][0:2]
							vq = zstr[1][2:4]
							fn = c.wwwroot+event+"/video"+"/list_"+sidx+vq+".m3u8"
							if (pu.pxpconfig.use_split_event_folder()):
								fn = c.wwwroot+event+"/video/"+vq+"_"+sidx+"/list_"+sidx+vq+".m3u8"
							pl = open(fn,'rb')
							lines = pl.readlines()
							if lines:
								#first_line = lines[:1]
								last_line = lines[-1]
							pl.close()
							if (last_line.find('EXT-X-ENDLIST')<0):
								f = open(fn, 'a')
								f.write("#EXT-X-ENDLIST\n")
								f.close()
								pu.mdbg.log("ENDLIST is added in file:{} ".format(fn))
			except Exception as e:
				pu.mdbg.log("[---] add_ENDLIST: line:{} err:{}".format(sys.exc_info()[-1].tb_lineno, e))
		except Exception as e:
			pu.mdbg.log("[---] re-create link error {}".format(e))
			pass			
		
		if (content):
			pu.mdbg.log("stopping event.................{}".format(event))
			cmd = 'STK|' + event
			#pu.mdbg.log("stopping event.................{}".format(cmd))
			pu.disk.sockSend(cmd, addnewline=False)
		
	except Exception as e:
		import sys
		msgstr=str(e)+' '+str(sys.exc_info()[-1].tb_lineno)
		pu.mdbg.log(msgstr)				
		return _err(msgstr)

def _sockData(event="live",tag=False,gameEvents=[{}],data=False,db=False):
	""" Sends (tag) data to a pxpservice socket. 
		Args:
			event(str,optionanl): event name. default: live
			tag(dictionary,optional): tag dictionray to send. overrides data argument. default: False
			gameEvents(list,optional): any events that happened in the game (enc_pause, enc_start, etc.). default: []
			data(str,optional): raw data to send to socket. if tag was not specified, this value will be sent.
			db(obj,optional): reference to the open database object from which to get the event data. default: False
		API args:
			N/A
		Returns:
			none
	""" 
	if(tag):
		# tag was specified - send it to the service
		if(not db):
			# no database specified - open it
			closedb = True
			db = pu.db(c.wwwroot+event+"/pxp.db")
		else:
			# database was specified - no need to open it (or close it) here
			closedb = False
		# get teams and league HIDs
		sql = "SELECT `id` FROM `logs` WHERE `type` LIKE 'enc_start'"
		db.qstr(sql)
		teamHIDs = db.getasc()
		if (len(teamHIDs)>0): #this will be the case when there is a blank db in the event (encode was not started)
			teamHIDs = teamHIDs[0]['id'].split(',')
		if(len(teamHIDs)>2):#in case this is an old event, and the league HID is not listed along with team HIDs (comma-delimeted) in the log table, add empty value for the league
			leagueHID = teamHIDs[2]
			del(teamHIDs[2]) #remove league id from the teams list
		else:
			leagueHID = ""
		outJSON = {
			'tags':{tag['id']:tag},
			'status':encoderstatus(),
			'events':gameEvents,
			'teams':teamHIDs,
			'league':leagueHID
		}
		# send the tag (with other info) to the socket
		pu.disk.sockSend(json.dumps(outJSON))
		if(closedb): #the db was opened here - so it must be closed here as well
			db.close()
	else:
		# tag was not specified - send the raw data
		pu.disk.sockSend(data)

def _stopping(event='live',msg=False):
	""" Checks if the live event is being stopped
		Args:
			msg(bool,optional): when True, just returns a message "Event is being stopped", otherwise checks if event is stopping and returns boolean
		API args:
			N/A
		Returns:
			(mixed): boolean if msg is False, string otherwise.
	""" 
	import psutil
	#event = 'live'
	if(not msg):
		# return True
		# TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:TODO:
		# ADD PROVISION, WHEN STOPPING ONE EVENT BUT CREATING BOOKMARKS IN ANOTHER
		# FFMPEG WILL BE ACTIVE, NEED TO TAKE THAT INTO CONSIDERATION:
		# DO ANOTHER ps ax | grep COMMAND AND CHECK 
		# IF THIS FFMPEG ALSO HAS THE 'event/video' AS PART OF ITS PARAMETERS
		if(os.path.exists(c.wwwroot+event+"/stopping.txt")):
			# check if the ffmpeg command is actually using any cpu
			# find the pid's of ffmpeg and handbrake processes
			pids = []
			for proc in psutil.process_iter():
				if (proc.name == 'ffmpeg' or proc.name == 'handbrake'):
					pids.append(proc.pid)
			# find the cpu usage
			processActive = False
			for pid in pids:
				 proc = psutil.Process(pid)
				 processActive = processActive or proc.get_cpu_percent()>=1
			# if the ffmpeg is just hanging out, the event has been stopped, delete the file
			if (not processActive or event!="live"):
				os.remove(c.wwwroot+event+"/stopping.txt")
			return processActive and event=='live'
		#end if not stopping.txt
		return False
	#end if not msg
	return _err("Event is being stopped")
#end stopping

def _syncAddTags(path,tagrow,del_arr,add_arr):
	""" Adds tags to an event during the sync procedure (gets called once for each event)
		Args:
			path(str): full path to the event (including event directory)
			tagrow(dictionary): dictionary with keys as field names from tags table and values as values to insert for the tag - this is used for field names and for values for single tag addition
			del_arr(list): list of WHERE clause entries to delete from tags table (e.g. ['id=3','id=5','id=7'])
			add_arr(list): when adding multiple tags, this will contain the values for each row. field names come from tagrow.
		API args:
			N/A
		Returns:
			none
	""" 
	if(not os.path.exists(path+'/pxp.db')):
		# event directory does not exist yet
		# create it recursively (default mode is 0777)
		pu.disk.mkdir(path)
		# copy the template database there
		pu.disk.copy(c.wwwroot+'_db/event_template.db', path+'/pxp.db')
	#end if not path exists

	sql_del = "DELETE FROM `tags` WHERE"+("OR".join(del_arr))
	if(len(add_arr)<1):#nothing to add - run dummy query
		sql_ins = "SELECT 1"
	elif(len(add_arr)<2):#a single tag needs to be added - special case syntax
		sql_ins = 'INSERT INTO `tags`(`'+('`, `'.join(tagrow.keys()))+'`) VALUES("'+('", "'.join(tagrow.values()))+'") '
	else:#adding multiple tags
		sql_ins = 'INSERT INTO `tags`(`'+('`, `'.join(tagrow.keys()))+'`) SELECT '+('UNION SELECT'.join(add_arr))
	# connect to the database of the event
	db = pu.db(path+'/pxp.db')
	#delete tags that should be deleted
	db.qstr(sql_del)
	#add tags that need to be added
	db.qstr(sql_ins)
	# disconnect from the db
	db.close()
#end syncAddTags

def _syncEnc( encEmail="none",encPassw="none"):
	""" Syncs local encoder to cloud
		Args:
			encEmail(str,optional): hashed email. default: "none"
			encPassw(str,optional): hashed,salted pass. default: "none"
		API args:
			N/A
		Returns:
			(dictionary): 
				success(bool): whether the sync was successful
	""" 
	try:
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("_syncEnc ==> email:[{0}], [{1}]".format(encEmail, encPassw))
		db = pu.db()
		#open the main database (where everything except tags is stored)
		if(not db.open(c.wwwroot+"_db/pxp_main.db")):
			return _err("no database")
		url = 'http://www.myplayxplay.net/max/sync/ajax'
		# name them v1 and v2 to make sure it's not obvious what is being sent
		# v3 is a dummy variable
		# v0 is the authorization code (it will determine if this is encoder or another device)
		cfg = _cfgGet()
		if(not cfg): 
			return _err("not initialized")
		authorization = cfg[1]
		customerID = cfg[2]
		params ={   'v0':authorization,
					'v1':encEmail,
					'v2':encPassw,
					'v3':encEmail.encode("rot13"), #dummy entry
					'v4':customerID
				}
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("_syncEnc ==> v0:{0}, v1:{1}, v2:{2}, v4:{3}".format(params['v0'], params['v1'], params['v2'], params['v4']))
			# unique device ID (generated during the initial activation), aka authorization ID
			# email
			# password
			# customer id
			
		
		resp = pu.io.send(url, params, jsn=True)
		if(not resp):
			return _err("connection error")
		
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("SYNC_DATA1 ==> ", pp.pformat(resp))
		
		# DEBUG NOTE:
		# CHECK WHAT HAPPENS WHEN THERE IS NO INTERNET CONNECTION, FOR SOME REASON OUTPUT IS '0'
		# :DEBUG NOTE
		if ('success' in resp and not resp['success']):
			return _err(resp['msg'])
		# get sync level in the cloud ()
		try:
			syncData = {"level":1} #in case getting syncLevel fails
			syncData = pu.io.send("http://myplayxplay.net/max/synclevel/ajax",params,jsn=True)
			# resp = json.loads(resp)
		except Exception as e:
			pass

		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("SYNC_DATA2 ==> ", pp.pformat(syncData))

		syncLevel = syncData['level']

		tables = ['users','leagues','teams','events', 'teamsetup']

		# here we go through every table, delete all the old data and add new data
		for table in tables:
			if (resp and (not (table in resp)) or (len(resp[table])<1)):
				continue
			sql_del = "DELETE FROM `"+table+"` WHERE"
			del_arr = [] #what will be deleted
			add_arr = [] #contains sql rows that will be inserted
			# add all data rows in a single query
			for row in resp[table]:
				if (table=='users' and row['email'].find('dene')>0):
					x = 1				
				delFields = row['primary'].split(",")#contains names of the fields that are the key - used to delete entries from old tables
				# e.g. may have "player, team" as the key
				delQuery = []
				for delField in delFields:
					#contains query conditions for deletion
					delQuery.append(' `'+delField+'` LIKE "'+_cln(row[delField])+'" ')
				del_arr.append(" AND ".join(delQuery))
				#if the entry was deleted, move on to the next one (do not add it to the insert array)
				if('deleted' in row and row['deleted']=='1'):
					continue
				# sql_ins = "INSERT INTO `"+table+"`("
				# sql_vals = "VALUES("
				sql_cols = [] #column names
				sql_vals = [] #values to insert
				#go throuch each field in a row and add it to the query array

				for name in row:
					if(name=='primary' or name=='deleted'):
						continue #this is only a name of a row - not actual data
					sql_cols.append(name)
					sql_vals.append("'"+str(row[name]).replace("'","''")+"'")
				#end for name in row
				add_arr.append("INSERT INTO `"+table+"`("+','.join(sql_cols)+") VALUES ("+','.join(sql_vals)+")")
				
				#pu.mdbg.log("QUERIES1 ==> ", sql_del)
				#pu.mdbg.log("QUERIES2 ==> ", del_arr)
				#pu.mdbg.log("QUERIES3 ==> ", add_arr)
				
			#end for row in table
			sql_ins="BEGIN TRANSACTION; \n"+("; \n".join(add_arr))+"; \nCOMMIT;"
			# delete query is fairly standard: DELETE FROM `table` WHERE `field` LIKE 'value' OR `field` LIKE 'another value'
			sql_del += "OR".join(del_arr)

			if(table=='events'): #only delete events that were deleted in the cloud
				db.qstr(sql_del)
				#pu.mdbg.log("sql_del ==> ", sql_del)				
			else:#delete all the data from the table (except for events)
				db.qstr("DELETE FROM `"+table+"`")
				#pu.mdbg.log("sql_del ==> ","DELETE FROM `"+table+"`")				
			db.qstr(sql_ins,multiple=True)
			#pu.mdbg.log("sql_ins ==> ", sql_ins)				
		#foreach table
		db.qstr("INSERT OR IGNORE INTO `teams`(`hid`,`name`,`txt_name`) VALUES('00000','Unspecified','Unspecified')")
		db.close()
		#now sync tags - go to each event folder and add tags to those databases

		eventDir = "../events/"
		event = ""
		if not 'tags' in resp:
			resp['tags']={}
		lastTagRow = {}
		for tagrow in resp['tags']:
			#check if still adding tags to the same event or a new one
			if(event!=tagrow['event']):
				#new event: submit the sql query for the previous event

				# first time the loop runs event will be empty
				# run sql query only after it's been created
				if(len(event)>0):
					_syncAddTags(eventDir+event,tagrow,del_arr,add_arr)
				#if len(event)>0
				del_arr = [] #what will be deleted
				add_arr = [] #values will be added here
			#end if event != tagrow[event]

			#get the event name (used as path to the database)
			event = tagrow['event']
			#remove it from the dictionary (don't need it for the query)
			del tagrow['event']
			del_arr.append(" (`name` LIKE '"+tagrow['name']+"' AND `user` LIKE '"+tagrow['user']+"' AND `time`="+str(tagrow['time'])+") ")
			if ('deleted' in tagrow and tagrow['deleted']=='1'):
				#skip deleted tags
				continue
			fields = []
			for field in tagrow:
				fields.append('"'+_cln(tagrow[field])+'" AS `'+field+'`')
			#end for field in tagrow
			add_arr.append(", ".join(fields))
			lastTagRow = tagrow
		#end for tagrow in resp[tags]
		if (len(lastTagRow)>0):
			#last add/delete query will be run after all the tags were parsed:
			_syncAddTags(eventDir+event,lastTagRow,del_arr,add_arr)
		# update the sync level on the local encoder to the level in the cloud
		_cfgSet([cfg[1],cfg[2],str(syncLevel)])
		return {"success":True}
	except Exception as e:
		import sys
		msgstr=str(e)+' '+str(sys.exc_info()[-1].tb_lineno)		
		pu.mdbg.log("[---]_syncEnc ==> ", msgstr)
		return _err(msgstr)

def _syncTab( user, device, event, allData=False):
	""" Syncs tablet with local ecnoder (sends any tag modifications that were created in a specific event since the last sync). This also creates a sync_tab entry in the log table
		Args:
			user(str): hid of the user who is requesting info
			event(str): hid of the event
			device(str): hid of the device that is requesting info
			allData(bool): whether to retreive all data, regardless of the last sync
		API args:
			N/A
		Returns:
			(dictionary): 
				tags(dict): a dictionary of tags for the current game, keys are tag IDs. if !allData, then since last sync, otherwise all of them. for individual tag description see _tagFormat
				status(str): text status of the encoder 
				events(dict): dictionary of that happened in this game (e.g. enc_start, enc_pause, etc.)
				teams(list): list of teams in this event
				league(str): hid of the league to which this event belongs
				
	""" 
	from collections import OrderedDict
	##get the user's ip
	##userIP = os.environ['REMOTE_ADDR']
	# get the current milliseconds (to make sure the sync event is registered before any other things are logged)
	from time import time
	#pu.mdbg.log("_syncTab user:{} dev:{} evt:{} allData:{}".format(user, device, event, allData))
	ms = int(round(time() * 1000))
	if (not user) or len(user)<1 or (not device) or len(device)<1 or (not event) or len(event)<1 or ('/' in event) or ('\\' in event) or (not os.path.exists(c.wwwroot+event+"/pxp.db")):
		return [] #return empty list if user did not provide the correct info or event does not exist
	db = pu.db(c.wwwroot+event+"/pxp.db")
	try:
		if(allData):#selecting all tags from this game (assumption here - user has no tags yet, so he doesn't need to see deleted tags)
			lastup = 0
			sql = "SELECT * FROM `tags` WHERE NOT `type`=3 ORDER BY `starttime`, `duration`"
			db.qstr(sql)
		else:
			#get the time of the last update
			sql = "SELECT IFNULL(MAX(`when`),0) AS `lastUpdate` FROM `logs` WHERE `id` LIKE ? AND `user` LIKE ? AND `type` LIKE 'sync_tablet' ORDER BY `logID`"
			success = db.query(sql,(device,user))
			lastup = db.getrow()
			lastup = lastup[0]
			#if allData...else
			#get new events that happened since the last update
			#get all tag changes that were made since the last update
			sql = "SELECT DISTINCT(tags.id) AS dtid, tags.* FROM tags LEFT JOIN logs ON logs.id=tags.id WHERE (`logs`.`when`>?) AND (`logs`.`type` LIKE 'mod_tags') ORDER BY tags.starttime, tags.duration "
			# return _err(sql+' '+str(lastup))
			db.query(sql,(lastup,))
		#put them in a list of dictionaries:
		tags = db.getasc()
		#close the database (for others to access this
		db.close()
		#format tags for output
		tagsOut = OrderedDict()
		for tag in tags:
			#only even type tags are sent (normal, telestration, period/half/zone/line end tags)
			#also deleted tags are sent - to delete them from other tablets
			# if ((int(tag['type'])&1) and (not int(tag['type'])==3)):
			#	 continue
			if(str(tag['time'])=='nan'):
				tag['time']=0
			tagJSON = _tagFormat(tag=tag,event=event, user=user, db=db)
			# if(allData or not user==tag['user']):
			tagsOut[tag['id']]=(tagJSON)
		#end for tags:
		db = pu.db(c.wwwroot+event+"/pxp.db")
		#get any other events (other than tags)
		sql = "SELECT `type`, `id` FROM `logs` WHERE `when`>? AND NOT(`type` LIKE 'mod_tags' OR `type` LIKE 'sync%')"
		db.query(sql,(lastup,))
		evts = db.getasc()
		# get the teams playing
		sql = "SELECT `id` FROM `logs` WHERE `type` LIKE 'enc_start'"
		db.qstr(sql)
		teamHIDs = db.getasc()
		if (len(teamHIDs)>0): #this will be the case when there is a blank db in the event (encode was not started)
			teamHIDs = teamHIDs[0]['id'].split(',')
		if(len(teamHIDs)>2):#in case this is an old event, and the league HID is not listed along with team HIDs (comma-delimeted) in the log table, add empty value for the league
			leagueHID = teamHIDs[2]
			del(teamHIDs[2]) #remove league id from the teams list
		else:
			leagueHID = ""
		#close the database (so that log can use it)
		db.close();
		
		outJSON = {
			'tags':tagsOut,
			'status':encoderstatus(),
			'events':evts,
			'teams':teamHIDs,
			'league':leagueHID
			# 'camera':encoderstatus()
		}
		for key in outJSON.keys():
			if len(outJSON[key])<1:
				del(outJSON[key])
		if len(outJSON)>0: #only log sync when something was sync'ed
			_logSql(ltype='sync_tablet',lid=device,uid=user,dbfile=c.wwwroot+event+'/pxp.db',ms=ms)
		return outJSON
	except Exception as e:
		import sys
		msgstr=str(e)+' '+str(sys.exc_info()[-1].tb_lineno)
		pu.mdbg.log(msgstr)
		return _err(msgstr)

def _tagFormat( event=False, user=False, tagID=False, tag=False, db=False, checkImg=True, sockSend=False):
	""" Formats the tag in a proper json format and returns it as json dictionary if db is not specified, the default db from the specified 'event' will be opened
		Args:
			event(str,optional): event name. must specify this or tag. default: False
			user(str,optional): user hid. default: False
			tagID(int, optional): id of the tag to retreive from the database. must specify this or tag. default: False
			tag(dictionary, optional): dictionary, containing tag info to format. must specify this or tagID. default: False
			db(obj,optional): reference to the open database object. must specify this or event. default: False
			checkImg(bool,optional): whether to verify that the thumbnail exists. default: True
			sockSend(bool,optional): send the formatted tag to socket as well as return it
		API args:
			N/A
		Returns:
			(dictionary): 
				comment(str): any comments associated with this tag
				rating(int): tag rating
				own(bool): whether this is the user's own tag (whoever sent this request)
				duration(float): tag duration in seconds
				homeTeam(str): name of the home team
				visitTeam(str): name of the visitor team
				event(str): event name
				url_2(dictionary): dictionary of URLs of thumbnails for each video source
				telefull_2(dictionary): dictionary of URLs of full size screenshots (if applicable)
				vidurl_2(dictionary): dictionary of URLs for bookmarked clips (if applicable)
				teleurl_2(dictionary):dictionary of URLs for telestrations (if applicable)
				id(int): tag id
				type(int): tag type
				deleted(bool): whether this tag was marked as deleted
				user(str): user HID
				islive(bool): whether this tag is from a live event
				name(str): tag name
				displaytime(str): formatted in-game time (to display on the thumbnail)
				url(str,deprecated): URL of the screenshot of the first source available (used in old app builds)
				colour(str): tagging user's colour
				deviceid(str): authorization ID for the device (given during initialization)
				starttime(float): start time of the tag in seconds from the beginning of video
				time(float): time at which the tag button was pressed, in seconds from the beginning of video
				success(bool): whether the request was successful
	""" 
	import os, datetime
	try:
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("tagformat begins-->event:{0} user:{1} tagId:{2} tag:{3} checkImg:{4} sockSend:{5}".format(event, user, tagID, tag, checkImg, sockSend))
		outDict = {}
		if(tagID): #tag id was given - retreive it from the database
			sql = "SELECT * FROM `tags` WHERE `id`=?"
			if(not db):
				autoclose = True #db was not passed, open and close it in this function
				if('/' in event or '\\' in event):
					return {} #invalid event
				db = pu.db(c.wwwroot+event+"/pxp.db")
			else:
				autoclose = False #db was passed as argument - do not close it here
			db.query(sql,(tagID,))
			tag = db.getasc()
			if(len(tag)<1): #invalid tag - not found in the database
				return _err("Tag "+str(tagID)+" does not exist")
			tag = tag[0]
			if(autoclose):
				db.close()
				db = False
		#if no tagID is given, the tag fields must be passed in the tag parameter
		elif(not tag):
			# no tag id or other information given - return empty dictionary
			return {}
		if(event):
			if(event=='live'):
				# live event has the proper event name stored in a text file
				evtname = pu.disk.file_get_contents(c.wwwroot+"live/evt.txt")
				if evtname:
					evtname = evtname.strip()
				else: #could not get the name from the text file - this should never happen
					evtname = 'live'
			#if event==live
			else:# event name is just the event passed to the server
				evtname = event
			#end if event live...else
			# open the database and get the info about the event (event name is the datapath)
			tmdb = pu.db(c.wwwroot+"_db/pxp_main.db")
			sql = "SELECT * FROM `events` WHERE `datapath` LIKE ?"
			tmdb.query(sql,(evtname,))
			evtInfo = tmdb.getasc()
			tmdb.close()
			if(len(evtInfo)>0):
				tag['homeTeam']=evtInfo[0]['homeTeam']
				tag['visitTeam']=evtInfo[0]['visitTeam']
		#end if event

		# some numeric sanity checks before the round function
		if (not tag['duration']):
			tag['duration']=0.01
		if (not tag['time']):
			tag['time']=0.01

		#format some custom fields
		tag['duration']=str(round(float(tag['duration'])))[:-2]
		#time to show on the thumbnail
		tag['displaytime'] = str(datetime.timedelta(seconds=round(float(tag['time']))))

		streams, firstStream = _listEvtSources(event)
		if(not streams):
			return _err(firstStream)
		oldStyleEvent = os.path.exists(c.wwwroot+event+'/video/main.mp4')
		if(oldStyleEvent):
			sPrefix = ""

		# path to the image file (to check if it exists)
		# imgFile = c.wwwroot+event+'/thumbs/tn'+str(tag['id'])+'.jpg'
		# # check we need to check whether the thumbnail image exists
		# if (checkImg and not os.path.exists(imgFile)):
		#	 # the thumbnail image does not exist, create it
		#	 if(event=='live'):
		#		 # for live events the thumbnail must be extracted from a .TS file
		#		 # get the name of the .ts segment containing the right time				
		#		 # res = {}
		#		 # vidSegmfileName = _thumbName(tag['time'],event=event,results=res)
		#		 # vidFile = c.wwwroot+event+"/video/"+str(vidSegmfileName)
		#		 res = _mkThumbPrep(event,tag['time'])
		#		 vidFile = res['file']
		#		 sec = res['time']
		#		 # sec = res['remainder']
		#	 else:
		#		 # for past events, the thumbnail can be extracted from the main.mp4
		#		 vidFile = c.wwwroot+event+"/video/main.mp4"
		#		 sec = tag['time']

		#	 _mkThumb(vidFile, imgFile, sec)

		#	 if(event=='live'):
		#		 # delete the temporary ts file after image extraction
		#		 try:
		#			 os.remove(vidFile)
		#		 except:
		#			 pass
		# #end if checkImg

		tag['own'] = tag['user']==user #whether this is user's own tag

		if(event=='live' and os.path.exists(c.wwwroot+event+'/evt.txt')):
			tag['event'] = pu.disk.file_get_contents(c.wwwroot+event+'/evt.txt').strip()
		else:
			tag['event'] = event
		#set deleted attribute for a tag
		tag['deleted'] = tag['type']==3
		tag['success'] = True #if got here, the tag info was retreived successfully
		if('hid' in tag):
			del(tag['hid'])
		# extract metadata as individual fields
		if ('meta' in tag):
			meta = json.loads(tag['meta'])
			del tag['meta'] #remove the original meta field from the tags
			if('id' in meta): #delete 'id' from meta field - confusing with 'id' from the fields
				del meta['id']
			tag.update(meta) #join 2 dictionaries
		# send the data to the socket (broadcast for everyone)
		tag['url_2'] = {}
		tag['teleurl_2'] = {}
		tag['telefull_2'] = {}
		tag['vidurl_2'] = {}
		newFields = ['url_2', 'teleurl_2', 'telefull_2', 'vidurl_2']
		
		split_folder = isAngleFolder(event)		
		
		# for old app version, use first source for everything (thumbnail, playback, clips, etc)
		lowestIndex = 999
		for s in streams:
			q = 'hq' if ('hq' in streams[s]) else 'lq'
			sIdx = s.split('_')[1]+q
			if(not oldStyleEvent):
				sPrefix = sIdx+'_'
			videoPath = '/video/'
# 			if (split_folder):
# 				videoPath = '/video/' + getlivefeedfolder(sIdx)
			tnPath = 'http://'+pu.uri.host+'/events/'+event+'/thumbs/'+sPrefix+'tn'+str(tag['id'])+'.jpg' #thumbnail image
			tlPath = 'http://'+pu.uri.host+'/events/'+event+'/thumbs/'+sPrefix+'tl'+str(tag['id'])+'.png' #telestration drawing
			tfPath = 'http://'+pu.uri.host+'/events/'+event+'/thumbs/'+sPrefix+'tf'+str(tag['id'])+'.jpg' #full size screenshot (for telestration)
			tvPath = 'http://'+pu.uri.host+'/events/'+event+'/thumbs/'+sPrefix+'tv'+str(tag['id'])+'.mp4' #video telestration
			vuPath = 'http://'+pu.uri.host+'/events/'+event+videoPath+sPrefix+'vid_'+str(tag['id'])+'.mp4'#extracted mp4 clip

# 			if (pu.pxpconfig.check_webdbg('param')):
# 				pu.mdbg.log("tagformat-->tnPath:{0} tlPath:{1} tfPath:{2} tvPath:{3} vuPath:{4}".format(tnPath, tlPath, tfPath, tvPath, vuPath))

			tag['url_2'][s] = tnPath

			if(int(tag['type'])==4): #static telestration - add teleurl only for these tags
				tag['teleurl_2'][s]=tlPath
				tag['telefull_2'][s]=tfPath

			if(int(tag['type'])==40): #video telestration - add televid only for these tags
				tag['televid_2'][s]=tvPath

			videoPath = c.wwwroot+event+'/video/'
# 			if (split_folder):
# 				videoPath = c.wwwroot+event+'/video/' + getlivefeedfolder(sIdx)

			if(os.path.exists(videoPath+sPrefix+'vid_'+str(tag['id'])+'.mp4')): #there's a bookmark associated with this tag already
				tag['vidurl_2'][s]=vuPath
			
			# set old-app style parameters
			if(int(s.split('_')[1])<lowestIndex):
				lowestIndex=int(s.split('_')[1])
				tag['url'] = tnPath #thumbnail path
				if(int(tag['type'])==4): #static telestration - add teleurl only for these tags
					tag['teleurl']=tlPath
					tag['telefull']=tfPath
				if(int(tag['type'])==40): #video telestration - add televid only for these tags
					tag['televid']=tvPath
				if(os.path.exists(c.wwwroot+event+'/video/'+sPrefix+'vid_'+str(tag['id'])+'.mp4')): #there's a bookmark associated with this tag already
					tag['vidurl']=vuPath
					#--- THIS IS A PATCH FOR OLD BUILDS! REMOVE ASAP!!! --- #
					os.system('ln -s '+c.wwwroot+event+'/video/'+sPrefix+'vid_'+str(tag['id'])+'.mp4'+' '+c.wwwroot+event+'/video/vid_'+str(tag['id'])+'.mp4')
					tag['vidurl']='http://'+pu.uri.host+'/events/'+event+'/video/vid_'+str(tag['id'])+'.mp4'
					#--- end patch --- #

			#end if sIdx<lowestIndex
		# go through each field in the tag and format it properly
		for field in tag:
			if(not field in newFields):
				field = field.replace("_"," ") #replace all _ with spaces in the field names
			if(tag[field]== None):
				tag[field] = ''
			else:
				outDict[field]=tag[field]

		outDict['islive']=event=='live'		
		if(sockSend):
			_sockData(event=event,tag=outDict,db=db)
			
		if (pu.pxpconfig.check_webdbg('param')):
			pu.mdbg.log("tagformat-->outDict:{0}".format(outDict))
			
		return outDict
	except Exception as e:
		import sys
		msgstr=str(sys.exc_info()[-1].tb_lineno)+' '+str(e)
		pu.mdbg.log("[---] "+msgstr)		
		return _err(msgstr)

def _time(format='%Y-%m-%d %H:%M:%S',timeStamp=False):
	""" Returns timestamp formatted as specified
		Args:
			format(str,optional): hashed email. default: "none"
			timeStamp(bool,optional): return only timestamp in seco
		API args:
			N/A
		Returns:
			(dictionary): 
				success(bool): whether the sync was successful
	""" 

	from time import time as tm
	if (timeStamp):
		return str(int(tm()*1000))
	from datetime import datetime as dt
	return dt.fromtimestamp(tm()).strftime(format)
#end time

def _thumbName(seekTo=0,number=False,event="live", results={}, totalTime=False,sIdx="",maxOnFail=False):
	""" Looks through an m3u8 playlist looking for the segment with the desired time.
		Args:
			seekTo(float,optional): time (in seconds) to find in the playlist file. must specify it or totalTime default: 0
			number(bool,optional): return only the number of the segment (not the actual file name). default: False
			event(str,optional): event folder name. default: "live"
			results(dict,optional): if passed, this will contain remainder, number, firstSegm, lastSegm, startTime
			totalTime(bool,optional): causes function to return total time of the playlist (not segment name). default: False
			sIdx(str,optional): source index. default: ""
			maxOnFail(bool,optional): if could not find desired time (i.e. seekTo > totalTime), return maximum possible time from the playlist. default:False
		Returns:
			mixed: file name of the segment containing desired time, OR number of the segment file containing desired time (if number=True), OR total time of the video (if totalTime=True)
	"""
	try:
		if (pu.pxpconfig.check_webdbg('param')):			
			pu.mdbg.log("_thumbName begins-->: seekTo:{}  number:{}  event:{}  totalTime:{}  sIdx:{}  maxOnFail:{}".format(seekTo, number, event, totalTime, sIdx, maxOnFail))
		import math
		# path to the list.m3u8 file - playlist for the hls
		s = ''
		if(sIdx):
			s = getsidx(sIdx)
			sSuffix = "_"+s
		else:
			sSuffix = ""
			
		videoPath = c.wwwroot + event + '/video/'
		listPath = videoPath+"list"+sSuffix+".m3u8"
		if (isAngleFolder(event)):
			videoPath = c.wwwroot + event + '/video/' + getlivefeedfolder(s)
			listPath = videoPath + "list"+sSuffix+".m3u8"
			if (s==''):
				videoPath = c.wwwroot + event + '/video/hq_00/'
				listPath = videoPath + "list_00hq.m3u8"
		
		fileName = False
		loopingCount = 4 # max 4 seconds check
		
		while not fileName and loopingCount > 0:
			#open m3u8 file:
			#the time of the current file. e.g. if there are 50 files of 1seconds each then file50.ts will be at roughly 00:00:50 time. reachedTime contains the number of seconds since file0
			reachedTime = 0.0
			# how much time is between the beginning of the HLS segment containing the required time and the required time
			# e.g. segment starts at 953 seconds, lasts 1 second, the tagtime is at 953.73 seconds, the remainder will be 0.73s
			results['remainder']=0
			# number of the HLS segment containing the required time
			results['number']=0
			results['firstSegm']=0
			results['lastSegm']=0
			#the time within full video where the found segment actually starts
			results['startTime']=0 
			try:
				f = open(listPath,"r")
				seekTo = float(seekTo) # make sure this is not a string
			except Exception as e:
				pu.mdbg.log("[---] _thumbName.1 err:{} listPath:{} seekTo:{}".format(str(e), listPath, seekTo))
				return 0
		
			#starting from the top, add up the times until reached desired time - that's the file
			#assuming m3u8 file is in this format:
			# #EXTINF:0.98431,
			# fileSequence531.ts
			# and so on - a line with time precedes the line with file name
			# the line with time contains duration of the segment following the lin
			# when all the previous durations are summed up, we can calculate the total time
			# of the video up to a given segment
			# when the total time surpasses the SeekTo time, it means the SeekTo time is contained
			# within the next segment. the 'remainder' tells exactly where in the segment is the desired time
			lastSegTime = 0
			for line in f:
				cleanStr = line.strip()
				if(cleanStr[:7]=='#EXTINF'):#this line contains time information
					lastSegTime = float(cleanStr[8:-1])#get the number (without the trailing comma) - this is the duration of this segment file
					reachedTime += lastSegTime
					#pu.mdbg.log("======>> reachedTime={}", reachedTime)
				elif(cleanStr[-3:]=='.ts'):#this line contains filename
					if (not results['firstSegm']): #only assign the first segment once
						results['firstSegm']=cleanStr
					#name of the last reached segment
					results['lastSegm']=cleanStr
					# check if desired time was reached (and user is not looking for total time)
					if (seekTo<=reachedTime and (not totalTime)):
						fileName = cleanStr
						results['remainder']=reachedTime-seekTo
						break
					if(maxOnFail):
						fileName = cleanStr
						results['remainder']=reachedTime-seekTo
			if (pu.pxpconfig.check_webdbg('param')):			
				pu.mdbg.log("_thumbName --> path:{}  last_line:{}".format(listPath, cleanStr))
			f.close()
			results['startTime']=reachedTime - lastSegTime
			if (not number and pu.pxpconfig.check_webdbg('param')):			
				pu.mdbg.log("_thumbName --> results:{}  reachedTime:{} lastSegTime:{} fileName:{}".format(results, reachedTime, lastSegTime, fileName))
			if (not fileName):
				loopingCount -= 1
				if (pu.pxpconfig.check_webdbg('param')):			
					pu.mdbg.log("_thumbName --> null filename and check again...looping:", loopingCount)
				sleep(1)
		
		
		# if user only wants the total time 
		if (totalTime):
			return reachedTime
		if (not fileName):
			return 0
		if(number):#only return the number without the rest of the filename
			results['number']=_exNum(fileName,startAtIdx=len(sSuffix))
			if (pu.pxpconfig.check_webdbg('param')):			
				pu.mdbg.log("_thumbName --> results:{}  reachedTime:{} lastSegTime:{} fileName:{}".format(results, reachedTime, lastSegTime, fileName))
			return results['number']
		return fileName
	except Exception as e:
		import sys
		msgstr=str(sys.exc_info()[-1].tb_lineno)+' '+str(e)
		pu.mdbg.log("[---] "+msgstr)		
		return False
#end thumbname

def _xmldict(data,key="",depth=0):
	""" Convert a dictionary or list to xml
		Args:
			data(dict): dictionary to parse (or any other object type)
			key(str,optional): dictionary key (required when passing dictionary, ignored otherwise)
			depth(int,optional): current level within a dictionary (translates to how many tabs to put before the string) NB: the function will parse the ENTIRE 'data', this parameter is used only for formatting the XML output
		API args:
			N/A
		Returns:
			(str): formatted XML output
	"""
	xmlOutput = ""
	try:
		typeName = _xmltype(data)
		# dictionaries must be parsed recursively
		if(typeName=='dict'):
			# output the key
			xmlOutput+=''.rjust(depth,'\t')+'<key>'+str(key)+'</key>\n'
			# add tag detail
			xmlOutput+=''.rjust(depth,'\t')+'<dict>\n'
			# convert each of the fields recursively
			for field in data:
				# get the field type
				xmlOutput += _xmldict(data[field],field,depth+1)
			#end for field in data
			xmlOutput+=''.rjust(depth,'\t')+'</dict>\n'
		elif(typeName=='array'):
		# for array - just list the entries
			xmlOutput+=''.rjust(depth,'\t')+'<key>'+key+'</key>\n'
			# indicate that this is an array
			xmlOutput+=''.rjust(depth,'\t')+'<array>\n'
			# output all the values of the array
			for val in data:
				xmlOutput+=''.rjust(depth+1,'\t')+'<'+_xmltype(val)+'>'+str(val).replace('<','&lt;').replace('>','&gt;')+'</'+_xmltype(val)+'>\n'
				# xmlOutput += _xmldict(val,"", depth+1)
			xmlOutput+=''.rjust(depth,'\t')+'</array>\n'
		#end if array
		elif(typeName=='boolean'):
			xmlOutput+=''.rjust(depth,'\t')+'<key>'+key+'</key>\n'
			xmlOutput+=''.rjust(depth,'\t')+'<'+str(data).lower()+'/>\n'
		else:
		# regular fields are added as is:
			xmlOutput+=''.rjust(depth,'\t')+'<key>'+key+'</key>\n'
			xmlOutput+=''.rjust(depth,'\t')+'<'+typeName+'>'+str(data).replace('<','&lt;').replace('>','&gt;')+'</'+typeName+'>\n'
	except Exception as e:
		# import sys
		# return _err(str(sys.exc_info()[-1].tb_lineno)+' '+str(e))
		pass
	return xmlOutput	
#end xmldict

def _xmltype(variable):
	""" Determine variable type (used for xml parsing) and return it as string
		Args:
			variable(mixed): variable whose type needs to be determined
		API args:
			N/A
		Returns:
			(str): name of type
	"""
	varType = type(variable)
	if(varType is int or varType is long):
		return "integer"
	elif(varType is float):
		return "real"
	elif(varType is list):
		return "array"				
	elif(varType is bool):
		return "boolean"
	elif(varType is dict):
		return "dict"
	else:
		return "string"




