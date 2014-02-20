lfile = "/var/www/html/events/live/video/list.m3u8"
import time
with open(lfile) as file_:
    # Go to the end of file
    file_.seek(0,2)
    while True:
        curr_position = file_.tell()
        print curr_position
        line = file_.readline()
        if not line:
            file_.seek(curr_position)
        else:
            print line, "YAY!"
        time.sleep(0.1)