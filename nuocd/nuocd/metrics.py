from xml.etree import ElementTree
from datetime import datetime
import traceback
import time,sys
import nuodb_mgmt

def value(v):
    if str(v):
        return int(v) if v.isdigit() else v
    else:
        return v

def summary(values):
    def get(key):
        return int(values[key]) if key in values else 0

    activeTime = get("ActiveTime")
    deltaTime  = get("Milliseconds")
    idleTime   = get("IdleTime")

    def v(raw):
        rvalues = "raw=%d" % (raw)
        if deltaTime > 0:
            rvalues += ",nthreads=%d" % (int(round(raw/deltaTime)))
            if activeTime > 0:
                multiplier = (deltaTime-idleTime)*1./deltaTime
                rvalues += ",percent=%d" % (int(round(multiplier*raw*100./activeTime)))
                return rvalues

    cpuTime          = get("UserMilliseconds") + get("KernelMilliseconds")
    syncTime         = get("SyncPointWaitTime") + get("StallPointWaitTime")
    syncTime        -= get("PlatformObjectCheckOpenTime") + get("PlatformObjectCheckPopulatedTime") + get("PlatformObjectCheckCompleteTime")
    lockTime         = get("TransactionBlockedTime")
    fetchTime        = get("PlatformObjectCheckOpenTime") + get("PlatformObjectCheckPopulatedTime")
    fetchTime       += get("PlatformObjectCheckCompleteTime") + get("LoadObjectTime")
    commitTime       = get("RemoteCommitTime")
    ntwkSendTime     = get("NodeSocketBufferWriteTime")
    archiveReadTime  = get("ArchiveReadTime")
    archiveWriteTime = get("ArchiveWriteTime") + get("ArchiveFsyncTime") + get("ArchiveDirectoryTime")
    journalWriteTime = get("JournalWriteTime") + get("JournalFsyncTime") + get("JournalDirectoryTime")
    throttleTime     = get("ArchiveSyncThrottleTime") + get("MemoryThrottleTime") + get("WriteThrottleTime")
    throttleTime    += get("ArchiveBandwidthThrottleTime") + get("JournalBandwidthThrottleTime")
    values = {
        "Summary.Active" : v(activeTime),
        "Summary.CPU" : v(cpuTime),
        "Summary.Idle" : v(idleTime),
        "Summary.Sync" : v(syncTime),
        "Summary.Lock" : v(lockTime),
        "Summary.Fetch": v(fetchTime),
        "Summary.Commit": v(commitTime),
        "Summary.NtwkSend":v(ntwkSendTime),
        "Summary.ArchiveRead":v(archiveReadTime),
        "Summary.ArchiveWrite":v(archiveWriteTime),
        "Summary.JournalWrite":v(journalWriteTime),
        "Summary.Throttle":v(throttleTime)
    }
    return values


def MONITOR_COUNT(k,values):
    raw = values[k]
    return "raw=%si" % (raw)

def MONITOR_DELTA(k,values):
    raw = int(values[k])
    rvalues="raw=%di" % (raw)
    if 'Milliseconds' in values:
        ms = int(values['Milliseconds'])
        rate = raw*1000./ms if ms != 0 else 0.
        rvalues += ",rate=%f" % (rate)
    return rvalues

def MONITOR_MILLISECOND(k,values):
    raw = int(values[k])
    rvalues="raw=%di" % (raw)    
    if 'Milliseconds' in values:
        ms = int(values['Milliseconds'])
        value =  raw*1./ms if ms != 0 else 0.
        rvalues+= ",value=%f" % (value)
        if 'NumberCores' in values:
            ncores = int(values['NumberCores'])
            nvalue = value/ncores if ncores != 0 else 0.
            rvalues += ",normvalue=%f" % (nvalue)
                
    return rvalues

def MONITOR_NUMBER(k,values):
    raw = values[k]
    return "raw=%si" % (raw)

MONITOR_IDENTIFIER=None

def MONITOR_PERCENT(k,values):
    raw = values[k]
    rvalues = "raw=%si" % (raw)
    if 'NumberCores' in values:
        ncores = int(values['NumberCores'])
        if ncores != 0:
            value = int(raw)*1./ncores
            bycore= int(raw)*.01
            # norm   -> 0 <-> 100 * ncores
            # ncores -> 0 <-> ncores
            rvalues += ",norm=%f,ncores=%f" % (value,bycore)
            if k == 'PercentCpuTime':
                idle = 100*ncores - int(raw)
                # idle   -> 0 <-> 100 * ncores
                # nidle  -> 0 <-> ncores
                rvalues += ",idle=%di,nidle=%f" % (idle,float(idle)/ncores)
        else:
            # ncores only 0 at disconnect
            rvalues += ",norm=%f,ncores=%f" % (0.,0.)
            if k == 'PercentCpuTime':
                rvalues += ",idle=%di,nidle=%f" % (0.,0.)
    return rvalues

units_mapper = {
    "1" : MONITOR_DELTA,       # most of the COUNT are actually DELTAs
    "2" : MONITOR_MILLISECOND,
    "3" : MONITOR_IDENTIFIER,  # MONITOR_STATE but no current instances of this units
    "4" : MONITOR_NUMBER,
    "5" : MONITOR_PERCENT,
    "6" : MONITOR_IDENTIFIER,
    "7" : MONITOR_DELTA
}

# for each nuodb process 
class Monitor:

    #(ntime,startId,hostname,pid,dbname,timedelta,fromNodeId,total-ototal,name,numStalls,totalTimeStalls,maxStallTime)
 
    def __init__(self,nuodb_process,conn,relative,args):
        self._dbkey     = conn._get_db_password(nuodb_process.db_name)
        self._process   = nuodb_process
        self._fullstate = None
        self._items     = None
        self._interval  = 1
        self.__session = nuodb_mgmt._monitor_process(self._process.address, self._dbkey)

    def execute_query(self):
        xml_msg = next(self.__session)
        if xml_msg.tag == 'Items':
            self._items = {}
            for item in xml_msg.findall('Item'):
                name = item.attrib['name']
                unit = item.attrib['units']
                if unit in units_mapper:
                    self._items[name] = units_mapper[unit]
                else:
                    self._items[name] = None
                    print >> sys.stderr,"WARN: don't know how to handle item %s..." % (name,)
            xml_msg = next(self.__session)

        if xml_msg.tag == 'Status':
            self._interval = 10
            statuses = dict([ (k,value(v)) for k,v in xml_msg.attrib.items() ])
            if self._fullstate is None:
                statuses['Database'] = self._process.db_name
                statuses['Region'] = self._process.region_name
                self._fullstate = statuses
            else:
                self._fullstate.update(statuses)
            self._fullstate['TimeStamp'] = int(round(time.time()*1000))
            outputdata = self.format(self._fullstate)
            self.send(outputdata)

    def send(self,lines):
        for line in lines:
            print line

    def format(self,values):
        # timestamp is in seconds
        timestamp = values['TimeStamp']
        nodetype  = values['NodeType']
        hostname  = values['Hostname']
        processid = values['ProcessId']
        startid   = self._process.start_id
        nodeid    = values['NodeId']
        database  = values['Database']
        region    = "<unknown>"
        if 'Region' in values:
            region    = values['Region']

        header = ["TimeStamp","NodeType","Hostname","ProcessId","NodeId","StartId","Database","Region"]
        tags = "host=%s,nodetype=%s,pid=%s,nodeid=%s,startid=%s,db=%s,region=%s" % (hostname,nodetype,processid,nodeid,
                                                                                    startid,database,region)

        results=[]
        for k in values:
            value_formatter = self._items[k] if k in self._items else None
            if value_formatter:
                rvalues = self._items[k](k,values)
                results.append("%s,%s %s %s000000" % (k,tags,rvalues,timestamp))

        summary_map = summary(values)
        for key,rvalues in summary_map.iteritems():
            results.append("%s,%s %s %s000000" % (key,tags,rvalues,timestamp))
        return results
