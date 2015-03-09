import constants as c
import os
import sys, subprocess
from threading import Thread
import time
import sqlite3
import urllib, urllib2
import base64
import sha, shelve, time, Cookie
import socket
import struct
import httplib
import StringIO
import pybonjour
import select
import psutil
class c_sqdb:
	"""Sqlite database management class"""
	con = None
	c   = None
	autocommit = True
	def __init__(self, dbpath=False):
		""" Instantiate the class
			Args:
				dbpath(str,optional): path to the .db file. if specified, it will automatically open. default: False
			Returns:
				none
		"""

		if dbpath:
			self.open(dbpath)
	def close(self):
		""" Close the db connection
			Args:
				none
			Returns:
				none
		"""
		self.autocommit = True
		try:
			if self.c:
				self.c.close()
			if self.con:
				self.con.close()
		except:
			#put some error handlers later on
			pass
	#end close()
	def commit(self):
		""" Commit a transaction
			Args:
				none
			Returns:
				none
		"""
		try:
			autoBack = self.autocommit #save the original state of the autocommit 
			self.autocommit = True
			if self.con:
				self.con.commit()
			self.autocommit = autoBack #restore the original autocommit state
		except Exception as e:
			pass
	#end commit()
   
	def getasc(self):
		""" Returns all rows of a query as a dictionary (associative array)
			Args:
				none
			Returns:
				(dictionary)
		"""
		try:
			rows = []
			cols = []
			if not self.c:
				return []
			#get column names
			for colname in self.c.description:
				cols.append(colname[0])
			#get all rows
			for row in self.getrows():
				entry = {}
				idx = 0
				for colname in cols:				
					entry[colname] = row[idx]
					idx += 1
				rows.append(entry)
		except:
			pass
		return rows
	#end getasc()
   
	def getrow(self):
		""" Returns one row from the query (as list) 
			Args:
				none
			Returns:
				(list)
		"""
		if self.c:
			return self.c.fetchone()
		return ()
	#end getrow()
   
	def getrows(self):
		""" Returns all the query rows as an array
			Args:
				none
			Returns:
				(list)
		"""
		if self.c:
			return self.c.fetchall()
		return []
	#end getrows()
   
	def lastID(self):
		""" Returns ID of the last inserted entry
			Args:
				none
			Returns:
				(str)
		"""
		if self.c:
			return self.c.lastrowid
		return False
	#end lastID()

	def numrows(self):
		""" returns number of rows from the last query 
			Args:
				none
			Returns:
				(int)
		"""
		if self.c:
			return self.c.rowcount
		return 0
	#end numrows()
   
	def open(self, dbpath):
		""" Creates connection to the database (if it wasn't opened during the init())
			Args:
				none
			Returns:
				(bool): whether the command was successful
		"""
		#open the connection:
		try:
			if self.con:#if a database connection is already open - close it
				self.close()
			#connect to the database
			connectAttempts=0
			success = False
			while(connectAttempts<20 and not success):
				connectAttempts += 1
				try:
					self.con = sqlite3.connect(dbpath,timeout=1)
					self.c = self.con.cursor()
					self.c.execute("select * from sqlite_sequence")
					test = self.c.fetchall()
					success = True
				except Exception as e:
					success = False
			# cur.execute('SELECT SQLITE_VERSION()')
			# data = cur.fetchone()
		except sqlite3.Error, e:
			#put some errors here later
			success = False
			#sys.exit(1)
		return success
	#end open()
	
	def query(self, sql, data, autocommit=True):
		""" Executes an sql query
			Args:
				sql(str): sql query to execute
				data(tuple): data to pass to the query
				autocommit(bool,optional): Whether to commit the query automatically once it executes. default: True
			Returns:
				(bool): whether the query executed successfully
		"""
		error = False
		try:#to prevent sql errors from interrupting the script
			self.c.execute(sql,data)#run the query
			if autocommit:
				self.con.commit()#commit it - without this no changes will be made to the db
		except:
			error = True
		#success when there was at least 1 row affected
		return (not error) or (self.con.total_changes >= 1) #no need to do (changes>1) AND (not error): if changes >1 then error will be false
	#end query()
	def qstr(self, query, multiple=False):
		""" Executes a query string
			Args:
				query(str): query to execute
				multiple(bool,optional): indicates whether query contains multiple queries (semicolon-delimeted). default: False
			Returns:
				(bool): whether the query executed successfully
		"""
		error = False
		try:#to prevent sql errors from interrupting the script
			if(multiple):
				self.c.executescript(query)#run the query
			else:
				self.c.execute(query)
			if self.autocommit:
				self.con.commit()#commit it - without this no changes will be made to the db
		except ValueError, e:
			error = True
		#success when there was at least 1 row affected
		return (not error) or (self.con.total_changes >= 1) #no need to do (changes>1) AND (not error): if changes >1 then error will be false
	def rollback(self):
		""" Roll back the last transaction
			Args:
				none
			Returns:
				none
		"""
		try:
			self.autocommit = True
			if self.con:
				self.con.rollback()
		except:
			pass
	#end commit()
	def transBegin(self):
		""" Begin transaction - user must commit or rollback manually
			Args:
				none
			Returns:
				none
		"""
		self.autocommit = False
	#end transBegin
#end c_sqdb
	#disk operations class

class c_disk:
	""" disk utilities class """
	def cfgGet(self, cfgfile=c.pxpConfigFile, section=False, parameter=False):
		""" Load configuration from the config file.
			Args:
				cfgfile(str,optional): path to the config file.
				section(str,optional): whether to return only a specfic section from the file. if unspecified, entire configuration will be returned default: False
				parameter(str,optional): name of the parameter from the section to retun. default: False
			Returns:
				(mixed): returns a string if it's only a specific parameter, a dictionary of the section or entire file otherwise
		"""

		import json
		try:#load all the settings
			settings = json.loads(self.file_get_contents(cfgfile))
		except:
			settings = {}
		if(section): #section was specified
			if(section in settings): #make sure it exists
				if(parameter):#parameter within this section was specified
					if(parameter in settings[section]): #parameter exists in this section - return it
						return settings[section][parameter]
					else:#parameter was not found in this section
						return False
				else:#parameter was not specified, return entire section
					return settings[section]
			else: #specified section does not exist
				return {}
		else: #section was not specified
			return settings #return all the settings
	#end cfgGet
	def cfgSet(self, cfgfile=c.pxpConfigFile, section=False, parameter=False, value=False, jsonData=False):
		""" Save a config file (either entire thing or a section, based on input)
			Args:
				cfgfile(str,optional): path to the config file.
				section(str,optional): whether to return only a specfic section from the file. if unspecified, entire configuration will be returned default: False
				parameter(str,optional): name of the parameter from the section to retun. default: False
				value(str,optional): value of the parameter to set. default: False
				jsonData(dictionary,optional): all of the settings are specified in here, not just a single section. NB: THIS WILL OVERWRITE THE ENTIRE SETTINGS FILE!
			Returns:
				(bool): True
		"""
		import json
		try: #load all the settings (to make sure nothing gets overwritten)
			settings = json.loads(self.file_get_contents(cfgfile))
		except:
			#could not load settings - probably error with the file or file doesn't exist
			settings = {}
		if(jsonData): #all of the settings are specified here - just overwrite the file WATCH OUT!!!!!
			self.file_set_contents(cfgfile, json.dumps(jsonData))
		# setting a specific section
		if(not section):
			return #if section was not specified, there's nothing to do
		if(not section in settings):
			# section does not exist yet, add it
			settings[section]={}
		if(parameter):
			# a single parameter within a section was specified
			settings[section][parameter]=value
		else:
			# overwriting the entire section
			settings[section] = value
		# write settings to the file
		self.file_set_contents(cfgfile, json.dumps(settings))
		return True
	#end cfgSet
	def copy(self, src, dst):
		""" Copy file
			Args:
				src(str): full path of file to copy
				dst(str): full path of destination
			Returns:
				none
		"""
		import shutil
		shutil.copy(src,dst)
	def dirSize(self,path):
		""" Recursively calculates size of a directory in bytes
			Args:
				path(str): full path to the directory
			Returns:
				(int): size in bytes or 0 if the directory does not exist
		"""
		if((path.lower().find('.ds_store')>=0) or (not os.path.exists(path))):
			return 0
		if(os.path.isfile(path)):
			return os.path.getsize(path)
		# print path
		total_size = 0
		for dirname in os.listdir(path):
			total_size += self.dirSize(path+'/'+dirname)
		return total_size
	def file_get_contents(self, filename):
		""" Reads an entire file
			Args:
				filename(str): file to read
			Returns:
				(str): content of the file
		"""
		import os
		if(not os.path.exists(filename)):
			return False
		contents = ""
		with open(filename,"rb") as f:
			contents = f.read()
		return contents
	def file_set_contents(self, filename,text):
		""" Writes a file with the specified contents
			Args:
				filename(str): file to write
				text(str): new contents of the file
			Returns:
				none
		"""
		f = open(filename,"w")
		f.write(text)
		f.close()	
	def getCPU(self,pgid=0,pid=0):
		""" Get cpu usage of a process
			Args:
				pgid(int,optional): process group id
				pid(int, optional): process id. one of PID or PGID must be specified
			Returns:
				(int)
		"""
		totalcpu = 0
		if(pgid):
			#list of all processes in the system
			proclist = psutil.get_process_list().copy()
			for proc in proclist:
				try:#try to get pgid of the process
					foundpgid = os.getpgid(proc.pid)
				except:
					continue #skip processes that do not exist/zombie/invalid/etc.
				if(pgid==foundpgid):#this process belongs to the same group
					try: #can use the same function recursively to get cpu usage of a single process, but creates too much overhead
						ps = psutil.Process(proc.pid)
						totalcpu += ps.get_cpu_percent(interval=1)
					except:
						continue
				#if pgid==foundpgid
			#for proc in proclist
		elif(pid):#looking for cpu usage of one process by pid
			try:
				ps = psutil.Process(pid)
				totalcpu = ps.get_cpu_percent(interval=1)
			except Exception as e:
				pass
		#get total cpu for a process
		return totalcpu
	#end getCPU

	def list(self):
		""" Lists all attached strage devices
			Args:
				none
			Returns:
				(list)
		"""
		drives = []
		try:
			if(osi.name=='mac'):
				# on a mac, all attached volumes are in /Volumes
				# drives = os.list("/Volumes")
	
				# this command might be different for linux
				listdrives=subprocess.Popen('mount', shell=True, stdout=subprocess.PIPE)
				# the output is something like this:
				# /dev/disk0s2 on / (hfs, local, journaled)
				# devfs on /dev (devfs, local, nobrowse)
				# map -hosts on /net (autofs, nosuid, automounted, nobrowse)
				# map auto_home on /home (autofs, automounted, nobrowse)
				# /dev/disk2s2 on /Volumes/3TB (hfs, local, nodev, nosuid, journaled)
				# /dev/disk3s1 on /Volumes/32gb (exfat, local, nodev, nosuid, noowners)
				# /dev/disk1s1 on /Volumes/32gb 1 (exfat, local, nodev, nosuid, noowners)
				listdrivesout, err=listdrives.communicate()
				for drive in listdrivesout.split('\n'):
					if(drive.startswith("/dev")): #this is a mounted drive. gets its mount point
						try:
							mountpoint = drive[drive.find('on /')+3:drive.rfind('(')-1]
							if(mountpoint!='/'): # / is the main drive - skip it. have to figure out how to skip a secondary drive (if there is one)
								drives.append(mountpoint)
						except: #this will happen if the format of the 'mount' output is wrong
							pass
					# driveParts = drive.split()
					# if(len(driveParts)>1 and driveParts[0].find('/dev')>=0 and driveParts[2]!='/'):
					# 	# grab full drive name (including any space it might have)
					# 	i = 2
					# 	driveName = ""
					# 	while (i<len(driveParts) and driveParts[i][0]!='('):
					# 		driveName += driveParts[i]+' '
					# 		i +=1
					# 	if(driveName != ""):
					# 		drives.append(driveName.strip())
				# for windows:
				# if 'win' in sys.platform:
				#     drivelist = subprocess.Popen('wmic logicaldisk get name,description', shell=True, stdout=subprocess.PIPE)
				#     drivelisto, err = drivelist.communicate()
				#     driveLines = drivelisto.split('\n')
		except Exception as e:
			print "[---]",e, sys.exc_traceback.tb_lineno
		return drives
	#end disklist
	def mkdir(self, dirpath, perm=0777):
		""" Creates a directory
			Args:
				dirpath(str): full path to the directory
				perm(int,optional): permissions for the new directory. default: 0777
			Returns:
				(bool) whether command was successful
		"""
		import os
		try:
			os.makedirs(dirpath,perm)
			return True
		except Exception as e:
			return False
	#end mkdir
	def psGet(self,procSearch):
		""" Returns a list of PIDs of all processes matching the procSearch string
			Args:
				procSearch(str): string to search for in a list of processes
			Returns:
				(list)
		"""
		found = []
		try:		
			procs = psutil.get_process_list() #get all processes in the system
			for proc in procs:
				try:#try to get command line for each process
					ps  = psutil.Process(proc.pid)
					if(type(ps.cmdline) is str):
						cmd = ' '.join(ps.cmdline)
					else:
						cmd = ' '.join(ps.cmdline())
					# see if this command line matches
					if(cmd.find(procSearch)>=0):
						found.append(proc.pid)
				except:
					continue #skip processes that do not exist/zombie/invalid/etc.
		except Exception as e:
			print "[---]psGet:",e,sys.exc_traceback.tb_lineno
		return found
	def psOn(self,process):
		""" Returns true if there is a specified process running. Checks if process is on (by name)
			Args:
				process(str): process name
			Returns:
				(bool)
		"""
		if (osi.name=='windows'):	#system can be Linux, Darwin
			#get all the processes for windows matching the specified one:
			cmd = "tasklist | findstr /I "+process
			#result of the cmd is 0 if it was successful (i.e. the process exists)
			return os.system(cmd)==0

		procs = psutil.get_process_list() #get all processes in the system
		for proc in procs:
			try:#try to get command line for each process
				ps  = psutil.Process(proc.pid)
				if(type(ps.cmdline) is str):
					cmd = ' '.join(ps.cmdline)
				else:
					cmd = ' '.join(ps.cmdline())
				# see if this command line matches
				if(cmd.find(process)>=0):
					return True
			except:
				continue #skip processes that do not exist/zombie/invalid/etc.
		return False
	def quickEvtSize(self,mp4List):
		""" Does a quick estimate for event size based on the list of mp4 files in that event
			Args:
				mp4List(dict): a dictionary containing URLs to the mp4 files (same as mp4_2 entry in each event from ajax/getpastevents call)
			Returns:
				(int): approximate size of the event (in bytes)
		"""
		# list is formatted as such:
		# s_02: {
		# 		hq: "http://pxp5.local/events/2015-01-29_12-04-45_5bb91fe9a9423a9fb242cf82ee62b3849cfffa7b_local/video/main_02hq.mp4"
		# 	},
		# s_00: {
		# 		hq: "http://pxp5.local/events/2015-01-29_12-04-45_5bb91fe9a9423a9fb242cf82ee62b3849cfffa7b_local/video/main_00hq.mp4"
		# 	},
		# s_01: {
		# 		hq: "http://pxp5.local/events/2015-01-29_12-04-45_5bb91fe9a9423a9fb242cf82ee62b3849cfffa7b_local/video/main_01hq.mp4"
		#	}
		totalSize = 0
		for s in mp4List:
			keys = mp4List[s].keys()
			for key in keys:
				# get the url
				url = mp4List[s][key]
				# get path part of the URI
				relPath = "/".join(url.split('/')[4:])
				# get absoulute path to the file:
				fullPath = c.wwwroot+relPath
				# get the size of the file, double it (since it will have same size in .TS segments) and add it to the total event size
				totalSize += os.path.getsize(fullPath)<<1 #<<1 is faster than *2
		return totalSize
	# end quickEvtSize

	def sockRead(self, udpAddr="127.0.0.1", udpPort=2224, timeout=0.5, sizeToRead=1):
		""" Reads data from UDP socket
			Args:
				udpAddr(str,optional): ip address of the host. default: 127.0.0.1
				udpPort(int,optional): udp port. default: 2224
				timeout(float,optional): timeout in seconds. default: 0.5s
				sizeToRead(int,optional): size in bytes to read from the socket. default: 1
			Returns:
				(str): read data
		"""

		import socket
		sock = socket.socket(socket.AF_INET, # Internet
							 socket.SOCK_DGRAM) # UDP
		sock.settimeout(timeout) #wait for 'timeout' seconds - if there's no response, server isn't running
		#bind to the port and listen
		try:
			sock.bind((udpAddr, udpPort))
			data, addr = sock.recvfrom(sizeToRead)
		except Exception as e:
			#failed to bind to that port
			data = -1
		#close the socket
		try:
			sock.close()
		except:
			#probably failed because bind didn't work - no need to worry
			pass
		return data
	def sockSend(self, msg, sockHost="127.0.0.1", sockPort=2232,addnewline=True):
		""" Sends data to the specified socket
			Args:
				msg(str): data to send to socket
				sockHost(str,optional): ip address of the host. default: 127.0.0.1
				sockPort(int,optional): udp port. default: 2232
				addnewline(bool,optional): add new line to the end of the message. default: True
			Returns:
				none
		"""
		import socket
		sent = 0
		try:
			sock = socket.socket(
				socket.AF_INET, socket.SOCK_STREAM)
			sock.settimeout(5) #wait for 'timeout' seconds, if the server doesn't respond - move on
			sock.connect((sockHost, sockPort))
			if(addnewline and msg[-2:]!="\r\n"):
				msg+="\r\n"
			sent = sock.send(msg)
			sock.close()
		except Exception as e:
			try:
				sock.close()
			except:
				pass
			return e
		return sent
	def sockSendWait(self, msg, sockHost="127.0.0.1", sockPort=2232,addnewline=True,timeout=20):
		""" Sends a message to a socket and waits for a response
			Args:
				msg(str): data to send to socket
				sockHost(str,optional): ip address of the host. default: 127.0.0.1
				sockPort(int,optional): udp port. default: 2232
				addnewline(bool,optional): add new line to the end of the message. default: True
				timeout(int,optional): how long to wait for response in seconds. default: 20s
			Returns:
				none
		"""
		import socket
		sent = 0
		chunkSize = 1024
		recvd = ""
		try:
			sock = socket.socket(
				socket.AF_INET, socket.SOCK_STREAM)
			sock.settimeout(timeout)
			sock.connect((sockHost, sockPort))
			if(addnewline and msg[-2:]!="\r\n"):
				msg+="\r\n"
			sent = sock.send(msg)
			recvd = sock.recv(chunkSize)
			newdata = recvd
			while(len(newdata)>=chunkSize):
				newdata = sock.recv(chunkSize)
				recvd +=newdata
			sock.close()
		except Exception as e:
			try:
				sock.close()
			except:
				pass
		return recvd
	# diskStat
	def stat(self, humanReadable=True, path="/"):
		""" Returns information about a disk
			Args:
				humanReadable(bool): return sizes in human-friendly form (e.g. Kb Mb, Gb, etc.). if false, returns sizes in bytes. default: False
				path(str): path to the mounted drive. default: /
			Returns:
				(dictionary):
					total: total disk size
					free: free bytes
					used: used bys
					percent: how much of the disk is used
		"""
		st = os.statvfs(path)
		diskFree = st.f_bavail * st.f_frsize
		diskTotal = st.f_blocks * st.f_frsize
		diskUsed = diskTotal-diskFree
		diskPrct = int(diskUsed*100/diskTotal)
		if(humanReadable):
	 		return {"total":self.sizeFmt(diskTotal),"free":self.sizeFmt(diskFree),"used":self.sizeFmt(diskUsed),"percent":str(diskPrct)}
	 	return {"total":diskTotal,"free":diskFree,"used":diskUsed,"percent":str(diskPrct)}
	 #end stat
	def sizeFmt(self, size):
		""" Formats the sizes in bytes in human readable form.
			Args:
				size(int): size in bytes
			Returns:
				(str)
		"""
		s = float(size)
		#size names
		sizeSuffix = ['b','KB','MB','GB','TB','PB','EB','ZB','YB']
		for x in sizeSuffix:			
			if s < 1024 or x==sizeSuffix[len(sizeSuffix)-1]:
				#either reached the capacity (i.e. size will be under 1024)
				#or reached the end of suffixes (highly unlikely)
				return "%0.2f %s" % (s, x)
			s = s / 1024
		return ""
	def treeList(self, path, prefix=""):
		""" Returns directory tree (in a linear list) 
			Args:
				path(str): full path to the source folder
				prefix(str,optional): prefix to append to each entry in the returned list
			Returns:
				(list)
		"""
		tree = []
		if(not os.path.exists(path)):
			return tree
		dirlist = os.listdir(path)
		for item in dirlist:
			if(item=='.' or item=='..'):
				continue
			if(os.path.isdir(path+'/'+item)): #this is a sub-directory, get its tree structure
				tree.append(prefix+item+'/')
				tree += self.treeList(path+'/'+item,prefix+item+'/')
			elif(os.path.isfile):
				tree.append(prefix+item)
		return tree
	#end treeRead
#end c_disk class

class c_enc:
	"""encryption/string operations class"""
	def sha(self,string):
		""" Return sha1 hash of the string
			Args:
				string(str): string to hash
			Returns:
				(str)
		"""
		import hashlib
		s = hashlib.sha1(string)
		return s.hexdigest()
	def repeat_str(self, string_to_expand, length):
		""" Repeats the string up to 'length' characters
			Args:
				string_to_expand(str): original string
				length(int): what should be the maximum new length of the string
			Returns:
				(str)
		"""
		return (string_to_expand * ((length/len(string_to_expand))+1))[:length]
	def sxor(self, s1,s2):
		""" Performs bitwise exclusive or on 2 strings. Must be of equal length, otherwise result will be trimmed to the shortest string
			Args:
				s1(str):string to compare
				s2(str):string to compare
			Returns:
				(str)
		"""
		# convert strings to a list of character pair tuples
		# go through each tuple, converting them to ASCII code (ord)
		# perform exclusive or on the ASCII code
		# then convert the result back to ASCII (chr)
		# merge the resulting array of characters as a string
		return ''.join(chr(c) for c in [ord(a) ^ ord(b) for a,b in zip(s1,s2)])
	#end sxor
#end enc class

#os info class
class c_osi:
	"""os info class"""
	name = None
	SN = ""
	def __init__(self):
		try:
			# get OS type
			if(sys.platform.lower().find('darwin')>=0):
				self.name = 'mac'
			elif(sys.platform.lower().find('linux')>=0):
				self.name = 'linux'
			elif(sys.platform.lower().find('win32')>=0):
				self.name = 'windows'
			# get serial number
			if (self.name=='mac'): 
				try:
					proc = subprocess.Popen('ioreg -l | grep -e \'"Serial Number" =\'',shell=True,stdout=subprocess.PIPE)
					serialNum = ""
					# the output will be similar to:
					#	 |   "IOPlatformSerialNumber" = "C07JKA31DWYL"
					for line in iter(proc.stdout.readline,""):
						if(line.find("\"")):
							lineParts = line.split("\"")
							if(len(lineParts)>3):
								serialNum +=lineParts[3]
				except Exception as e:
					serialNum = "n/a"
			elif(self.name=='linux'): #linux
				try: #NB!! make sure dmidecode utility is installed!!! 
					 #NB!! on some systems you might need to do 
					 #	 'dmidecode -s system-serial-number' instead of '... system-uuid'
					proc = subprocess.Popen('dmidecode -s system-uuid',shell=True,stdout=subprocess.PIPE)
					serialNum = ""
					for line in iter(proc.stdout.readline,""):
						serialNum = line
				except Exception as e:
					serialNum = "n/a"
			self.SN = serialNum.strip()
		except Exception as e:
			print "osi init error: ", e, sys.exc_traceback.tb_lineno
class c_io:
	"""web input/output class"""
	frm = None
	def __init__(self):
		if (osi.name=='linux'):
			pass #on linux using flask field storage is managed externally
		elif (osi.name == 'mac'):
			import cgi
			if not self.frm:
				self.frm = cgi.FieldStorage()
	def get(self, fieldName):
		""" Get a POST parameter from the form
			Args:
				none
			Returns:
				none
		"""
		try:
			if(osi.name=='linux'):
				return self.frm[fieldName]
			elif(osi.name=='mac'):
				return self.frm.getvalue(fieldName)
		except:
			return False
	#end get
	def isweb(self):
		""" Checks if there is connection to myplayxplay.net website
			Args:
				none
			Returns:
				(bool)
		"""
		import urllib2
		from time import time as tm				
		try:
			timestamp = str(int(tm()*1000))
			response=urllib2.urlopen('http://myplayxplay.net/?timestamp='+timestamp,timeout=10)
			return True
		except Exception as e: pass
		return False
	def myIP(self,allDevs=False):
		""" Determines local IP address
			Args:
				allDevs(bool,optional): whether to retreive IP addresses of all network adapters. default: False
			Returns:
				(mixed): string with IP if allDevs is False, a list with all IPs otherwise
		"""
		try:
			import sys, netifaces as ni
			ips = []
			ipaddr = "127.0.0.1"
			ips.append(ipaddr)
			for dev in ni.interfaces():
				adds = ni.ifaddresses(dev)
				for addr in adds:
					for add in adds[addr]:
						if('addr' in add):
							ip = add['addr']
							ipp = ip.split('.')
							if(len(ipp)==4 and ip!=ipaddr): #this is a standard X.X.X.X address (ipv4)
								ipaddr = ip
							if(not self.sameSubnet("127.0.0.1",ipaddr)): #first non-localhost ip found returns - should be en0 - or ethernet connection (not wifi)
								if(not allDevs):
									return ipaddr
								if(not ipaddr in ips):
									ips.append(ipaddr)
		except Exception as e:
			print "error in myIP: ", e, sys.exc_traceback.tb_lineno
		if(allDevs):
			return ips
		return ipaddr
	def myName(self):
		""" Find local computer name (i.e. hostname)
			Args:
				none
			Returns:
				(str)
		"""
		try:
			name	= socket.gethostname() #computer name
			if(name[-6:]=='.local'):# hostname ends with .local, remove it
				name = name[:-6]
			# append mac address as hex ( [2:] to remove the preceding )
			# name += ' - '+ hex(getmac())[2:]
			return name
		except Exception as e:
			print "[---]io.myName: ", e, sys.exc_traceback.tb_lineno
		return ""	
	def ping(self,host):
		""" Ping a host 
			Args:
				host(str): host address
			Returns:
				(bool): whether the host is alive
		"""
		try:
			return os.system("ping -c 1 -W 1000 "+host+" > /dev/null") == 0
		except:
			return False
	def sameSubnet(self, ip1,ip2):
		""" Returns true if both ip addresses belong to the same subnet"""
		try:
			return ".".join(ip1.split('.')[:3])==".".join(ip2.split('.')[:3])
		except:
			return False
	#end sameSubnet
	def send(self,url,params,jsn=False):
		""" Sends a POST request
			Args:
				url(str): where to send the request
				params(dictionary): fields to include in the request
				jsn(bool,optional): whether to to parse the JSON object in the response. default: False
			Returns:
				(mixed): bool(success/fail) if jsn==False, dictionary otherwise
		"""
		import httplib, urllib, urlparse, json
		try:
			headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
			parsed = urlparse.urlparse(url)
			conn = httplib.HTTPConnection(parsed.netloc)
			conn.request("POST", parsed.path, urllib.urlencode(params),headers)
			r1 = conn.getresponse()
			if(jsn):
				try:
					return json.loads(r1.read())
				except:
					return False
			return r1.read()
		except:
			return False
	#end send
	def upload(self, filePath):
		""" Upload a file from web interface to this python script
			Args:
				filePath(str): where to save the file
			Returns:
				(bool): received the file successfully
		"""
		form = self.frm
		# A nested FieldStorage instance holds the file
		fileitem = form['file']
		# Test if the file was uploaded
		if fileitem.filename:
			# strip leading path from file name to avoid directory traversal attacks
			# fn = os.path.basename(fileitem.filename) # don't need file name
			f = open(filePath, 'wb')
			if not f:
				return False
			f.write(fileitem.file.read())
			f.close()
			return True
		return False
		#end fileitem
	#end upload
	def uploadCloud(self,url,filePath,params={}):
		""" Uploads a file to a remote location (via form POST request)
			Args:
				url(str): url where to upload the file (e.g. www.server.com/upload.php)
				filePath(str): full path to the local file to upload
				params(dict,optional): any additional parameters to send with the file. default: {}.
			Returns:
				(mixed): upon successful request, response from the remote server. if request failed or the local file does not exist, will return False
		"""
		from poster.encode import multipart_encode
		from poster.streaminghttp import register_openers
		import urllib2
		try:
			if (not os.path.exists(filePath)):
				return False
			# Register the streaming http handlers with urllib2
			register_openers()

			# Start the multipart/form-data encoding of the file "DSC0001.jpg"
			# "image1" is the name of the parameter, which is normally set
			# via the "name" parameter of the HTML <input> tag.

			# headers contains the necessary Content-Type and Content-Length
			# datagen is a generator object that yields the encoded parameters
			formFields = params
			formFields.update({"qqfile": open(filePath, "rb")})
			datagen, headers = multipart_encode(formFields)

			# Create the Request object
			request = urllib2.Request(url, datagen, headers)
			# Actually do the request, and get the response
			response = urllib2.urlopen(request).read()
			try:
				# try to return json-formatted response if it was json
				return json.loads(response)
			except:
				# if the response wasn't json, just return it as is
				return response
		except Exception as e:
			return False
	def url(self,url,params=False,timeout=60, username=False, password=False):
		""" Creates a url call (i.e. a 'get' request)
			Args:
				url(str): url to request
				params(dictionary,optional): additional parameters to send along with request. default: False
				timeout(int, optional): time in seconds to wait before declaring a timeout. default: 60s
				username(str,optional): username for BASIC authentication. default: False.
				password(str,optional): password for BASIC authentication. default: False.
			Returns:
				(str): response text
		"""
		try:
			if(params):
				data = urllib.urlencode(params)
				req = urllib2.Request(url,data)
			else:
				req = urllib2.Request(url)
			if(username and password):
				base64string = base64.encodestring('%s:%s' % (username, password))[:-1]
				authheader =  "Basic %s" % base64string
				req.add_header("Authorization", authheader)
			answer = urllib2.urlopen(req,timeout=timeout)
			respText = answer.read()
			# if(not respText):
				# return True
			return respText
		except Exception as e:
			print "[---]urlERR:",e, sys.exc_traceback.tb_lineno, '---url:',url
			return False
	def urlFile(self,url,params=False,timeout=60,dst="./file"):
		""" Downloads a file form url to dst, does chunked download (in case the file is large)
			Args:
				url(str): link to the remote file
				params(dictionary,optional): additional parameters to send along with request. default: False
				timeout(int, optional): time in seconds to wait before declaring a timeout. default: 60s
				dst(str,optional): where to save the file. default: ./file
			Returns:
				(bool): whether the download was successful
		"""
		try:
			if(params):
				data = urllib.urlencode(params)
				req = urllib2.Request(url,data)
			else:
				req = urllib2.Request(url)
			answer = urllib2.urlopen(req,timeout=timeout)
			chunkSize = 1024 * 1024
			with open(dst, 'wb') as fp:
				while True:
					chunk = answer.read(chunkSize)
					if (not chunk): 
						break
					fp.write(chunk)
				#end while
			#end with
			return True
		except Exception as e:
			print "[---]urlFile",e,sys.exc_traceback.tb_lineno, url
			return False
	#end urlFile
	def urlexists(self,urlpath):
		""" Check if the url is responsive
			Args:
				urlpath(str): url to check
			Returns:
				(bool)
		"""
		import httplib
		# remove the beginning http:// if it's there
		prefix = "http://"
		if(urlpath[:7]=='http://'):
			urlpath = urlpath[7:]
		if(urlpath[:8]=='https://'):
			prefix = "https://"
			urlpath = urlpath[8:]
		# make sure url ends with /
		if(urlpath[-1:]!='/'):
			urlpath = urlpath+'/'
		site = urlpath[:urlpath.find('/')]
		path = urlpath[urlpath.find('/'):-1] #exclude trailing slash from path
		conn = httplib.HTTPConnection(prefix+site)
		conn.request('HEAD', path)
		response = conn.getresponse()
		conn.close()
		return response.status > 308
	#end urlexists
#end c_io class

class c_session(object):
	""" Session management class """
	def close(self):
		""" Close the session
			Args:
				none
			Returns:
				none
		"""
		try:
			self.data.close()
		except:
			pass
	def destroy(self):
		""" Close session and destroy the session variables
			Args:
				none
			Returns:
				none
		"""
		self.close()
		try:
			self.data = None
		except:
			pass
	#end close
	# by default session expires in 1 day
	def start(self, expires=24*60*60, cookie_path="/"):
		""" Start a new session
			Args:
				expires(int,optional): expiration time in seconds for the session. default: 86400s (1 day)
				cookie_path(str,optional): where to store cookies with session ID. default: /
			Returns:
				none
		"""
		try:
			string_cookie = os.environ.get('HTTP_COOKIE', '')
			self.cookie = Cookie.SimpleCookie()
			self.cookie.load(string_cookie)
			if self.cookie.get('sid'):
				sid = self.cookie['sid'].value
				# Clear session cookie from other cookies
				self.cookie.clear()
			else:
				self.cookie.clear()
				sid = sha.new(repr(time.time())).hexdigest()
			self.cookie['sid'] = sid
			if cookie_path:
				self.cookie['sid']['path'] = cookie_path
			session_dir = c.wwwroot+"session/"
			if not os.path.exists(session_dir):
				disk.mkdir(session_dir,0770)
			self.data = shelve.open(session_dir + 'sess_' + sid, writeback=True)
			# os.chmod(session_dir + '/sess_' + sid, 0660)
			
			# Initializes the expires data
			if not self.data.get('cookie'):
				self.data['cookie'] = {'expires':''}
			self.set_expires(expires)
			print("%s"%(self.cookie))
		except Exception as e:
			# pass
			print(sys.exc_traceback.tb_lineno, e)
	#end start
	def set_expires(self, expires=24*60*60):
		""" Sets new expiration time for a session
			Args:
				expires(int, optional): new expiration time in seconds from current time. default: 1 day
			Returns:
				none
		"""

		if expires == '':
			self.data['cookie']['expires'] = ''
		elif isinstance(expires, int):
			self.data['cookie']['expires'] = expires
		self.cookie['sid']['expires'] = self.data['cookie']['expires']
	#end set_expires
#end session class

# class c_ssdp:
# 	# waits for a device to announce itself on the network, any announcements that were made prior to executing .discover() will not appear here
# 	# this method works better for matrox since it announces itself every 5 seconds or so
# 	# for devices that announce themselves infrequently, this method will have to wait for the announcement
# 	class ssdpObject(object):
# 		def __init__(self, response):
# 			self.location 	= ""
# 			self.usn 		= ""
# 			self.st 		= ""
# 			# get LOCATION
# 			posstr = response.find("LOCATION:")
# 			if(posstr>=0):
# 				posend = response.find("\n",posstr)
# 				self.location = response[posstr+10:posend-1].strip()
# 			# get USN
# 			posstr = response.find("USN:")
# 			if(posstr>=0):
# 				posend = response.find("\n",posstr)
# 				self.usn = response[posstr+4:posend-1].strip()
# 			# get NT
# 			posstr = response.find("NT:")
# 			if(posstr>=0):
# 				posend = response.find("\n",posstr)
# 				self.st = response[posstr+3:posend-1].strip()
# 		def __repr__(self):
# 			return "<ssdpObject({location}, {st}, {usn})>".format(**self.__dict__)
# 	def discover(self, service, timeout=5):

# 		multicast_group   = "239.255.255.250"
# 		multicast_port  = 1900
# 		buffer_size = 1500

# 		sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# 		sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
# 		mreq = struct.pack('=4sl', socket.inet_aton(multicast_group), socket.INADDR_ANY) # pack multicast_group correctly
# 		sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)		 # Request multicast_group

# 		sock.bind((multicast_group, multicast_port))						   # bind on all interfaces
# 		devices = {}
# 		sock.settimeout(timeout)
# 		tm_start = time.time()
# 		while (time.time()-tm_start)<=timeout:
# 			try:
# 				data, srv_sock = sock.recvfrom(buffer_size)			  # Receive data (blocking)
# 				srv_addr, srv_srcport = srv_sock[0], srv_sock[1]
# 				device = self.ssdpObject(data)
# 				if((service in data or service=="ssdp:all") and not device.location in devices):
# 					devices[device.location]=device
# 			except Exception as e:
# 				pass
# 		return devices

class c_ssdp:
	""" ssdp discovery class """
	# code adapted from https://gist.github.com/dankrause/6000248
	class SSDPResponse(object): #creates an object out of an SSDP device
		class _FakeSocket(StringIO.StringIO): #used to extract headers from the SSDP response
			def makefile(self, *args, **kw):
				return self
		def __init__(self, response):
			r = httplib.HTTPResponse(self._FakeSocket(response)) #creates a fake HTTP 'response' - to get location, usn and st easier
			r.begin()
			try:
				self.location = r.getheader("location")
				self.server = r.getheader("server")
				self.usn = r.getheader("usn")
				self.st = r.getheader("st")
				self.cache = r.getheader("cache-control").split("=")[1]
			except Exception, e:
				raise e
		def match(self,field,value, case=False):
			""" Determine whether this device has a specified string in its property

			Args:
				field (str): field/property to search.
				value (str): what to look for in the field.
				case (bool, optional): whether to perform case-sensitive search. Default: False.

			Returns:
				bool: True if this device's field contains the specified value, False otherwise.
			"""
			if(not hasattr(self,field)): #test if this class even has the property that the user is trying to search
				return False
			if(case):#case-sensitive search
				return getattr(self,field).find(value)>=0
			#case-insensitive search
			return getattr(self,field).lower().find(value.lower())>=0
		def __repr__(self):
			return "<SSDPResponse(location:{location}, st:{st}, usn:{usn}, server:{server})>".format(**self.__dict__)
	 
	def discover(self, st=False, text=False, field='server', case=False, timeout=5):
		""" Discovers any UPnP devices (using SSDP protocol).
		
		The function sends an M-SEARCH request to the UPnP multicast address/port,
		parses the response and provides a list of devices matching the search criteria.

		Args:
			st (str, optional): search target for M-SEARCH request, to find all SSDP-enabled devices, use 'ssdp:all'. Default: ssdp:all
			text (str, optional): search for the devices with this text in one of its fields. Default: False
			field (str, optional): in which property to look for 'text'. Default: 'server'
			case (bool, optional): whether to do a case-sensitive search on 'field'. Default: False
			timeout (int, optional): how long to wait for a response to the M-SEARCH request and how long search. NB: if timeout is below 3, the response may be empty.

		Returns:
			dict: a dictionary of all the devices found in the system.
			e.g.:
			{
				'192.168.1.15': <ssdp object>
			}
		"""

		# NB: if M-SEARCH fails (on routers that don't support multicast), we can implement B-SEARCH as fallback method.

		buffer_size = 1500 # how much to read from an M-SEARCH response
		multicast_ip   = "239.255.255.250"
		multicast_port  = 1900
		group = (multicast_ip, multicast_port)
		message = "\r\n".join([
			'M-SEARCH * HTTP/1.1',
			'HOST: {0}:{1}', #multicast address
			'MAN: "ssdp:discover"',
			'ST: {st}', #search target
			'MX: {timeout}', #maximum time to wait for the M-SEARCH response
			# 'USER-AGENT: pxp' #optional parameter for UPnP, compulsory for UDAP (e.g.: USER-AGENT: iOS/5.0 UDAP/2.0 iPhone/4 )
			'', #adds newline after MX
			''])#adds another newline (required for M-SEARCH request)
		socket.setdefaulttimeout(timeout)
		devices = {}
		sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
		sock.settimeout(timeout)
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
		if(not st): #user
			target = "ssdp:all"
		else:
			target = st
		sock.sendto(message.format(*group, st=target, timeout=timeout), group)
		tm_start = time.time()
		while (time.time()-tm_start)<=timeout:
			try:
				response = sock.recv(buffer_size)
				device = self.SSDPResponse(response)
				if((st or (text and device.match(field,text))) and not (device.location in devices)):
					#found a device that matches the search criteria
					devices[device.location] = device
			except Exception as e:
				pass
		return devices
	
class c_str():
	""" String class - used for printing stuff to browser"""
	def jout(self, dictionary):
		""" Outputs a dictionary as json-formatted response
			Args:
				dictionary(dictionary): what to output to browser
			Returns:
				none
		"""
		import json
		print("Content-Type: text/html\n")
		print(json.dumps(dictionary))
	def pout(self, text):
		""" Outputs a regular text to screen (with html header)
			Args:
				text(str): text to output
			Returns:
				none
		"""
		print("Content-Type: text/html\n")
		print(text)
#end string class

class c_tt(Thread):
	""" Timed thread class. The functions called from this class execute on separate threads. Take care not to have any infinite loops, otherwise the python application will never terminate.

		example usage. Given a function:											
																	
		def tst(param1,param2)										
																	
		a = TimedThread(tst,("a",5),3)								
																	
		this will call tst("a",5) every 3 seconds
	"""
	def __init__(self,callback,params=(),period=0, autostart=True):
		""" Constructor
			Args:
				callback(function): to be called when the timeout expires
				params(tuple,optional): parameters to the callback function. default: ()
				period(int,optional): how often to call the callback function. if period is zero, the function will only execute once. default: 0
				autostart(bool,optional): whether to start the function automatically. default: True
			Returns:
				none
		"""
		super(TimedThread, self).__init__()
		self.running = True
		self.timeout = period #how often to run a specified function
		self.sleeptime = min(1,period/2) #how much to sleep while waiting to run the next time - sleep for 1 second at most or half of the desired period (if sub-second)
		self.callback = callback
		self.args = params
		if(autostart):
			self.start()
	def stop(self):
		""" Set the .running property as false
			Args:
				none
			Returns:
				none
		"""
		self.running = False
 
	def run(self):
		""" Start the thread
			Args:
				none
			Returns:
				none
		"""
		tm_start = time.time()
		try: #run the function immediately
			if(type(self.args) is tuple):
				self.callback(*self.args) #more than 1 parameter passed (as a tuple)
			else:
				self.callback(self.args) #single parameter is passed, not a tuple - do not pass by reference
		except:
			pass
		if(self.timeout<=0):
			return
		while (self.running):
			try:
				if(time.time()-tm_start<self.timeout):
					time.sleep(self.sleeptime) #this will reduce the load on the processor
					continue
				tm_start = time.time()
			except KeyboardInterrupt:
				print "keybd stop"
				self.running = False
				break
			try:
				if(type(self.args) is tuple):
					self.callback(*self.args)
				else:
					self.callback(self.args)
			except KeyboardInterrupt:
				print "keybd stop"
				self.running = False
				break
			except Exception as e:
				print "ERROR:",e
				print "THREAD:",self.callback.__name__
				pass
		#end while
	#end run
	def kill(self):
		""" Stop the thread
			Args:
				none
			Returns:
				none
		"""
		try:
			self.running = False
			self.stop()
			self.join()
		except:
			pass
#end timed thread class


class c_uri:
	"""url utilities class"""
	uriString = ""
	host = ""
	uriList = []
	uriQuery = ""
	def __init__(self):
		import os
		# get uri string without the script name
		if "PATH_INFO" in os.environ:
			self.uriString = os.environ['PATH_INFO']
		else:
			self.uriString = ""
		self.uriList = self.uriString.split('/')
		if (not 'SCRIPT_NAME' in os.environ):
			os.environ['SCRIPT_NAME'] = ""
		self.uriList[0]=os.path.basename(os.environ['SCRIPT_NAME'])
		self.uriList = filter(None,self.uriList)
		if ('HTTP_HOST' in os.environ):
			self.host = os.environ['HTTP_HOST']
		if "QUERY_STRING" in os.environ:
			self.uriQuery = os.environ["QUERY_STRING"]
	#end __init__
	def numsegs(self):
		""" returns total number of segments minus the script name """
		return len(self.uriList)-1
	#end numsegs	
	def segarr(self):
		""" returns array of segments """
		return self.uriList[1:]
	def segment(self,segnum,ifempty=False):
		""" returns a specified segment from the script URI (segment 0 is the script name) 
			Args:
				segnum(int): segment index to retreive (e.g. from http://localhost/min/seg/num, segment #1 will be 'seg')
				ifempty(mixed,optional): this value will be returned if specified segment does not exist. default: False
			Return:
				mixed: will return string containing the value from the requested segment or ifempty value if the segment doesn't exist
		"""
		if len(self.uriList)<(segnum+1):
			#element doesn't exist, return the ifempty string (if it was specified)
			return ifempty
		return self.uriList[segnum]
	#end segment
	def query(self):
		""" Returns query string 
			Args:
				none
			Returns:
				(mixed): returns the query string if one is present, False otherwise
		"""
		if len(self.uriQuery)>0:
			return self.uriQuery
		return False
	#end query
#end uri class

class c_bonjour:
	""" bonjour service class """
	def discover(self, regtype, callback):
		""" Discover a device
			Args:
				regtype(str): bonjour protocol registration type
				callback(function): method to call when discovery is complete
			Returns:
				none
		"""
		# list of devices that are queried on the network, in case there are other matches besides the specified one (internal only)
		queried  = []
		# don't bother if a device is unreachable
		timeout  = 5
		# list of devices for which was able to get the info (internal only)
		resolved = []	

		# gets called when device is resolved
		def resolve_callback(sdRef, flags, interfaceIndex, errorCode, fullname, hosttarget, port, txtRecord):
			def query_record_callback(sdRef, flags, interfaceIndex, errorCode, fullname, rrtype, rrclass, rdata, ttl):
				if errorCode == pybonjour.kDNSServiceErr_NoError:
					ipAddr = socket.inet_ntoa(rdata)
					queried.append(True)
					#return the results to the caller
					results = {
						'ip':ipAddr,
						'txtRecord':txtRecord,
						'port':port
					}
					callback(results)
			#end query_record_callback

			if errorCode != pybonjour.kDNSServiceErr_NoError:
				return
			query_sdRef = pybonjour.DNSServiceQueryRecord(interfaceIndex = interfaceIndex,  fullname = hosttarget, rrtype = pybonjour.kDNSServiceType_A, callBack = query_record_callback)
			try:
				while not queried:
					ready = select.select([query_sdRef], [], [], timeout)
					if query_sdRef not in ready[0]:
						break
					pybonjour.DNSServiceProcessResult(query_sdRef)
				else:
					queried.pop()
				query_sdRef.close()
			except Exception as e:
				print "[---]bonjour.publish.query_callback:",e, sys.exc_traceback.tb_lineno
			resolved.append(True)
		#end resolve_callback

		def browse_callback(sdRef, flags, interfaceIndex, errorCode, serviceName, regtype, replyDomain):
			if (errorCode != pybonjour.kDNSServiceErr_NoError) or not (flags & pybonjour.kDNSServiceFlagsAdd): 
				# error or the service was removed
				return
			try:
				resolve_sdRef = pybonjour.DNSServiceResolve(0, interfaceIndex, serviceName, regtype, replyDomain, resolve_callback)
				while not resolved:
					ready = select.select([resolve_sdRef], [], [], timeout)
					if resolve_sdRef not in ready[0]:
						break
					pybonjour.DNSServiceProcessResult(resolve_sdRef)
				else:
					resolved.pop()
				resolve_sdRef.close()
			except Exception as e:
				print "[---]bonjour.publish.browse_callback:",e, sys.exc_traceback.tb_lineno
		#end browse_callback

		try:
			browse_sdRef = pybonjour.DNSServiceBrowse(regtype = regtype, callBack = browse_callback)
			start_time = time.time()
			now = start_time
			while ((now-start_time)<2):#look for encoders for 3 seconds, then exit
				ready = select.select([browse_sdRef], [], [], 0.1)
				if browse_sdRef in ready[0]:
					pybonjour.DNSServiceProcessResult(browse_sdRef)
				now = time.time()
		except Exception as e:
			print "[---]bonjour.discover",e
		finally:
			browse_sdRef.close()
	#end discover
	def parseRecord(self,txtRecord):
		""" Parses txtRecord in VAR=VALUE format into a dictionary
			Args:
				txtRecord(str): record in VAR=VALUE format
			Returns:
				(dictionary)
		"""
		if(not txtRecord):
			return {}
		length = len(txtRecord)
		parts = []
		line = ""
		# split the txtRecord into lines
		for i in xrange(length):
			if(ord(txtRecord[i])<27):
				# line ended
				parts.append(line)
				line = ""
			else:
				line += txtRecord[i]
		if(len(line)>0):
			parts.append(line)
		records = {}
		for line in parts:
			linepart = line.split('=')
			if(len(linepart)>1):
				records[str(linepart[0])] = str(linepart[1])
		return records
	#end extractStream
	def publish(self, regtype, name, port, txtRecord=""):
		""" Publish the local device on bonjour
			Args:
				regtype(str): bonjour registration type
				name(str): what to name the local computer on the bonjour service list
				port(str): port that will be identified when this computer is discovered on the network
				txtRecord(str,optional): additional text record to send along with registration
			Returns:
				none
		"""
		try:
			# gets called when bonjour registration is complete
			def register_callback(sdRef, flags, errorCode, name, regtype, domain):
				pass
			#end register_callback
			try:
				# register the pxp service
				sdRef = pybonjour.DNSServiceRegister(name = name,
													 regtype = regtype,
													 port = port,
													 callBack = register_callback,
													 txtRecord = txtRecord) #can put extra info in txtRecord
				start_time = time.time()
				while ((time.time()-start_time)<5):#try to publish for 5 seconds, then exit
					ready = select.select([sdRef], [], [],2)
					if sdRef in ready[0]:
						pybonjour.DNSServiceProcessResult(sdRef)
			except Exception as e:
				print "[---]bonjour.publish",e, sys.exc_traceback.tb_lineno
				pass
			finally:
				sdRef.close()
		except Exception as e:
			print "[---]bonjour.publish",e
			pass
#end bonjour class

osi = c_osi()
db = c_sqdb
disk = c_disk()
enc = c_enc()
io = c_io()
session = c_session()
ssdp = c_ssdp()
sstr = c_str()
TimedThread = c_tt
uri = c_uri()
bonjour = c_bonjour()