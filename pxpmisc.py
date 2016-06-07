from __future__ import division, print_function, absolute_import, unicode_literals
from datetime import datetime as dt
from uuid import getnode as getmac
from pxputil import TimedThread
from urlparse import parse_qsl
from itertools import izip_longest
import camera, constants as c, copy, json, os, psutil, pxp, pxputil as pu, signal, socket, subprocess as sb, time
import glob, sys, os, shutil, hashlib, re
import itertools
import pprint as pp
import threading
import time
from pip.utils.filesystem import check_path_owner


tmr_misc = {}

# This class helps to rebuild whole mp4 file from the TS files

class MP4FixWorker (threading.Thread):
    def __init__(self, threadId, event_path, camid, vq):
        threading.Thread.__init__(self)
        self.threadId = threadId
        self.event_path = event_path
        self.camid = camid
        self.vq = vq
        self.thread_name = "worker-{}-{}-{}-{}".format(self.threadId, event_path, camid, vq)
        self.ret_status = False
        self.progress = 0
    
    def log(self, *arguments, **keywords):
        try:
            logFile = "/tmp/fix-" + self.getname() + ".txt"
            #logFile = c.wwwroot + self.event_path + "/video/" + self.getname() + ".txt"
            #logFile = c.wwwroot + "/_db" + self.getname() + ".txt"
            with open(logFile,"a") as fp:
                fp.write(dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"))
                fp.write(' '+' '.join(map(str, (arguments))))
                fp.write("\n")
        except Exception as e:
            pass
    
    def getname(self):
        return "{}-{}-{}".format(self.event_path, self.camid, self.vq)
    
    def doFixNow(self):
        self.log("starting {}  time:{}".format(self.thread_name, time.ctime(time.time())))
        self.rebuild_mp4()
        self.log("finishes {}  time:{}".format(self.thread_name, time.ctime(time.time())))
    
    def run(self):
        self.doFixNow()

    def rebuild_mp4(self):
        self.ret_status = False
        try:
            results = {}
            self.progress = 0
            
            videoPath = c.wwwroot + self.event_path + "/video/"
            check_path = c.wwwroot + self.event_path + "/video/" + self.vq + "_" + self.camid + "/list_" + self.camid + self.vq + ".m3u8"
            if (os.path.exists(check_path)):
                videoPath = c.wwwroot + self.event_path + "/video/" + self.vq + "_" + self.camid + "/"

            results = self.getseginfo(self.camid, self.vq, self.event_path)
            if (results == False):
                self.progress = 5 # at least it has been tried...
                return self.ret_status
            if (results['last_idx']):
                self.concat_ts(results['last_idx'], self.camid, self.vq, self.event_path)
                self.convert_ts2mp4(videoPath, self.camid, self.vq)
            time.sleep(3)
            progress_step = (100 - self.progress) / 3 
            cmd1 = 'mv ' + videoPath + "main_{}{}.mp4".format(self.camid, self.vq) + " " + videoPath + "main_org_{}{}.mp4".format(self.camid, self.vq)
            cmd2 = 'mv ' + videoPath + "all_{}{}.mp4".format(self.camid, self.vq) + " " + videoPath + "main_{}{}.mp4".format(self.camid, self.vq)
            cmd3 = 'rm ' + videoPath + "all_{}{}.ts".format(self.camid, self.vq)
            self.log("rebuild_mp4 postproc1: {}".format(cmd1))
            os.system(cmd1)
            self.progress += progress_step
            self.log("rebuild_mp4 postproc2: {}".format(cmd2))
            os.system(cmd2)
            self.progress += progress_step
            self.log("rebuild_mp4 postproc3: {}".format(cmd3))
            os.system(cmd3)
            self.progress += progress_step
            self.log("rebuild mp4 DONE!!! ----> {}".format(self.name))
            self.ret_status = True
            self.progress = 100
        except Exception as e:
            self.log("[---] rebuild_mp4 {}".format(e))
        return self.ret_status

    def getseginfo(self, camid="00", vq="hq", event='live'):
        try:
            if (pu.pxpconfig.check_webdbg('param')):            
                self.log("--> getseginfo: cam:{} vq:{} event:{}".format(camid, vq, event))
            import math
            results = {}
            results['camid'] = camid
            results['vq'] = vq
            results['first_seg'] = False
            results['last_seg'] = False
            results['first_idx'] = False
            results['last_idx'] = False
            results['duration'] = 0.0
            
            videoPath = c.wwwroot + event + '/video/'
            listPath = c.wwwroot + event + "/video/list_" + camid + vq + ".m3u8"

            check_path = c.wwwroot + event + "/video/" + vq + "_" + camid + "/list_" + camid + vq + ".m3u8"
            if (os.path.exists(check_path)):
                listPath = check_path
                videoPath = c.wwwroot + event + '/video/' + vq + "_" + camid + "/"
            
            reachedTime = 0.0
            try:
                f = open(listPath, "r")
            except Exception as e:
                self.log("[---] error getseginfo: {}  path:{}".format(e, listPath))
                return False
            
            lastSegTime = 0
            for line in f:
                cleanStr = line.strip()
                if(cleanStr[:7]=='#EXTINF'): # this line contains time information
                    lastSegTime = float(cleanStr[8:-1]) # get the number (without the trailing comma) - this is the duration of this segment file
                    reachedTime += lastSegTime
                elif(cleanStr[-3:]=='.ts'):  # this line contains filename
                    if (not results['first_seg']): #only assign the first segment once
                        results['first_seg']=cleanStr
                    results['last_seg']=cleanStr
            f.close()
            self.progress += 5 # 5% usage for this procedure
            results['duration']=reachedTime
                        
            if (results['first_seg']):
                if (os.path.exists(videoPath+results['first_seg'])):
                    results['first_idx'] = int(results['first_seg'].split('.')[0].split('_')[2]) # get first index
            if (results['last_seg']):
                if (os.path.exists(videoPath+results['last_seg'])):
                    results['last_idx'] = int(results['last_seg'].split('.')[0].split('_')[2])  # get last index
            return results
        except Exception as e:
            msgstr=str(sys.exc_info()[-1].tb_lineno)+' '+str(e)
            self.log("[---] error getseginfo: {}  path:{}".format(msgstr, videoPath))
            return False

    def convert_ts2mp4(self, event_path, camid, vq):
        import subprocess
        tsfilename = event_path + "all_" + camid + vq + ".ts"
        (tsfilebase, fext) = os.path.splitext(tsfilename)
        mp4_path = "{}{}".format(tsfilebase, ".mp4")
        if (os.path.exists(mp4_path)):
            os.system("rm " + mp4_path)
        try:
            self.log("convert file from:{}  to:{}".format(tsfilename, mp4_path))
            hbrake_param = " -i {} -o {} --preset=\"Android Tablet\"".format(tsfilename, mp4_path)
            if (pu.pxpconfig.hbrake_conf()):
                hbrake_param = pu.pxpconfig.hbrake_conf()
            hbcmd = c.handbrake + " " + hbrake_param.format(tsfilename, mp4_path)
            self.log('hb_cmd---->'+hbcmd)
            
            #hbcmd = c.handbrake + " -i {} -o {} --preset=\"Android Tablet\"".format(tsfilename, mp4_path)
            #subprocess.check_call(hbcmd, shell=True)
            
            hb_cmd = hbcmd.split(' ')
            hbproc = subprocess.Popen(hb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            cur_progress = self.progress
            
            # this parsing line should be changed if the HB version is upgraded or changed...
            # for now, it looks for such as following lines: Encoding: task 1 of 1, 100.00 % (521.78 fps, avg 533.34 fps, ETA 00h00m00s)
            #
            percent_templ = re.compile("([A-z0-9: ]*[,]+)([ ]+)([.0-9][0-9. ]+[%]+)", re.I)
            line = ''
            while hbproc.poll() is None:
                out = hbproc.stdout.read(1)
                #sys.stdout.write(out)
                line += out
                if (out == '\r'):
                    if (line.find('%')>0):
                        percent = percent_templ.match(line)
                        if (percent != None):
                            if (isinstance(percent.group(3), basestring)):
                                self.progress = cur_progress + int(float(percent.group(3).split(' ')[0])/100.0*75.0) # 75% usage for this procedure
                        self.log('out:'+line+ '---->' + str(self.progress))
                    line = ''
                sys.stdout.flush()            

#             hb_cmd = hbcmd.split(' ')
#             hbproc = subprocess.Popen(hb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#             while hbproc.poll() is None:
#                 line = hbproc.stdout.readline()
#                 for o in line.split('\r'):
#                     if (o.find('%')>0):
#                         self.log('out:'+o)
            
#             hb_cmd = hbcmd.split(' ')
#             hbproc = subprocess.Popen(hb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#             out,err = hbproc.communicate()
#             for o in out.split('\r'):
#                 if (o.find('%')>0):
#                     self.log('out:'+o)
            
        except subprocess.CalledProcessError:
            self.log("CalledProcessError!!, next file")
            pass
        except OSError:
            self.log("OSError!!, next file")
            pass            
        except Exception as e:
            self.log('[---] convert_ts2mp4:' + e)
            pass            

    def concat_ts(self, last_idx, camid="00", vq="hq", event='live'):
        self.log("concatenating ts files started...last index:{}".format(last_idx))
        try:
            videoPath = c.wwwroot + event + "/video/"
            check_path = videoPath + vq + "_" + camid + "/list_" + camid + vq + ".m3u8"
            if (os.path.exists(check_path)):
                videoPath = c.wwwroot + event + "/video/" + vq + "_" + camid + "/"
            
            all_ts = videoPath + "all_" + camid + vq + ".ts"
            if (os.path.exists(all_ts)):
                os.system("rm " + all_ts)
                
            progress_step = int(15.0/float(last_idx)) # 15% usage for this procedure   
            for i in xrange(last_idx):
                segn = videoPath + camid + vq + "_segm_" + str(i) + ".ts"
                cmd = "cat " + segn + " >> " + all_ts
                self.log("count:{}   cmd:{}".format(i, segn))
                os.system(cmd)
                self.progress += int(progress_step)
        except Exception as e:
            msgstr=str(sys.exc_info()[-1].tb_lineno)+' '+str(e)
            self.log("[---] concat_ts:{}    path:{}".format(msgstr, all_ts))
        self.log("concatenating ts files ends...path:{}  file size:{} MB".format(all_ts, os.path.getsize(all_ts)/1e6))

    def rebuild_status(self):
        return self.ret_status

class MP4Rebuilder(object):
    def __init__(self):
        super(MP4Rebuilder, self).__init__()
        self.worker = {}
        self.threadIndex = 1
        self.inhibit = False
        self.canDeleteCount = 0 # allow 5 more time to status check to show "ok-mark" in html
        
    def __del__(self):
        pass
    
    def cleanup(self):
        if ('mp4fix_status' in tmr_misc):
            tmr_misc['mp4fix_status'].kill()
            del tmr_misc['mp4fix_status']
    
    def add(self, event, camid, vq):
        must_add = False
        try:
            if (self.inhibit):
                pu.mdbg.log("MP4Rebuilder-->Cannot continue MP4 rebuild because it is inhibited")
                return False
            if (event=='live'):
                pu.mdbg.log("MP4Rebuilder-->Cannot continue MP4 rebuild due to live mode")
                return False
            if (not self.can_run()):
                pu.mdbg.log("MP4Rebuilder-->Cannot continue because too many instances are already running")
                return False
            if (not 'mp4fix_status' in tmr_misc):
                tmr_misc['mp4fix_status'] = TimedThread(self.check_status, period=10)
            if (self.init_ifcan()):
                self.init()
                
            buildkey = "{}-{}-{}".format(event, camid, vq)
            
            if (buildkey in self.worker and 'status' in self.worker[buildkey]):
                if (self.worker[buildkey]['status']=='started'):
                    pu.mdbg.log("MP4Rebuilder-->{} is already started".format(buildkey))
                    return False
                elif (self.worker[buildkey]['status']=='progress'):
                    pu.mdbg.log("MP4Rebuilder-->{} is in progress".format(buildkey))
                    return False
                elif (self.worker[buildkey]['status']=='added'):
                    pu.mdbg.log("MP4Rebuilder-->{} is added already".format(buildkey))
                    return False
                elif (self.worker[buildkey]['status']=='done'):
                    pu.mdbg.log("MP4Rebuilder-->{} is reported to be done".format(buildkey))
                    must_add = True
                    self.worker[buildkey]['status'] = "added"
                    self.worker[buildkey]['thread'] = False
            else:
                self.worker[buildkey] = {}
                self.worker[buildkey]['status'] = "added"
                must_add = True
            if (must_add):
                self.worker[buildkey]['thread'] = MP4FixWorker(self.threadIndex, event, camid, vq)
                pu.mdbg.log("MP4Rebuilder-->{} is now added".format(buildkey))
                self.threadIndex += 1
        except Exception as e:
            pass 
        return must_add

    def check_status(self,progress=False):
        result = {}
        try:
            i = 0
            #print("mp4fix_check_status-->{}".format(len(self.worker)));
            for t in self.worker:
                result[t] = False
                if (progress):
                    result[t] = 0
                if (len(self.worker[t])>0 and 'thread' in self.worker[t] and self.worker[t]['thread'].rebuild_status()):
                    self.worker[t]['status']='done'
                    result[t] = True
                if (progress):
                    result[t] = self.worker[t]['thread'].progress     
                pu.mdbg.log("MP4Rebuilder.check_status--> idx:{} name:{} key:{} status:{} progrss:{}".format(i,  self.worker[t]['thread'].name, t, self.worker[t]['status'], self.worker[t]['thread'].progress))
                i+=1
            if (self.init_ifcan()):
                if (self.canDeleteCount>5):
                    self.init()
                self.canDeleteCount += 1
            return result
        except Exception as e:
            pu.mdbg.log("[---] error MP4Rebuilder.check_status: {}".format(e))
            return {}

    def init(self):
        self.worker = {}
        self.threadIndex = 1
        self.canDeleteCount = 0
        
    def init_ifcan(self): # check if it can init
        doneCount = 0
        for t in self.worker:
            if (self.worker[t]['status'] == 'done'):
                doneCount += 1
        if (doneCount == len(self.worker)):
            return True
        return False
    
    def can_run(self):
        try:
            if (self.inhibit):
                return False
            if (len(self.worker)<4):
                return True
            else:
                doneCount = 0
                for t in self.worker:
                    if (self.worker[t]['status'] == 'done'):
                        doneCount += 1
                return True if (doneCount>1) else False
            return False
        except Exception as e:
            pu.mdbg.log("[---] error MP4Rebuilder.canrun: {}".format(e))

    def run(self, background=True):
        try:
            if (background):
                for t in self.worker:
                    if (self.worker[t]['status'] != 'started' and self.worker[t]['status'] != 'done'):
                        if (not self.inhibit):
                            self.worker[t]['thread'].start()
                            self.worker[t]['status']='started'
            else:
                self.run_forground()
        except Exception as e:
            pu.mdbg.log("[---] error MP4Rebuilder.run: {}".format(e))
        
    def run_forground(self):
        try:
            for t in self.worker:
                if (self.worker[t]['status'] != 'started' and self.worker[t]['status'] != 'done'):
                    if (not self.inhibit):
                        self.worker[t]['thread'].doFixNow()
                        self.worker[t]['status']='started'
        except Exception as e:
            pu.mdbg.log("[---] error MP4Rebuilder.run_forground: {}".format(e))

#-------------------------------------------

class ExportEventWorker (threading.Thread):
    def __init__(self, threadId, event_path, camid, vq):
        threading.Thread.__init__(self)
        self.threadId = threadId
        self.event_path = event_path
        self.camid = camid
        self.vq = vq
        self.thread_name = "worker-{}-{}-{}-{}".format(self.threadId, event_path, camid, vq)
        self.ret_status = False
        self.progress = 0
    
    def log(self, *arguments, **keywords):
        try:
            logFile = "/tmp/xpt-" + self.getname() + ".txt"
            #logFile = c.wwwroot + self.event_path + "/video/" + self.getname() + ".txt"
            #logFile = c.wwwroot + "/_db" + self.getname() + ".txt"
            with open(logFile,"a") as fp:
                fp.write(dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"))
                fp.write(' '+' '.join(map(str, (arguments))))
                fp.write("\n")
        except Exception as e:
            pass
    
    def getname(self):
        return "{}-{}-{}".format(self.event_path, self.camid, self.vq)
    
    def doItNow(self):
        self.log("starting {}  time:{}".format(self.thread_name, time.ctime(time.time())))
        self.export_evt()
        self.log("finishes {}  time:{}".format(self.thread_name, time.ctime(time.time())))
    
    def run(self):
        self.doItNow()

    def export_evt(self):
        self.ret_status = False
        try:
            results = {}
            self.progress = 0
            
            videoPath = c.wwwroot + self.event_path + "/video/"
            check_path = c.wwwroot + self.event_path + "/video/" + self.vq + "_" + self.camid + "/list_" + self.camid + self.vq + ".m3u8"
            if (os.path.exists(check_path)):
                videoPath = c.wwwroot + self.event_path + "/video/" + self.vq + "_" + self.camid + "/"

            self.progress = 99
            time.sleep(3)
            progress_step = (100 - self.progress) / 3 
            self.progress = 100
            self.ret_status = True
        except Exception as e:
            self.log("[---] export_evt {}".format(e))
        return self.ret_status

    def rebuild_status(self):
        return self.ret_status

class ExportEvent(object):
    def __init__(self):
        super(ExportEvent, self).__init__()
        self.worker = {}
        self.threadIndex = 1
        self.inhibit = False
        self.canDeleteCount = 0 # allow 5 more time to status check to show "ok-mark" in html
        
    def __del__(self):
        pass
    
    def cleanup(self):
        if ('export_status' in tmr_misc):
            tmr_misc['export_status'].kill()
            del tmr_misc['export_status']
    
    def add(self, event, camid, vq):
        must_add = False
        try:
            if (self.inhibit):
                pu.mdbg.log("ExportEvent-->Cannot continue exporting event because it is inhibited")
                return False
#             if (event=='live'):
#                 pu.mdbg.log("ExportEvent-->Cannot continue exporting event due to live mode")
#                 return False
            if (not self.can_run()):
                pu.mdbg.log("ExportEvent-->Cannot continue because too many instances are already running")
                return False
            if (not 'export_status' in tmr_misc):
                tmr_misc['export_status'] = TimedThread(self.check_status, period=10)
            if (self.init_ifcan()):
                self.init()
                
            buildkey = "{}-{}-{}".format(event, camid, vq)
            
            if (buildkey in self.worker and 'status' in self.worker[buildkey]):
                if (self.worker[buildkey]['status']=='started'):
                    pu.mdbg.log("ExportEvent-->{} is already started".format(buildkey))
                    return False
                elif (self.worker[buildkey]['status']=='progress'):
                    pu.mdbg.log("ExportEvent-->{} is in progress".format(buildkey))
                    return False
                elif (self.worker[buildkey]['status']=='added'):
                    pu.mdbg.log("ExportEvent-->{} is added already".format(buildkey))
                    return False
                elif (self.worker[buildkey]['status']=='done'):
                    pu.mdbg.log("ExportEvent-->{} is reported to be done".format(buildkey))
                    must_add = True
                    self.worker[buildkey]['status'] = "added"
                    self.worker[buildkey]['thread'] = False
            else:
                self.worker[buildkey] = {}
                self.worker[buildkey]['status'] = "added"
                must_add = True
            if (must_add):
                self.worker[buildkey]['thread'] = ExportEventWorker(self.threadIndex, event, camid, vq)
                pu.mdbg.log("ExportEvent-->{} is now added".format(buildkey))
                self.threadIndex += 1
        except Exception as e:
            pass 
        return must_add

    def check_status(self,progress=False):
        result = {}
        try:
            i = 0
            #print("export_check_status-->{}".format(len(self.worker)));
            for t in self.worker:
                result[t] = False
                if (progress):
                    result[t] = 0
                if (len(self.worker[t])>0 and 'thread' in self.worker[t] and self.worker[t]['thread'].rebuild_status()):
                    self.worker[t]['status']='done'
                    result[t] = True
                if (progress):
                    result[t] = self.worker[t]['thread'].progress     
                pu.mdbg.log("ExportEvent.check_status--> idx:{} name:{} key:{} status:{} progrss:{}".format(i,  self.worker[t]['thread'].name, t, self.worker[t]['status'], self.worker[t]['thread'].progress))
                i+=1
            if (self.init_ifcan()):
                if (self.canDeleteCount>5):
                    self.init()
                self.canDeleteCount += 1
            return result
        except Exception as e:
            pu.mdbg.log("[---] error ExportEvent.check_status: {}".format(e))
            return {}

    def init(self):
        self.worker = {}
        self.threadIndex = 1
        self.canDeleteCount = 0
        
    def init_ifcan(self):
        doneCount = 0
        for t in self.worker:
            if (self.worker[t]['status'] == 'done'):
                doneCount += 1
        if (doneCount == len(self.worker)):
            return True
        return False
    
    def can_run(self):
        try:
            if (self.inhibit):
                return False
            if (len(self.worker)<4):
                return True
            else:
                doneCount = 0
                for t in self.worker:
                    if (self.worker[t]['status'] == 'done'):
                        doneCount += 1
                return True if (doneCount>1) else False
            return False
        except Exception as e:
            pu.mdbg.log("[---] error ExportEvent.canrun: {}".format(e))

    def run(self, background=True):
        try:
            if (background):
                for t in self.worker:
                    if (self.worker[t]['status'] != 'started' and self.worker[t]['status'] != 'done'):
                        if (not self.inhibit):
                            self.worker[t]['thread'].start()
                            self.worker[t]['status']='started'
            else:
                self.run_forground()
        except Exception as e:
            pu.mdbg.log("[---] error ExportEvent.run: {}".format(e))
        
    def run_forground(self):
        try:
            for t in self.worker:
                if (self.worker[t]['status'] != 'started' and self.worker[t]['status'] != 'done'):
                    if (not self.inhibit):
                        self.worker[t]['thread'].doFixNow()
                        self.worker[t]['status']='started'
        except Exception as e:
            pu.mdbg.log("[---] error ExportEvent.run_forground: {}".format(e))

#-------------------------------------------

class EmailAlert(object):
    def __init__(self):
        pass
    def check_max_stat(self):
        pass
    # send_gmail('alert@avocatec.com', '******', 'admin@yahoo.com', "test", "body 1234\n\tnext line\n\t\tnext line 2\nlast line")
    def send_gmail(self, user, pwd, recipient, subject, body):
        import smtplib
        gmail_user = user
        gmail_pwd = pwd
        FROM = user
        TO = recipient if type(recipient) is list else [recipient]
        SUBJECT = subject
        TEXT = body
        message = "\From: {}\nTo: {}\nSubject: {}\n\n{}".format(FROM, ", ".join(TO), SUBJECT, TEXT)    
        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.ehlo()
            server.starttls()
            server.login(gmail_user, gmail_pwd)
            server.sendmail(FROM, TO, message)
            server.close()
            pu.mdbg.log('successfully sent the mail')
        except:
            pu.mdbg.log("failed to send mail")    


    
    