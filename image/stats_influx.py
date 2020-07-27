#!/usr/bin/python
# (C) Copyright NuoDB, Inc. 2020  All Rights Reserved.
#
# Converts nuocmd get stats output from new admin to influx line protocol
# stanzas and uploads them to influx.  Steals liberally from dbutson and dbain's
# prior work.

import fileinput
import re
import requests
import logging
from datetime import datetime
from dateutil import parser
import argparse
import time,sys,os
from metrics_influx import metrics, summary
from urlparse import urlparse

os.environ['TZ'] = 'GMT'

logging.basicConfig(level=logging.INFO,format='%(asctime)s:%(levelname)s %(message)s')
logging.getLogger("requests").setLevel(logging.WARNING)

argparser = argparse.ArgumentParser()
argparser.add_argument("-d", "--db",  dest="db", default="nuodb", help="Influx database name.")
argparser.add_argument("-t", "--tag", dest="tags", action="append", help="Influx extra tag.")
argparser.add_argument("-D", "--debug",dest="debug", action="store_true", default=False, help="Print out extra info.")
argparser.add_argument("-o", "--output", dest="output",
                       help="url to file (file://filename, stdout:) or influx server (http://server:8086)",
                       default="http://influxdb:8086")
argparser.add_argument('files', metavar='FILE', nargs='*', help='files to read, if empty, stdin is used')
args = argparser.parse_args()

# startId -> tag string
tagMap = {}
# startId -> values dictionary
previousValues = {}
# values, we don't clear them so if value doesn't change
values = {}
timestamp = None

influxURL=None

o = urlparse(args.output)
if o.scheme == 'http' or o.scheme == 'https':
    influxURL="%s/write?db=%s&precision=ms" % (args.output,args.db)
elif o.scheme == '' or o.scheme == 'file':
    if o.path == 'stdout':
        _OUTPUT = sys.stdout
    else:
        _OUTPUT = open(o.path,'wb')
elif o.scheme == 'stdout':
    _OUTPUT = sys.stdout

lines = []

def formatTimeStamp(timestr):
    """ return timestr as number of milliseconds since epoch"""
    dt = parser.parse(timestr)
    tstamp = int(time.mktime(dt.timetuple())*1000 + dt.microsecond/1000)
    return tstamp

def output(data):
    if influxURL:
        requests.post(influxURL, data = data)
    elif _OUTPUT:
        print >> _OUTPUT,data

# format monitor values into: metric,<identity tags> <fields> timestamp
def influx_send(values, tags, timestamp):
    ignore = {"NodeType":'',"Hostname":'',"ProcessId":'',"NodeId":'',"Database":'',"Region":'',"ArchiveDirectory":''}

    if tags == None:
        extraTags = ""
        nodetype  = values['NodeType']
        hostname  = values['Hostname']
        processid = values['ProcessId']
        nodeid    = values['NodeId']
        if 'Database' in values:
            extraTags += ",db=%s" % (values['Database'])
        if 'Region' in values:
            extraTags += ",region=%s" % (values['Region'])
        if args.tags:
            extraTags = "," + ",".join(args.tags)
        tags = "host=%s,nodetype=%s,pid=%s,nodeId=%s%s" % (hostname,nodetype,processid,nodeid,extraTags)

    for k in values:
        value_formatter = metrics[k] if k in metrics else None
        if value_formatter:
            rvalues = metrics[k](k,values)
            lines.append("%s,%s %s %s" % (k,tags,rvalues,timestamp))
        elif k not in metrics and k not in ignore:
            # catch all if new metric added
            try:
                rvalues = "raw=%di" % (int(values[k]))
                lines.append("%s,%s %s %s" % (k,tags,rvalues,timestamp))
            except:
                pass

    summary_map = summary(values)
    for key,rvalues in summary_map.iteritems():
        lines.append("%s,%s %s %s" % (key,tags,rvalues,timestamp))

    if len(lines) > 5000:
        output('\n'.join(lines))
        del lines[:]

    return tags

for line in fileinput.input(args.files, openhook=fileinput.hook_compressed):
    startId = -1
    matches = re.findall(r'"(.+?)"', line)

    if len(matches) == 2:
        if matches[0] == "startId":
            assert timestamp != None
            startId = matches[1]
            tags = tagMap[startId] if startId in tagMap else None
            if startId in previousValues:
                previousValues[startId].update(values)
                values = previousValues[startId]
            else:
                # Only happends once on the first occurrance of stats from this startId
                previousValues[startId] = values.copy()
            tags = influx_send(values, tags, timestamp)
            if not startId in tagMap:
                tagMap[startId] = tags
            values = {}
        elif matches[0] == "Time":
            timestamp = formatTimeStamp(matches[1])
        else:
            if args.debug:
                print >> sys.stderr,"%s=%s" % (matches[0], matches[1])
            values[matches[0]] = matches[1]

# make sure to flush any remaining lines
if len(lines) > 0:
    output('\n'.join(lines))
