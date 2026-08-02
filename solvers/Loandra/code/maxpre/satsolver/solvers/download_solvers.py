from __future__ import print_function
import tarfile
import os
import shutil

try:
    from urllib2 import urlopen
    from urllib2 import Request
except ImportError:
    from urllib.request import urlopen
    from urllib.request import Request



DOWNLOAD=1
DOWNLOAD_IF_NOT_EXIST=2
EXTRACT=4
EXTRACT_IF_NOT_EXISTS=8
COMPILE=16

#GLUCOSE3 = DOWNLOAD_IF_NOT_EXIST | EXTRACT_IF_NOT_EXISTS | COMPILE
GLUCOSE3 = EXTRACT_IF_NOT_EXISTS | COMPILE


if GLUCOSE3: #download glucose 3
    url="http://www.labri.fr/perso/lsimon/downloads/softwares/glucose-3.0.tgz"
    #save_to="glucose3.tar.gz"
    save_to="glucose-3.0-modified.tar.gz"
    extract_to="glucose-3.0" # must be same as defined in tar repo!
    compile_command="(cd glucose-3.0/core/ && make libs)"

    if (GLUCOSE3 & DOWNLOAD) or ( (GLUCOSE3 & DOWNLOAD_IF_NOT_EXIST) and not os.path.exists(save_to) ):
        print("will download...")

        t=urlopen(url)
        f=open(save_to, "wb")
        while 1:
            buff=t.read(2048)
            if not buff:    break
            f.write(buff)
        f.close()
        print("downloaded")

    if (GLUCOSE3 & EXTRACT) or ( (GLUCOSE3 & EXTRACT_IF_NOT_EXISTS) and not os.path.exists(extract_to) ):
        print("will extract...")

        if os.path.exists(extract_to): shutil.rmtree(extract_to)
        tfile = tarfile.open(save_to, 'r:gz')
        tfile.extractall(".")

        print("extracting done")

    if (GLUCOSE3 & COMPILE):
        print("will compile")
        os.system(compile_command)
        print("compiled")

