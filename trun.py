#/usr/bin/python
import time
print "START!!"
start_time = time.time()
while(True):
        if((time.time()-start_time)<2):#run the function every 2 seconds
                time.sleep(0.5) #dramatically reduces the load on the CPU
                continue
        start_time = time.time()
        print "YUP!"
print "done??"

