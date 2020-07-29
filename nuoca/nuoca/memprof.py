import nuodb_mgmt
from xml.etree import ElementTree
from datetime import datetime
import pprint

"""
<SyncTrace NodeId="1" PID="1313" SampleTime="255193801">
   <Trace AverageStallTime="0" MaxStallTime="42" MinStallTime="0" Name="NoTrace" NumStalls="127107" TotalStallTime="12562" />
   ...
   <Trace AverageStallTime="1" MaxStallTime="74" MinStallTime="1" Name="PlatformObjectMarkComplete" NumLocks="4585118" NumStalls="110" NumUnlocks="4585118" TotalStallTime="192" />
   <Probes>
      <Transaction Duration="26577890078" ID="6194963074" />
      <Transaction Duration="2764147844" ID="5102867202" />
      <Transaction Duration="436200606" ID="6967425282" />
      <Transaction Duration="94011584" ID="5102974466" />
      ...
   </Probes>
</SyncTrace>
"""

# for each nuodb process 
class Monitor:
    def __init__(self,nuodb_process,conn,relative,args):
        self._process = nuodb_process
        self._dbkey = conn._get_db_password(nuodb_process.db_name)
        self._relative = relative
        self._lastnow = None
        self._stalls = (0,{})
        
    def execute_query(self):
        session = None
        try:
            session = nuodb_mgmt._get_authorized_session(self._process.address,self._dbkey, 'Query')
            msg = '<Request Service="Query" Type="Memory"><Memory Verbose="true" Profile="true"/></Request>'
            session.send(msg)
            msg=session.recv()
            now = datetime.now()
            st = ElementTree.fromstring(msg)
            print ElementTree.tostring(st)
            #self.process(now,total,stalls,ototal,ostalls)
            self._lastnow    = now
        finally:
            if session:
                session.close()
        
