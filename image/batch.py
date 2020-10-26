import sys,os

import fileinput,time,requests,optparse,logging
from dateutil import parser
import metrics_influx
from urlparse import urlparse
from urlparse import urljoin

counters = {}
metrics = {}
id = None
_URL=None
_OUTPUT=None

os.environ['TZ'] = 'GMT'

logging.basicConfig(level=logging.INFO,format='%(asctime)s:%(levelname)s %(message)s')
logging.getLogger("requests").setLevel(logging.WARNING)

def post(contentType,msg):
    if _URL:
        requests.post(_URL, data = msg)
    elif _OUTPUT:
        print >> _OUTPUT,msg,


def formatTimeStamp(timestr):
    """ return timestr as number of milliseconds since epoch"""
    dt = parser.parse(timestr)
    tstamp = int(time.mktime(dt.timetuple())*1000+dt.microsecond/1000)
    return tstamp


usage = "usage: %prog [options] filename"
_parser = optparse.OptionParser(usage=usage)
_parser.add_option("-o", "--output", dest="output",
                   help="url to file (file://filename, stdout:) or influx server (http://server:8086)",
                   default="http://influxdb:8086")
# _parser.add_option("-p", "--port", dest="port",
#                   help="InfluxDB port", type="int", default=8086)
# _parser.add_option("-H", "--hostname", dest="hostname",
#                   help="Hostname", default="influxdb")
_parser.add_option("-D", "--database", dest="db", default="nuodb")

(options, args) = _parser.parse_args()
    

o = urlparse(options.output)
if o.scheme == 'http' or o.scheme == 'https':
    _URL= urljoin(options.output, "/write?db=%s" % (options.db))
elif o.scheme == '' or o.scheme == 'file':
    if o.path == 'stdout':
        _OUTPUT = sys.stdout
    else:
        _OUTPUT = open(o.path,'wb')
elif o.scheme == 'stdout':
    _OUTPUT = sys.stdout

    
logging.info("Timezone being used GMT%s." % time.strftime('%z'))

if _URL is None:
    print >> _OUTPUT, "# DML"
    print >> _OUTPUT, "# CONTEXT-DATABASE: nuodb"
    print >> _OUTPUT, "# CONTEXT-RETENTION-POLICY: nuodbrp\n"

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
if _OUTPUT:
    _OUTPUT.close()
sys.exit(0)
