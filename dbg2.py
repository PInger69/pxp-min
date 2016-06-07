import glob
import os

os.chdir('/private/var/www/html/events/live/video')

for i in xrange(4):
    s1 = str(i).zfill(2)+"hq_segm*.ts"
    s2 = str(i).zfill(2)+"lq_segm*.ts"
    print s1, len(glob.glob(s1))
    print s2, len(glob.glob(s2))


