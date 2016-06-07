import sys
import time
import logging
import os
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler
from watchdog.events import PatternMatchingEventHandler
from datetime import datetime
from test.test_socket import try_address

lasttime = 0
myts = []

class MyHandler(PatternMatchingEventHandler):
    patterns = ["*.ts", "*.m3u8"]

    def process(self, event):
        """
        event.event_type
            'modified' | 'created' | 'moved' | 'deleted'
        event.is_directory
            True | False
        event.src_path
            path/to/observed/file
        """
        global lasttime
        global myts

        # the file will be processed there
        t = time.time()
        delta = t-lasttime
        msg = os.path.basename(event.src_path)
        msg = msg.replace("_segm_","-")
        msg = msg.replace(".ts", "")
        myts.append(msg)

        #print "{0:.2f} --> {1}".format(delta, os.path.basename(event.src_path))  #, event.event_type  # print now only for degug
        if (delta>=0.97):
            print "{0:.2f} --> {1}".format(delta, sorted(myts))
            myts = []
        lasttime = t


    #def on_modified(self, event):
    #    self.process(event)

    def on_created(self, event):
        self.process(event)

def use_wd():
    event_handler = LoggingEventHandler()
    wd = Observer()
    wd.schedule(MyHandler(), path, recursive=True)
    wd.start()
    lasttime = time.time()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        wd.stop()
    wd.join()

class TimeFileData():
    mili = 0
    fileindex = 0
    filetype = 0    
    def __init__(self, mili, fileindex, filetype):
        self.mili = mili
        self.fileindex = fileindex
        self.filetype = filetype


if __name__ == "__main__":
    print os.getcwd()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    path = sys.argv[1] if len(sys.argv) > 1 else '/private/var/www/html/events/live/video'

    #if (not os.path.exists(path)):
    #    print "not live mode...terminated"
    #    sys.exit(0)


    segm = ['00hq_segm_0.ts', '00lq_segm_0.ts', '01hq_segm_0.ts', '01lq_segm_0.ts', '02hq_segm_0.ts', '02lq_segm_0.ts', '03hq_segm_0.ts', '03lq_segm_0.ts', ]
    try:
        for i in xrange(len(segm)):
            print segm[i] + " --> " + "created: %s" % time.ctime(os.path.getctime('/private/var/www/html/events/live/video/'+segm[i]))
        print "----------------------------------------------------------------"
        for i in xrange(len(segm)):
            print segm[i] + " --> " + "modified: %s" % time.ctime(os.path.getmtime('/private/var/www/html/events/live/video/'+segm[i]))
    except Exception as e:
        pass
        
    vids = os.listdir('/private/var/www/html/events/xlive/video')
    templ = ['00hq', '00lq', '01hq', '01lq', '02hq', '02lq', '03hq', '03lq']
    maxfileidx = []
    timefile = [[],[],[],[],[],[],[],[]]
    try:
        for i in xrange(len(vids)):
            for j in xrange(len(templ)):
                if (vids[i].find(templ[j])>=0):
                    mili = os.path.getctime('/private/var/www/html/events/xlive/video/'+templ[i]+"_segm_"+str(i)+".ts")
                    timefile[j].append(TimeFileData(mili,i,j))
    except Exception as e:
        print e
        pass
                
        
        
        

