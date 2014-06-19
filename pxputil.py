import constants as c
import os
from threading import Thread
import time
import sqlite3
import urllib, urllib2
import sha, shelve, time, Cookie, os, sys
import socket
import struct
import httplib
import StringIO

#sqlite database management class
class c_sqdb:
	con = None
	c   = None
	autocommit = True
	def __init__(self, dbpath=False):
		if dbpath:
			self.open(dbpath)
	def close(self):
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
		self.autocommit = True
		if self.con:
			self.con.commit()
	#end commit()
   
	#returns all rows of a query as a dictionary (associative array)
	def getasc(self):
		try:
			if not self.c:
				return []
			rows = []
			#get column names
			cols = []
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
   
	#returns one row from the query
	def getrow(self):
		if self.c:
			return self.c.fetchone()
		return ()
	#end getrow()
   
	#returns all the query rows as an array
	def getrows(self):
		if self.c:
			return self.c.fetchall()
		return []
	#end getrows()
   
	#returns ID of the last inserted entry
	def lastID(self):
		if self.c:
			return self.c.lastrowid
		return False
	#end lastID()

	#returns number of rows
	def numrows(self):
		if self.c:
			return self.c.rowcount
		return 0
	#end numrows()
   
	#creates connection to the database
	def open(self, dbpath):
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
	
	#executes an sql query
	def query(self, sql, data, autocommit=True):
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
   	#executes a query string
	def qstr(self, query, multiple=False):
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
		try:
			self.autocommit = True
			if self.con:
				self.con.rollback()
		except:
			pass
	#end commit()
	#begin transaction - user must commit or rollback manually
	def transBegin(self):
		self.autocommit = False
	#end transBegin
#end c_sqdb
	#disk operations class

#disk utilities class
class c_disk:
	def cfgGet(self, cfgfile=c.pxpConfigFile, section=False, parameter=False):
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
						return {}
				else:#parameter was not specified, return entire section
					return settings[section]
			else: #specified section does not exist
				return {}
		else: #section was not specified
			return settings #return all the settings
	#end cfgGet
	#assigns a config file (either entire thing or a section, based on input)
	def cfgSet(self, cfgfile=c.pxpConfigFile, section=False, parameter=False, value=False, jsonData=False):
		import json
		try: #load all the settings (to make sure nothing gets overwritten)
			settings = json.loads(self.file_get_contents(cfgfile))
		except:
			#could not load settings - probably error with the file or file doesn't exist
			settings = {}
		if(jsonData): #all of the settings are specified here - just overwrit the file WATCH OUT!!!!!
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
		import shutil
		shutil.copy(src,dst)
	#retrieves file contents as a string
	def file_get_contents(self, filename):
		import os
		if(not os.path.exists(filename)):
			return False
		contents = ""
		with open(filename,"rb") as f:
			contents = f.read()
		return contents
	def file_set_contents(self, filename,text):
		f = open(filename,"w")
		f.write(text)
		f.close()	
	def mkdir(self, dirpath, perm=0777):
		import os
		try:
			os.makedirs(dirpath,perm)
			return True
		except Exception as e:
			return False
	#end mkdir
	#returns true if there is a specified process running
	def psOn(self, process):
		import platform, os
		if (platform.system()=="Windows"):
			#get all the processes for windows matching the specified one:
			cmd = "tasklist | findstr /I "+process
		else:
			#system can be Linux, Darwin
			#get all the processess matching the specified one:
			cmd = "ps -ef | grep \""+process+"\" | grep -v grep > /dev/null" #"ps -A | pgrep "+process+" > /dev/null"
		#result of the cmd is 0 if it was successful (i.e. the process exists)
		return os.system(cmd)==0
	#end psOn
	# reads sizeToRead from a specified udp port
	def sockRead(self, udpAddr="127.0.0.1", udpPort=2224, timeout=0.5, sizeToRead=1):
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
	# sends msg to the specified socket
	def sockSend(self, msg, sockHost="127.0.0.1", sockPort=2232,addnewline=True):
		import socket
		sent = 0
		try:
			sock = socket.socket(
				socket.AF_INET, socket.SOCK_STREAM)
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
#end c_disk class

#encryption/string operations class
class c_enc:
	#return sha1 hash of the string
	def sha(self,string):
		import hashlib
		s = hashlib.sha1(string)
		return s.hexdigest()
	#repeats the string up to 'length' characters
	def repeat_str(self, string_to_expand, length):
	   return (string_to_expand * ((length/len(string_to_expand))+1))[:length]
	# performs bitwise exclusive or on 2 strings 
	# must be of equal length, otherwise result will be trimmed to the shortest string
	def sxor(self, s1,s2):
		# convert strings to a list of character pair tuples
		# go through each tuple, converting them to ASCII code (ord)
		# perform exclusive or on the ASCII code
		# then convert the result back to ASCII (chr)
		# merge the resulting array of characters as a string
		return ''.join(chr(c) for c in [ord(a) ^ ord(b) for a,b in zip(s1,s2)])
	#end sxor
#end enc class

class c_osi:
	"""os info class"""
	name = None
	SN = ""
	def __init__(self):
		try:
			import sys, subprocess
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
					#     |   "IOPlatformSerialNumber" = "C07JKA31DWYL"
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
				     #     'dmidecode -s system-serial-number' instead of '... system-uuid'
					proc = subprocess.Popen('dmidecode -s system-uuid',shell=True,stdout=subprocess.PIPE)
					serialNum = ""
					for line in iter(proc.stdout.readline,""):
						serialNum = line
				except Exception as e:
					serialNum = "n/a"
			self.SN = serialNum.strip()
		except Exception as e:
			print "osi init error: ", e, sys.exc_traceback.tb_lineno
#web input/output class
class c_io:
	frm = None
	def __init__(self):
		# import cgitb; cgitb.enable()
		if (osi.name=='linux'):
			pass #on linux using flask field storage is managed externally
		elif (osi.name == 'mac'):
			import cgi
			if not self.frm:
				self.frm = cgi.FieldStorage()
	def get(self, fieldName):
		try:
			if(osi.name=='linux'):
				return self.frm[fieldName]
			elif(osi.name=='mac'):
				return self.frm.getvalue(fieldName)
		except:
			return False
	#end get
	def myIP(self):
		try:
			import sys, netifaces as ni
			ipaddr = "127.0.0.1"
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
								return ipaddr
		except Exception as e:
			print "error in myIP: ", e, sys.exc_traceback.tb_lineno
		return ipaddr
	
	def sameSubnet(self, ip1,ip2):
		"""returns true if both ip addresses belong to the same subnet"""
		try:
			return ".".join(ip1.split('.')[:3])==".".join(ip2.split('.')[:3])
		except:
			return False
	#end sameSubnet
	# creates a url call (i.e. a 'get' request)
	def url(self,url,params=False,timeout=60):
		try:
			if(params):
				data = urllib.urlencode(params)
				req = urllib2.Request(url,data)
			else:
				req = urllib2.Request(url)
			answer = urllib2.urlopen(req,timeout=timeout)
			respText = answer.read()
			if(not respText):
				return True
			return respText
		except Exception as e:
			return False
	# checks if there is connection to myplayxplay.net website
	def isweb(self):
		import urllib2
		from time import time as tm				
		try:
			timestamp = str(int(tm()*1000))
			response=urllib2.urlopen('http://myplayxplay.net/?timestamp='+timestamp,timeout=10)
			return True
		except Exception as e: pass
		return False
	def send(self,url,params,jsn=False):
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
	def urlexists(self,urlpath):
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

#session management class
class c_session(object):
	def close(self):
		self.data.close()
	def destroy(self):
		try:
			self.data.close()
		except:
			pass
		try:
			self.data = None
		except:
			pass
	#end close
	# by default session expires in 1 day
	def start(self, expires=24*60*60, cookie_path="/"):
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
		if expires == '':
			self.data['cookie']['expires'] = ''
		elif isinstance(expires, int):
			self.data['cookie']['expires'] = expires
		self.cookie['sid']['expires'] = self.data['cookie']['expires']
	#end set_expires
#end session class

class c_ssdp:
	class ssdpObject(object):
		def __init__(self, response):
			self.location 	= ""
			self.usn 		= ""
			self.st 		= ""
			# get LOCATION
			posstr = response.find("LOCATION:")
			if(posstr>=0):
				posend = response.find("\n",posstr)
				self.location = response[posstr+10:posend-1].strip()
			# get USN
			posstr = response.find("USN:")
			if(posstr>=0):
				posend = response.find("\n",posstr)
				self.usn = response[posstr+4:posend-1].strip()
			# get NT
			posstr = response.find("NT:")
			if(posstr>=0):
				posend = response.find("\n",posstr)
				self.st = response[posstr+3:posend-1].strip()
		def __repr__(self):
			return "<ssdpObject({location}, {st}, {usn})>".format(**self.__dict__)
	def discover(self, service, timeout=5):

		multicast_group   = "239.255.255.250"
		multicast_port  = 1900
		buffer_size = 1500

		sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		mreq = struct.pack('=4sl', socket.inet_aton(multicast_group), socket.INADDR_ANY) # pack multicast_group correctly
		sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)         # Request multicast_group

		sock.bind((multicast_group, multicast_port))                           # bind on all interfaces
		devices = {}
		sock.settimeout(timeout)
		tm_start = time.time()
		while (time.time()-tm_start)<=timeout:
			try:
				data, srv_sock = sock.recvfrom(buffer_size)              # Receive data (blocking)
				srv_addr, srv_srcport = srv_sock[0], srv_sock[1]
				device = self.ssdpObject(data)
				if((service in data or service=="ssdp:all") and not device.location in devices):
					devices[device.location]=device
			except Exception as e:
				pass
		return devices
 
#string class
class c_str():
	#outputs a dictionary as json-formatted response
	def jout(self, dictionary):
		import json
		print("Content-Type: text/html\n")
		print(json.dumps(dictionary))
	#outputs a regular text to screen (with html header)
	def pout(self, text):
		print("Content-Type: text/html\n")
		print(text)
#end string class


##################################################################
#                       timed thread class                       #
#                                                                #
#  parameters:                                                   #
#    callback - function to be called when the timeout expires   #
#    params - parameters to the callback function                #
#    period - how often to call the callback function            #
#             if period is zero, the function will only          #
#             execute once                                       #
#                                                                #
#                                                                #
#  example usage:                                                #
#  given a function:                                             #
#                                                                #
#  def tst(param1,param2)                                        #
#                                                                #
#  a = TimedThread(tst,("a",5),3)                                #
#                                                                #
#  this will call tst("a",5) every 3 seconds                     #
#                                                                #
##################################################################
# timed thread class. 
class c_tt(Thread):
	def __init__(self,callback,params=(),period=0, autostart=True):
		super(TimedThread, self).__init__()
		self.running = True
		self.timeout = period #how often to run a specified function
		self.sleeptime = min(1,period/2) #how much to sleep while waiting to run the next time - sleep for 1 second at most or half of the desired period (if sub-second)
		self.callback = callback
		self.args = params
		if(autostart):
			self.start()
	def stop(self):
		self.running = False
 
	def run(self):
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
		self.stop()
		self.join()



#url utilities class
class c_uri:
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
		""" returns a specified segment (segment 0 is the script name) """
		if len(self.uriList)<(segnum+1):
			#element doesn't exist, return the ifempty string (if it was specified)
			return ifempty
		return self.uriList[segnum]
	#end segment
	#returns query string (if one is present, false otherwise)
	def query(self):
		if len(self.uriQuery)>0:
			return self.uriQuery
		return False
	#end query
#end uri class

osi = c_osi() #os info
db = c_sqdb
disk = c_disk()
enc = c_enc()
io = c_io()
session = c_session()
ssdp = c_ssdp()
sstr = c_str()
TimedThread = c_tt
uri = c_uri()
