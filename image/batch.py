import sys,os

import fileinput,time,requests,optparse,logging
from dateutil import parser
import metrics_influx

counters = {}
metrics = {}
id = None
_URL=None

logging.basicConfig(level=logging.INFO,format='%(asctime)s:%(levelname)s %(message)s')
logging.getLogger("requests").setLevel(logging.WARNING)

def post(contentType,msg):
    if _URL is not None:
        requests.post(_URL, data = msg)
        
def formatTimeStamp(timestr):
    """ return timestr as number of milliseconds since epoch"""
    dt = parser.parse(timestr)
    tstamp = int(time.mktime(dt.timetuple())*1000+dt.microsecond/1000)
    return tstamp


usage = "usage: %prog [options] filename"
_parser = optparse.OptionParser(usage=usage)
_parser.add_option("-p", "--port", dest="port",
                  help="InfluxDB port", type="int", default=8086)
_parser.add_option("-H", "--hostname", dest="hostname",
                  help="Hostname", default="influxdb")
_parser.add_option("-D", "--database", dest="db", default="nuodb")

(options, args) = _parser.parse_args()
    
_URL='http://%s:%d/write?db=%s' % (options.hostname,options.port,options.db)


logging.info("Timezone being used GMT%s." % time.strftime('%z'))

_count = 0
for line in fileinput.input(args,openhook=fileinput.hook_compressed):
    if line == '\n':
        if id is not None:
            counters[id] = metrics
            post(*metrics_influx.format(metrics))
            id = None
    if "[" in line:
        _count += 1
        if _count % 1000 == 0:
            logging.info("Processing [%d] %d ..." % (fileinput.lineno(),_count))
            
        id = line[line.find("]")+2:]
        timestamp = line[0:line.find(" [")]
        id = id[:id.find(":")+6]
        if id not in counters:
            counters[id] = {}
        metrics = counters[id]
        metrics["TimeStamp"] = formatTimeStamp(timestamp)
        f=line.split(" ")
        if f[-10] == "db":
            metrics["Database"] = f[-8]
        else:
            metrics["Database"] = "unknown"
    elif "=" in line:
        key,eq,value=line.split()
        metrics[key] = value
        
post(*metrics_influx.format(metrics))
sys.exit(0)
