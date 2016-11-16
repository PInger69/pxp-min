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
import psutil

tmr_misc = {}

# This class helps to rebuild whole mp4 file from the TS files

class MP4FixWorker (threading.Thread):
    """
    Rebuild mp4 file in case video file has been corrupted. Use TS file to rebuild.
    """
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
        """
        Thread base logging. 
        """
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

    def error_log(self, *arguments, **keywords):
        """
        Thread base logging. 
        """
        try:
            logFile = "/tmp/fix-error-" + self.getname() + ".txt"
            #logFile = c.wwwroot + self.event_path + "/video/" + self.getname() + ".txt"
            #logFile = c.wwwroot + "/_db" + self.getname() + ".txt"
            with open(logFile,"a") as fp:
                fp.write(dt.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S.%f"))
                fp.write(' '+' '.join(map(str, (arguments))))
                fp.write("\n")
        except Exception as e:
            pass
    
    def getname(self):
        """
        build name with event path, cam ID and video quality 
        """
        return "{}-{}-{}".format(self.event_path, self.camid, self.vq)
    
    def doFixNow(self):
        """
        Start rebuilding mp4 files 
        """
        self.log("starting {}  time:{}".format(self.thread_name, time.ctime(time.time())))
        self.rebuild_mp4()
        self.log("finishes {}  time:{}".format(self.thread_name, time.ctime(time.time())))
    
    def run(self):
        self.doFixNow()

    def rebuild_mp4(self):
        """
        Rebuild mp4 files using TS files 
        """
        self.ret_status = False
        try:
            if (os.path.exists("/tmp/fix-" + self.getname() + ".txt")):
                cmd = 'rm -f ' + "/tmp/fix-" + self.getname() + ".txt"
                os.system(cmd)
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
            self.log("[---] rebuild_mp4 {} {}".format(str(e),sys.exc_info()[-1].tb_lineno))
            
        return self.ret_status

    def getseginfo(self, camid="00", vq="hq", event='live'):
        """
        Get ts segment information such as first and last index.
        Input:
            camid(str): leading zero based can ID string
            vq(str): cam quality designator
            event(str): event name
        returns:
            result(dict): segment information
        """
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
                    if (results['first_seg'].find("_")>=0):
                        results['first_idx'] = int(results['first_seg'].split('.')[0].split('_')[2]) # get first index
                    else: # old style segm0, segm1 etc.
                        fidx = results['first_seg'].find('.')
                        results['first_idx'] = int(results['first_seg'][4:fidx]) # old style ts file
            if (results['last_seg']):
                if (os.path.exists(videoPath+results['last_seg'])):
                    if (results['last_seg'].find("_")>=0):
                        results['last_idx'] = int(results['last_seg'].split('.')[0].split('_')[2])  # get last index
                    else:
                        fidx = results['last_seg'].find('.')
                        results['last_idx'] = int(results['last_seg'][4:fidx]) # old style ts file
            return results
        except Exception as e:
            msgstr=str(sys.exc_info()[-1].tb_lineno)+' '+str(e)
            self.log("[---] error getseginfo: {}  path:{}".format(msgstr, videoPath))
            return False

    def convert_ts2mp4(self, event_path, camid, vq):
        """
        Convert TS file to mp4 file using handbrake...
        Input:
            camid(str): 0 based cam ID
            vq(str): camera video quqality
            event(str): event name
        returns:
            None
        """
        import subprocess
        tsfilename = event_path + "all_" + camid + vq + ".ts"
        (tsfilebase, fext) = os.path.splitext(tsfilename)
        mp4_path = "{}{}".format(tsfilebase, ".mp4")
        if (os.path.exists(mp4_path)):
            os.system("rm " + mp4_path)
        try:
            self.log("convert file from:{}  to:{}".format(tsfilename, mp4_path))
            hbrake_param = "-i {} -o {} --preset=\"Android Tablet\"".format(tsfilename, mp4_path)
            if (pu.pxpconfig.hbrake_conf()):
                hbrake_param = pu.pxpconfig.hbrake_conf()
                if (hbrake_param.find("{}")>=0):
                    hbrake_param = hbrake_param.format(tsfilename, mp4_path)
            hbcmd = c.handbrake + " " + hbrake_param
            hbbrake_timeout = pu.pxpconfig.hbbrake_timeout()
            self.log('hb_cmd---->{}  hb_slowness_detection_timeout:{}'.format(hbcmd, hbbrake_timeout))
            
            #hbcmd = c.handbrake + " -i {} -o {} --preset=\"Android Tablet\"".format(tsfilename, mp4_path)
            #subprocess.check_call(hbcmd, shell=True)
            
            # ffmpeg command test only         
            if (pu.pxpconfig.use_ffbrake()):   
                ffmpeg_param = "-y -i {} -f mp4 {}".format(tsfilename, mp4_path)
                return self.convert_via_ffmpeg(ffmpeg_param)
            
            
            hb_cmd = hbcmd.split(' ')
            hbproc = subprocess.Popen(hb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            cur_progress = self.progress
            
            # this parsing line should be changed if the HB version is upgraded or changed...
            # for now, it looks for following lines like this: Encoding: task 1 of 1, 100.00 % (521.78 fps, avg 533.34 fps, ETA 00h00m00s)
            #
            percent_templ = re.compile("([A-z0-9: ]*[,]+)([ ]+)([.0-9][0-9. ]+[%]+)", re.I)
            line = ''
            error_line = ''
            use_stderr = False
            slowness_mark = False
            old_progress = 0
            while hbproc.poll() is None:
                out = hbproc.stdout.read(1)
                if (use_stderr):
                    err = hbproc.stderr.read(1)
                    error_line += err
                    if (err == '\r' or err == '\n'):
                        self.error_log('error-out:'+error_line)
                #sys.stdout.write(out)
                line += out
                if (out == '\r'):
                    if (line.find('%')>0):
                        percent = percent_templ.match(line)
                        if (percent != None):
                            if (isinstance(percent.group(3), basestring)):
                                float_progress = float(percent.group(3).split(' ')[0])
                                self.progress = cur_progress + int(float_progress/100.0*75.0) # 75% usage for this procedure
                        self.log('out:'+line+ '---->' + str(self.progress) + "  " + str(float_progress))
                        # check slowness of progress
                        if (old_progress == float_progress):
                            if (not slowness_mark):
                                slowness_mark = time.time()
                        else:
                            slowness_mark = False
                        if (slowness_mark and (time.time()-slowness_mark) > hbbrake_timeout): # 5 min
                            sys.stdout.flush()
                            self.log('out: TOO SLOW PROGRESS stopped at {}%  hb_pid:{} killed'.format(str(float_progress), hbproc.pid))
                            hbproc.kill()
                            hbproc = False
                            time.sleep(3)
                            ffmpeg_param = "-y -i {} -f mp4 {}".format(tsfilename, mp4_path)
                            self.log('trying to use ffmpeg instead now...') 
                            self.convert_via_ffmpeg(ffmpeg_param)
                            break            
                        old_progress = float_progress
                        # end of check slowness of progress
                    line = ''
                sys.stdout.flush()            
                if (use_stderr):
                    sys.stderr.flush()            

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
            self.log('[---] convert_ts2mp4:' + str(sys.exc_info()[-1].tb_lineno) + " " + str(e))
            pass            

    def parse_timestamp(self, time_stamp): # 00:00:00.99
        total_time = 0
        duration = time_stamp.split(".")
        msec = duration[1]
        sec = duration[0].split(":")
        if (len(sec)>=3):
            total_time = int(sec[0])*3600+int(sec[1])*60+int(sec[2])
        return total_time

    def update_ffmpeg_duration(self, stderrLine):
        """
        Check if following line is generated from the ffmpeg lines...
        Duration: 00:00:12.68, start: 1.933333, bitrate: 521 kb/s
        """
        try:
            self.log('ffmpeg-out:'+stderrLine)
            st = stderrLine.find("Duration:")
            if (st>=0):
                ed = stderrLine.find(",")
                if ((st+9)>=0 and ed>=0 and ed>st):
                    total_time = self.parse_timestamp(stderrLine[(st+9):ed])
                    self.log('ffmpeg-out: total_time==>{}  timestamp:{}'.format(str(total_time),stderrLine[(st+9):ed]))
                    return total_time
        except Exception as e:
            self.log('[---] update_ffmpeg_duration:' + str(sys.exc_info()[-1].tb_lineno) + " " + str(e))
        return False
    
    def update_ffmpeg(self, c_progress, stderrLine, total_time):
        """
        Check if following line is generated from the ffmpeg lines...
        frame=   52 fps=0.0 q=29.0 size=      64kB time=00:00:01.77 bitrate= 296.5kbits/s dup=3 drop=0 speed=3.43x    
        """
        try:
            if (stderrLine.find("frame=")>=0 and total_time):
                st = stderrLine.find("time=")
                ed = stderrLine.find("bitrate")
                if (st>=0 and ed>=0 and (ed-1)>(st+5)):
                    ctime = self.parse_timestamp(stderrLine[(st+5):(ed-1)])
                    self.progress = c_progress + int((ctime / total_time) * 100 * 0.75)
                    self.log('ffmpeg-out: c_time==>{}/{} progress:{} timestamp:{}'.format(str(ctime), str(total_time),str(self.progress), stderrLine[(st+5):(ed-1)]))
        except Exception as e:
            self.log('[---] update_ffmpeg:' + str(sys.exc_info()[-1].tb_lineno) + " " + str(e))
        return self.progress

    def convert_via_ffmpeg(self, cmdparam):
        try:
            self.log("**********************************************************************")
            self.log("**********************************************************************")
            self.log("*** FFMPEG CONVERSION ************************************************")
            self.log("**********************************************************************")
            self.log("**********************************************************************")
            c_progress = self.progress
            total_time = False
            cmd = c.ffbin + " " + cmdparam
            self.log("ff_cmd:{}".format(cmd))
            ffmpeg_cmd = cmd.split(' ')
            import subprocess
            ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            error_line = ''
            start_time = time.time()
            while ffmpeg_proc.poll() is None:
                err = ffmpeg_proc.stderr.read(1)
                if (err == '\r' or err == '\n'):
                    self.log('ffmpeg-out:{}'.format(error_line))
                    if (not total_time):
                        duration = self.update_ffmpeg_duration(error_line) 
                        total_time = duration
                    else:
                        self.update_ffmpeg(c_progress, error_line, total_time)
                    error_line = ''
                else:
                    error_line += err
                if (time.time()-start_time>60 and not total_time):
                    self.log('Cannot convert_via_ffmpeg because "Duration" is not found')
                    break;
                sys.stderr.flush()
        except Exception as e:
            self.log('[---] convert_via_ffmpeg:' + str(sys.exc_info()[-1].tb_lineno) + " " + str(e))

    def concat_ts(self, last_idx, camid="00", vq="hq", event='live'):
        """
        Concatenate all of ts files into one single file to convert.
        """
        self.log("concatenating ts files started...last index:{}".format(last_idx))
        try:
            videoPath = c.wwwroot + event + "/video/"
            check_path = videoPath + vq + "_" + camid + "/list_" + camid + vq + ".m3u8"
            if (os.path.exists(check_path)):
                videoPath = c.wwwroot + event + "/video/" + vq + "_" + camid + "/"
            
            all_ts = videoPath + "all_" + camid + vq + ".ts"
            if (os.path.exists(all_ts)):
                os.system("rm " + all_ts)
            
            old_style_ts = False
            if (os.path.isfile(videoPath+"main.mp4") and os.path.isfile(videoPath+"list.m3u8")):
                old_style_ts = True
            
            progress_step = int(15.0/float(last_idx)) # 15% usage for this procedure   
            for i in xrange(last_idx):
                segn = videoPath + camid + vq + "_segm_" + str(i) + ".ts"
                if (old_style_ts):
                    segn = videoPath + "segm" + str(i) + ".ts"
                cmd = "cat " + segn + " >> " + all_ts
                self.log("count:{}/{}   cmd:{}".format(i, last_idx, segn))
                os.system(cmd)
                self.progress += int(progress_step)
        except Exception as e:
            msgstr=str(sys.exc_info()[-1].tb_lineno)+' '+str(e)
            self.log("[---] concat_ts:{}    path:{}".format(msgstr, all_ts))
        self.log("concatenating ts files ends...path:{}  file size:{} MB".format(all_ts, os.path.getsize(all_ts)/1e6))

    def rebuild_status(self):
        """
        Return status of building
        """
        return self.ret_status

class MP4Rebuilder(object):
    """
    MP4 rebuilder: it collects all of the events and initiate the process. 
    """
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
        """
        Collect event to rebuild with event name, camid and video quality
        """
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
        """
        Return status of rebuilding status
        """
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
        """
        Initializer
        """
        self.worker = {}
        self.threadIndex = 1
        self.canDeleteCount = 0
        
    def init_ifcan(self): 
        """
        Check if it can init
        """
        doneCount = 0
        for t in self.worker:
            if (self.worker[t]['status'] == 'done'):
                doneCount += 1
        if (doneCount == len(self.worker)):
            return True
        return False
    
    def can_run(self):
        """
        Check if option and maximum limit to run
        """
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
        """
        Not used (test only)
        """
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
    """
    Export event from the web UI
    """
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
    """
    Event exporter from the web UI
    """
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
class TestMuxWorker (threading.Thread):
    """
    Test Only
    """
    def __init__(self):
        threading.Thread.__init__(self)
        self.p = False
        self.out = False
        self.inp = False
        #    -mpegts_service_id 3 \
#         self.ffcmd = '/usr/bin/ffmpeg -fflags +igndts -thread_queue_size 1024 -i "rtsp://192.168.5.139/media/video1"  -thread_queue_size 1024 -i "rtsp://192.168.5.139/media/video2" -thread_queue_size 1024 -i "rtsp://192.168.5.139/media/video3" \
#             -fflags +igndts -c copy -an -map 0:v -map 0:1 \
#             -fflags +igndts -c copy -an -map 1:v -map 1:1 \
#             -fflags +igndts -c copy -an -map 2:v -map 2:1 \
#             -f mpegts udp://127.0.0.1:22600'
#         self.ffcmd = '/usr/bin/ffmpeg -fflags +igndts -thread_queue_size 1024 -rtsp_transport tcp -i "rtsp://192.168.5.139/media/video1" -thread_queue_size 1024 -rtsp_transport tcp -i "rtsp://192.168.5.139/media/video2" \
#                 -fflags +igndts -codec copy -an -map 0:v -map 0:1 \
#                 -fflags +igndts -codec copy -an -map 1:v -map 1:1 \
#                 -mpegts_service_id 1  -muxrate 3M \
#                 -f mpegts udp://127.0.0.1:22600?pkt_size=1316'
        self.ffcmd = '/usr/bin/ffmpeg -fflags +igndts -thread_queue_size 1024 -rtsp_transport tcp -i "rtsp://192.168.5.139/media/video1" -thread_queue_size 1024 -rtsp_transport tcp -i "rtsp://192.168.5.139/media/video2" \
                -fflags +igndts -codec copy -map 0:v  \
                -fflags +igndts -codec copy -map 1:v  \
                -fflags +igndts -codec copy -map 0:a  \
                -mpegts_service_id 1  -muxrate 3M \
                -f mpegts udp://127.0.0.1:22600?pkt_size=1316'
#         self.ffcmd = '/usr/bin/ffmpeg -fflags +igndts -i "rtsp://192.168.5.139/media/video1"  \
#                 -fflags +igndts -codec copy -an -map 0:v -map 0:1 \
#                 -mpegts_service_id 1  \
#                 -f mpegts udp://127.0.0.1:22600?pkt_size=1316'
    def run(self):
        import subprocess
        try:
            self.p = subprocess.Popen(self.ffcmd, shell=True, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            while True:
                self.out = self.p.stderr.read(1)
                self.inp = self.p.stdin
                if self.out == '' and self.p.poll() != None:
                    break
                if self.out != '':
                    sys.stdout.write(self.out)
                    sys.stdout.flush()            
        except subprocess.CalledProcessError as e1:
            print("CalledProcessError!! {}".format(e1))
        except OSError as e2:
            print("OSError!! {}".format(e2))
        except Exception as e:
            print('[---] test.run:{}'.format(e))
    def stop(self):
        try:
            for i in xrange(3):
                if (self.inp):
                    self.inp.write('q')
                    time.sleep(1)
            print('muxer stopped')
        except:
            if (psutil.pid_exists(self.p.pid)):
                self.p.send_signal(signal.SIGINT)

class TestSegWorker (threading.Thread):
    """
    Test Only
    """
    def __init__(self):
        threading.Thread.__init__(self)
        self.p = False
        self.out = False
        self.inp = False
        #audio only
        #self.segcmd = '/usr/bin/mediastreamsegmenter -a -p -t 1s -S 1 -s 4 -B 00hq_segm_ -i list_00hq.m3u8 -f /var/www/html/events/test 127.0.0.1:22600'
        self.segcmd = '/usr/bin/mediastreamsegmenter -p -t 1s -S 1 -s 4 -B 00hq_segm_ -i list_00hq.m3u8 -f /var/www/html/events/test 127.0.0.1:22600'
    def run(self):
        import subprocess
        try:
            self.p = subprocess.Popen(self.segcmd, shell=True, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            while True:
                self.out = self.p.stderr.read(1)
                self.inp = self.p.stdin
                if self.out == '' and self.p.poll() != None:
                    break
                if self.out != '':
                    sys.stdout.write(self.out)
                    sys.stdout.flush()            
        except subprocess.CalledProcessError as e1:
            print("CalledProcessError!! {}".format(e1))
        except OSError as e2:
            print("OSError!! {}".format(e2))
        except Exception as e:
            print('[---] test.run:{}'.format(e))
    def stop(self):
        if (self.p):
            self.p.send_signal(signal.SIGINT)
            time.sleep(1)
            if (psutil.pid_exists(self.p.pid)):
                self.p.kill()
            #self.p.terminate()
            #self.p.kill()
            print('segmenter stopped')

def fix_m3u8():
    """
    Check if m3u8 file is capped properly for each event and it make sure capped properly.
    Fix m3u8 (terminating with #EXT-X-ENDLIST)
    Input:
        None
    Return:
        None
    """
    f =''
    try:
        for root, dirs, files in os.walk("/private/var/www/html/events"):
            for pl_file in files:
                f = root + "/" + pl_file
                if file.endswith(".m3u8") and not os.path.islink(f):
                    #print(f)
                    if ((root.endswith("video") and not os.path.exists(root+"/hq_00"))  # video folder and no hq_XX
                        or (root.find('video/hq_')>=0 or root.find('video/lq_')>=0)):   # hq_XX or lq_XX folder only
                        pl = open(f,'rb')
                        lines = pl.readlines()
                        if lines:
                            #first_line = lines[:1]
                            last_line = ''
                            i = 1
                            while i<len(lines):
                                last_line = lines[-i]
                                i += 1
                                if (last_line != '\n'):
                                    break
                        pl.close()
                        print ("{} last:{}".format(f, last_line.replace("\n","")))
                        if (last_line.find('EXT-X-ENDLIST')<0 and f.find('list_templ')<0 and not os.path.islink(f)):
                            fp = open(f, 'a')
                            fp.write("#EXT-X-ENDLIST\n")
                            fp.close()
                            print ("ENDLIST is added in file:{} ".format(f))
    except Exception as e:
        print(e)

