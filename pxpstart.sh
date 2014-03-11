#/bin/sh
#start service manager
python /var/www/html/min/pxpservice.pyc
#start m3u8 file monitor
python /var/www/html/min/pxplistmon.pyc
#start the initialization script
python /var/www/html/min/pxpstart.pyc