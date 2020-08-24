"""
proc=$1
clk_tck=$(getconf CLK_TCK)
pids=$(pidof $proc)
for pid in $pids;
do
    for tid in /proc/$pid/task/*; do
      stats=$(cat "$tid/stat")
      statarr=($stats)
      utime=${statarr[13]}
      stime=${statarr[14]}
      cputime=$(bc <<< "scale=3; $utime / $clk_tck + $stime / $clk_tck")
      usertime=$(bc <<< "scale=3; $utime / $clk_tck")
      systime=$(bc <<< "scale=3; $stime / $clk_tck")
      echo -e "$proc\t$pid\t$(basename $tid)\t$usertime\t$systime\t$cputime"
    done
done
"""

import os
import fileinput
import glob
import time
import sys
from datetime import datetime
import subprocess
import socket
import re
from six import *

import signal
def signal_handler(sig, frame):
   sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

#lineformat =  "CPUThread,host=%s,processid=%s,threadid=%s,state=%s,exe=%s,lcpu=%d utime=%f,stime=%f,ttime=%f,minf=%d,majf=%d %s"
#timefmt="%s%f000"
lineformat = "%s,%s,%s,%s,%s,%d,%f,%f,%f,%d,%d,%s"
timefmt="%s%f"
print("#host,processid,threadid,state,exe,lcpu,utime,stime,ttime,minf,majf,time")

hostname=socket.gethostname()
clk_tck = os.sysconf(os.sysconf_names['SC_CLK_TCK'])

if len(sys.argv) < 2:
   process_name = "nuodb"
else:
   process_name = sys.argv[1]


pat = "(\d+) \((.*)\)"
m   = re.compile(pat)


while True:
   _pids = None
   try:
      # assume only one process by given name
      #_pid = subprocess.check_output(["pidof", process_name ])
      _pid = subprocess.check_output(["pgrep", process_name ])
      _pids = _pid[:-1].split()
   except:
      print_("Unexpected error: %s" % sys.exc_info()[0],file=sys.stderr)
      sys.stderr.flush()
      time.sleep(10)
      continue
   
   last_measurements = {}

   while True:
      lines = []
      now = datetime.now()
      tasks = []
      for _pid in _pids:
         tasks.extend(glob.glob("/proc/%s/task/*/stat" % (_pid)))

      if not tasks:
         break
         
      queue = []
      # what happens if process goes away before all tasks
      # are read?  does this hang?  throw exception ?
      for line in fileinput.input(tasks):
         queue.append(line)

      for line in queue:
         result = m.match(line)
         pid, exe = result.groups()
         args = line[:-1].split(' ')
         args = args[-50:]
         if pid == _pid:
            continue
         args.insert(0,exe)
         args.insert(0,now)
         if pid in last_measurements:
            prev_measurement = last_measurements[pid]
            exe = args[1]
            state = args[2]
            minf = int(args[9]) - int(prev_measurement[9])
            majf = int(args[11]) - int(prev_measurement[11])
            lcpu = int(args[38])
            deltatime = now - prev_measurement[0]
            dt = deltatime.total_seconds()
            utime = (( float(args[13]) - float(prev_measurement[13]))/clk_tck)*100./dt
            stime = (( float(args[14]) - float(prev_measurement[14]))/clk_tck)*100./dt
            ttime = utime + stime
            print(lineformat % (hostname, _pid, pid,state,exe,lcpu,utime,stime,ttime,minf,majf,now.strftime(timefmt)))
         last_measurements[pid] = args

      tbd = [ k for k in last_measurements.iterkeys() if last_measurements[k][0] != now ]
      for k in tbd:
         del last_measurements[k]
      sys.stdout.flush()

      wait = datetime.now() - now
      sleepFor = 10 - wait.total_seconds() - 1./clk_tck
      time.sleep(sleepFor)

   time.sleep(10)
