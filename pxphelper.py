from time import sleep
from datetime import datetime as dt
import pxputil as pu, constants as c, os, json, re, shutil, sys, subprocess, time, glob
import pprint as pp
from test.test_socket import try_address
import threading

# This helps to run the work load in the background from the web request, which improves the response time. 

class PXPHeler(threading.Thread):
    def __init__(self, cmd, cookie, param):
        threading.Thread.__init__(self)
        self.cmd = cmd
        self.cookie = cookie
        self.param = param
        self.thread_name = "worker-{}-{}".format(cookie, cmd)
        self.t = time.time()
        self.done = False
        self.rec_stat = {}

    def __str__(self):
        return "{}--> time_elapsed:{}  param:{} done:{}".format(self.thread_name, time.time()-self.t, self.param, self.done)
    
    def pxp_rec_stat(self):
        import pxp # want to have fresh instance ???!
        ans={}
        for i in xrange(1):
            ans = pxp.rec_stat(self.param)
            if ('success' in ans and ans['success']):
                break
            else:
                time.sleep(1)
        return ans
    
    def run(self):
        """
        rec_stat caller from the service
        """
        import pxp # want to have fresh instance ???!
        ans = {}
        pu.mdbg.log("PXPWORKER started ------>cmd:{} cookie:{}".format(self.cmd, self.cookie))
        if (self.cmd=='tagset'):
            ans = pxp.tagset(self.param)
        elif (self.cmd=='tagmod'):        
            ans = pxp.tagmod(self.param)
        elif (self.cmd=='teleset'):        
            ans = pxp.teleset(self.param)
        elif (self.cmd=='sumset'):        
            ans = pxp.sumset(self.param)
        elif (self.cmd=='sumget'):        
            ans = pxp.sumget(self.param)
        elif (self.cmd=='rec_stat'):
            self.rec_stat = {}
            self.rec_stat = self.pxp_rec_stat()
            self.done = True
            ans['cookie'] = self.cookie
            pu.mdbg.log("PXPHeler finished ------>cmd:{} param:{}".format(self.cmd, self.param))
            return
                        
        ans['cookie'] = self.cookie
        #resp = pu.disk.sockSendWait("AUP|"+json.dumps(ans), addnewline=True, timeout=1)
        pu.disk.sockSendWait("AUP|"+json.dumps(ans), addnewline=True)
        self.done = True
        pu.mdbg.log("PXPHeler finished ------>cmd:{} cookie:{}".format(self.cmd, self.cookie))

