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
from threading import Thread
import time
# timed thread class. 
class TimedThread(Thread):
    def __init__(self,callback,params=(),period=0, autostart=True):
        super(TimedThread, self).__init__()
        self.running = True
        self.timeout = period #how often to run a specified function
        self.sleeptime = min(1,period/2) #how much to sleep while waiting to run the next time
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
                print "THREAD ",self.callback.__name__," ERROR: ",e
                pass
        #end while
    #end run
    def kill(self):
        self.stop()
        self.join()

