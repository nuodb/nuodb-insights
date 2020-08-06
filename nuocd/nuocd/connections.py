import nuodb_mgmt
from xml.etree import ElementTree
from datetime import datetime

# for each nuodb process 
class Monitor:

    #(ntime,startId,hostname,pid,dbname,timedelta,fromNodeId,total-ototal,name,numStalls,totalTimeStalls)
    format="%s,%s,%d,%s,%d,%s,%d,%d,%s,%d,%d"
    header="#time,id,startId,host,pid,dbname,timedelta,totalSumStalls,message,numStalls,totalTimeStalls"

    def __init__(self,nuodb_process,conn,relative,args):
        self._process = nuodb_process
        self._dbkey = conn._get_db_password(nuodb_process.db_name)
        self._relative = relative
        self._lastnow = None
        self._stalls = {}
        print Monitor.header

    def execute_query(self):
        session = None
        try:
            session = nuodb_mgmt._get_authorized_session(self._process.address,self._dbkey, 'Query')
            #msg = '<Request Service="Query" Type="QueryConnections"><QueryConnections TopConnections="10"/></Request>'
            msg = '<Request Service="Query" Type="LogQueries"/>'
            session.send(msg)
            msg=session.recv()
            now = datetime.now()
            st = ElementTree.fromstring(msg)
            print ElementTree.tostring(st)
        finally:
            if session:
                session.close()
        
