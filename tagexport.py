#!/usr/bin/python

#export all tags with a specified name from all events
#import pxp, 
import os
#, pxputil as pu
import sys
import datetime

import sys, subprocess
import constants as c
import sqlite3
import psutil
import urllib, urllib2
import base64
import sha, shelve, time, Cookie
import socket
import struct
import httplib
import StringIO
import select
import psutil
import json

OLD_VER = False

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
            proclist = list(psutil.process_iter())
            for proc in proclist:
                try:#try to get pgid of the process
                    foundpgid = os.getpgid(proc.pid)
                except:
                    continue #skip processes that do not exist/zombie/invalid/etc.
                if(pgid==foundpgid):#this process belongs to the same group
                    try: #can use the same function recursively to get cpu usage of a single process, but creates too much overhead
                        ps = psutil.Process(proc.pid)
                        totalcpu += ps.cpu_percent(interval=1)
                    except:
                        continue
                #if pgid==foundpgid
            #for proc in proclist
        elif(pid):#looking for cpu usage of one process by pid
            try:
                ps = psutil.Process(pid)
                totalcpu = ps.cpu_percent(interval=1)
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
                    #     # grab full drive name (including any space it might have)
                    #     i = 2
                    #     driveName = ""
                    #     while (i<len(driveParts) and driveParts[i][0]!='('):
                    #         driveName += driveParts[i]+' '
                    #         i +=1
                    #     if(driveName != ""):
                    #         drives.append(driveName.strip())
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
            procs = list(psutil.process_iter())
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
        if (osi.name=='windows'):    #system can be Linux, Darwin
            #get all the processes for windows matching the specified one:
            cmd = "tasklist | findstr /I "+process
            #result of the cmd is 0 if it was successful (i.e. the process exists)
            return os.system(cmd)==0
        procs = list(psutil.process_iter())        
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
        #         hq: "http://pxp5.local/events/2015-01-29_12-04-45_5bb91fe9a9423a9fb242cf82ee62b3849cfffa7b_local/video/main_02hq.mp4"
        #     },
        # s_00: {
        #         hq: "http://pxp5.local/events/2015-01-29_12-04-45_5bb91fe9a9423a9fb242cf82ee62b3849cfffa7b_local/video/main_00hq.mp4"
        #     },
        # s_01: {
        #         hq: "http://pxp5.local/events/2015-01-29_12-04-45_5bb91fe9a9423a9fb242cf82ee62b3849cfffa7b_local/video/main_01hq.mp4"
        #    }
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

osi = c_osi()
sqdb = c_sqdb
disk = c_disk()

def clipTag(evtPath, mp4video_filename, tag, outName):
    tmStart = str(int(tag['starttime']))
    duration= str(int(tag['duration']))
    outFile = outName+'_'+(tag['name'].replace(' ','_'))+'.mp4'

    if(os.path.exists(evtPath + "/" + main_video)):
        # extract from mp4 file
        cmd = "ffmpeg -y -ss " + tmStart + " -i " + evtPath + "/" + mp4video_filename + " -t " + duration + " -codec copy " + outFile
        pass

    print ".............."
    print cmd
    print tag['name'], tmStart, duration, '...'
    os.system(cmd)
    if(not os.path.exists(outFile)):
        # could not create file from the full mp4 game, try to extract it from the segments
        pass
    print ".............."

args = False
if (len(sys.argv) == 4 ):
    args = sys.argv
    print args
else:
    print "usage example) ./tagexport.py <mp4 video filename> <m3u8 playlist name> <tag name>"
    print "WARNING: This command will delete all of mp4 files in /users/dev/Desktop/clips"
    quit()

st = datetime.datetime.now()
print "starting...", st.strftime('%Y-%m-%d %H:%M:%S')

# Change following lines to adjust for the old/new encoder box
if (args != False):
    main_video = args[1]
    playlist = args[2]
    tagname = args[3]
    if(os.path.exists("/users/dev/Desktop/clips")):
        os.system("rm -f /users/dev/Desktop/clips/*.mp4")
else:
	if (OLD_VER):
	    main_video = "main.mp4"
	    playlist = "list.m3u8"
	    tagname = "pp" # goal
	else:
	    main_video = "main_00hq.mp4"
	    playlist = "list_00hq.m3u8"
	    tagname = "pp" # goal		



eventFolders = os.listdir("/private/var/www/html/events") #evtDir = "/Users/dev/Documents/test.events/"  #"/users/dev/Desktop/sacPXPfield.events/"
for evtDir in eventFolders:
    print evtDir
    if (evtDir.find('_local') > 0):
        dirs = os.listdir("/private/var/www/html/events/" + evtDir)
        tagNum = 1
        outPath = "/users/dev/Desktop/clips"
        if(not os.path.exists(outPath)):
            disk.mkdir(outPath)
        
        if(not (os.path.exists("/private/var/www/html/events/" + evtDir+"/pxp.db"))):
            print "db not found"    
            quit
            
        db = sqdb("/private/var/www/html/events/" + evtDir + "/pxp.db")
        if(not db):
            print "error in opening db"
            quit
            
        for evt in dirs:
            evtPath = "/private/var/www/html/events/" + evtDir + "/" + evt
            if(not ((os.path.exists(evtPath + "/" + main_video) or os.path.exists(evtPath + "/" + playlist)))):
                continue #skip non-event folders
            print evtPath
        
            # print evtPath
            # get all tags, matching the specified one
            sql = "SELECT * FROM `tags` WHERE `name` LIKE ?"
            db.query(sql,("%"+tagname,)) # % are wild cards to make sure and grab all tags containing that word
            tags = db.getasc()
            for tag in tags:
                print "tag-->", tag
                # extract clip from this tag and save it
                tgn = tagname.replace(' ', '_')
                clipTag(evtPath, main_video, tag, outPath+"/"+evtDir+"_"+tgn+str(tagNum).zfill(4))
                tagNum+=1

st = datetime.datetime.now()
print "Export Finished", st.strftime('%Y-%m-%d %H:%M:%S')
