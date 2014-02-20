# app version
ver 					= "1.0.0"
# where application executables are
approot 				= "/var/www/html/min/"
# where events and config files are stores
wwwroot 				= "/var/www/html/events/"
# minimum free space required in order to have an encode running
minFreeSpace 			= 1073741824 * 5 #5gb
# path to the pXp configuration file
pxpConfigFile 			= wwwroot+"_db/.pxpcfg"
# ffmpeg/avconv name (used for starting and killing)
# ffmpeg used to capture streams and create mp4 files
# also used to extract clips and create thumbnails
ffname 					= "ffmpeg"
ffbin 					= "/usr/bin/"+ffname
# HLS segmenter - creates m3u8 file and .ts files
# name used for starting/killing
segname 				= "mediastreamsegmenter"
segbin 					= "/usr/bin/"+segname
#path to the list of all teradek cameras
tdCamList 				= wwwroot+"_db/.tdlist"