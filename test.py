#/usr/bin/python
import time, thread, subprocess as sb, psutil, os, signal
import threading

class ffthread(threading.Thread):
	def __init__ (self, timerTick):
		threading.Thread.__init__(self)
		self.timerTick = timerTick
	def mon(self):
		try:
			start_time = time.time()
			now = start_time
			ffstarted = False
			fref = None
			while(True):
				if((now-start_time)<self.timerTick):
					now = time.time()
					continue
				print "now ", now
				start_time=now
				if not ffstarted:
					camid = "0"
					fref = sb.Popen("ffmpeg -i rtsp://192.168.1.107:554/stream1 -codec copy -f h264 udp://127.0.0.1:221"+camid+" -codec copy -f mpegts udp://127.0.0.1:220"+camid+" 2>/var/www/html/events/_db/live.log &",shell=True, preexec_fn=os.setsid)
					ffstarted = True
				else:
					# print "trying to kill all processes..."
					# os.killpg(fref.pid, signal.SIGTERM)
					try:
						ps = psutil.Process(fref.pid)
						print ps.get_cpu_percent()
					except Exception as e:
						print e
		except Exception as e:
			print e
	def run(self):
		self.mon()

thread = ffthread(10) #run the monitor function every 2 seconds
thread.start()
thread.join()

# thread.start_new_thread(mon,())

