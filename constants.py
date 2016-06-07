# app version
ver 					= "1.1.8"
# where application executables are
approot 				= "/var/www/html/min/"
# where events and config files are stores
wwwroot 				= "/var/www/html/events/"
live_video              = "/var/www/html/events/live/video/"
# minimum free space required in order to have an encode running
minFreeSpace 			= 1073741824 * 5 #5gb
# path to the pXp configuration file
pxpConfigFile 			= wwwroot+"_db/.pxpcfg"
# ffmpeg/avconv name (used for starting and killing)
# ffmpeg used to capture streams and create mp4 files
# also used to extract clips and create thumbnails
ffname 					= "ffmpeg"
ffbin 					= "/usr/bin/"+ffname
#ffbin 					= "/usr/local/bin/"+ffname
# HLS segmenter - creates m3u8 file and .ts files
# name used for starting/killing
segname 				= "mediastreamsegmenter"
segbin 					= "/usr/bin/"+segname
#path to the list of all teradek cameras
devCamList 				= wwwroot+"_db/.tdlist"
encStatFile				= wwwroot+"_db/.encstat"
rtmpStatFile            = wwwroot+"_db/.rtmpstat"
sessdir 				= wwwroot+"session/"
logFile					= wwwroot+"_db/pxpservicelog.txt"
tmpLogFile              = wwwroot+"_db/mypxp.txt"
maxLogSize 				= 50 * 1024 * 1024 #50 Mb
curUsbDrv               = wwwroot+"_db/cusbdrv"
mp4info_ext             = ".info.txt"
mp4progress_ext         = ".mp4.progress"
handbrake               = "/Applications/HandBrakeCLI"
fifo_size               = "?fifo_size=1000000&overrun_nonfatal=1"
segment_conf            = "-p -t 1s -S 1 -B"
hbrake_conf             = " -i {} -o {} --preset=\"Android Tablet\""
# maximum number of video sources in the system
maxSources				= 10
CAPTURE                 = 'capture_'
SEGMENT                 = 'segment_'
RECORD                  = 'record_' 
cloud					= "http://myplayxplay.net/maxdev/"
