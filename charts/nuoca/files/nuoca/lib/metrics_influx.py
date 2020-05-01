from contextlib import closing
try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO

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

def MONITOR_MILLISECONDS(k,values):
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

def summary(values):
    # from nuodbmgr
    def get(key):
        return int(values[key]) if key in values else 0

    activeTime = get("ActiveTime")
    deltaTime = get("Milliseconds")
    idleTime  = get("IdleTime")

    def v(raw):
        rvalues = "raw=%d" % (raw)
        if deltaTime > 0:
            rvalues += ",nthreads=%d" % (int(round(raw/deltaTime)))
            if activeTime > 0:
                multiplier = (deltaTime-idleTime)*1./deltaTime
                rvalues += ",percent=%d" % (int(round(multiplier*raw*100./activeTime)))
        return rvalues

    cpuTime   = get("UserMilliseconds") + get("KernelMilliseconds")
    syncTime  = get("SyncPointWaitTime") + get("StallPointWaitTime")
    syncTime -= get("PlatformObjectCheckOpenTime") + get("PlatformObjectCheckPopulatedTime") + get("PlatformObjectCheckCompleteTime")
    lockTime  = get("TransactionBlockedTime")
    fetchTime = get("PlatformObjectCheckOpenTime") + get("PlatformObjectCheckPopulatedTime") + get("PlatformObjectCheckCompleteTime") + get("LoadObjectTime")
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


metrics = {
    "Objects"                                     :     MONITOR_COUNT,
    "PurgedObjects"                               :     MONITOR_COUNT,
    "ObjectsCreated"                              :     MONITOR_DELTA,
    "ObjectsSaved"                                :     MONITOR_DELTA,
    "ObjectsImported"                             :     MONITOR_DELTA,
    "ObjectsExported"                             :     MONITOR_DELTA,
    "ObjectsLoaded"                               :     MONITOR_DELTA,
    "ObjectsReloaded"                             :     MONITOR_DELTA,
    "ObjectsPurged"                               :     MONITOR_DELTA,
    "ObjectsDropped"                              :     MONITOR_DELTA,
    "ObjectsDroppedPurged"                        :     MONITOR_DELTA,
    "ObjectsDeleted"                              :     MONITOR_DELTA,
    "ObjectsRequested"                            :     MONITOR_DELTA,
    "ObjectsBounced"                              :     MONITOR_DELTA,
    "Commits"                                     :     MONITOR_DELTA,
    "Rollbacks"                                   :     MONITOR_DELTA,
    "Inserts"                                     :     MONITOR_DELTA,
    "Updates"                                     :     MONITOR_DELTA,
    "Deletes"                                     :     MONITOR_DELTA,
    "Stalls"                                      :     MONITOR_DELTA,
    "SqlMsgs"                                     :     MONITOR_DELTA,
    "SqlListenerSqlProcTime"                      :     MONITOR_MILLISECONDS,
    "SqlListenerThrottleTime"                     :     MONITOR_MILLISECONDS,
    "SqlListenerIdleTime"                         :     MONITOR_MILLISECONDS,
    "SqlListenerStallTime"                        :     MONITOR_MILLISECONDS,
    "SqlListenerContextSwitches"                  :     MONITOR_DELTA,
    "NodePingTime"                                :     MONITOR_MILLISECONDS,
    "NodeApplyPingTime"                           :     MONITOR_MILLISECONDS,
    "NodePostMethodTime"                          :     MONITOR_MILLISECONDS,
    "IdManagerBlockingStallCount"                 :     MONITOR_DELTA,
    "IdManagerNonBlockingStallCount"              :     MONITOR_DELTA,
    "PendingUpdateStallCount"                     :     MONITOR_DELTA,
    "PlatformCatalogStallCount"                   :     MONITOR_DELTA,
    "PlatformObjectCheckOpenTime"                 :     MONITOR_MILLISECONDS,
    "PlatformObjectCheckPopulatedTime"            :     MONITOR_MILLISECONDS,
    "PlatformObjectCheckCompleteTime"             :     MONITOR_MILLISECONDS,
    "PlatformObjectCheckAcknowledgedTime"         :     MONITOR_MILLISECONDS,
    "PlatformObjectCheckChairmanAcknowledgedTime" :     MONITOR_MILLISECONDS,
    "CoordinatedBroadcastWaitTime"                :     MONITOR_MILLISECONDS,
    "TableIndexBuildManagerWaitTime"              :     MONITOR_MILLISECONDS,
    "StallPointWaitTime"                          :     MONITOR_MILLISECONDS,
    "SyncPointWaitTime"                           :     MONITOR_MILLISECONDS,
    "TransactionBlockedTime"                      :     MONITOR_MILLISECONDS,
    "PendingInsertWaitTime"                       :     MONITOR_MILLISECONDS,
    "PendingUpdateWaitTime"                       :     MONITOR_MILLISECONDS,
    "MessagesReceived"                            :     MONITOR_DELTA,
    "ReplicationMessagesReceived"                 :     MONITOR_DELTA,
    "MessagesSent"                                :     MONITOR_DELTA,
    "PacketsReceived"                             :     MONITOR_DELTA,
    "PacketsSent"                                 :     MONITOR_DELTA,
    "AdminReceived"                               :     MONITOR_DELTA,
    "AdminSent"                                   :     MONITOR_DELTA,
    "ClientReceived"                              :     MONITOR_DELTA,
    "ClientSent"                                  :     MONITOR_DELTA,
    "ServerReceived"                              :     MONITOR_DELTA,
    "ServerSent"                                  :     MONITOR_DELTA,
    "BytesReceived"                               :     MONITOR_DELTA,
    "BytesSent"                                   :     MONITOR_DELTA,
    "BytesBuffered"                               :     MONITOR_DELTA,
    "DiskWritten"                                 :     MONITOR_COUNT,
    "DiskReadGeneral"                             :     MONITOR_COUNT,
    "DiskReadHotCopy"                             :     MONITOR_COUNT,
    "HeapAllocated"                               :     MONITOR_NUMBER,
    "HeapActive"                                  :     MONITOR_NUMBER,
    "HeapMapped"                                  :     MONITOR_NUMBER,
    "HeapResident"                                :     MONITOR_NUMBER,
    "Memory"                                      :     MONITOR_NUMBER,
    "PageFaults"                                  :     MONITOR_COUNT,
    "PageFaultsMinor"                             :     MONITOR_COUNT,
    "ArchiveQueue"                                :     MONITOR_COUNT,
    "LogMsgs"                                     :     MONITOR_COUNT,
    "JrnlWrites"                                  :     MONITOR_COUNT,
    "JrnlBytes"                                   :     MONITOR_COUNT,
    "JournalQueue"                                :     MONITOR_COUNT,
    "RefactorTXQueueTime"                         :     MONITOR_MILLISECONDS,
    "NodeSocketBufferWriteTime"                   :     MONITOR_MILLISECONDS,
    "MessageSequencerSortTime"                    :     MONITOR_MILLISECONDS,
    "MessageSequencerMergeTime"                   :     MONITOR_MILLISECONDS,
    "BroadcastTime"                               :     MONITOR_MILLISECONDS,
    "NonChairSplitTime"                           :     MONITOR_MILLISECONDS,
    "WaitForSplitTime"                            :     MONITOR_MILLISECONDS,
    "NumSplits"                                   :     MONITOR_DELTA,
    "ArchiveBufferedBytes"                        :     MONITOR_DELTA,
    "Milliseconds"                                :     MONITOR_MILLISECONDS,
    "UserMilliseconds"                            :     MONITOR_MILLISECONDS,
    "KernelMilliseconds"                          :     MONITOR_MILLISECONDS,
    "NumberCores"                                 :     MONITOR_NUMBER,
    "Hostname"                                    :     MONITOR_IDENTIFIER,
    "NodeType"                                    :     MONITOR_IDENTIFIER,
    "NodeState"                                   :     MONITOR_IDENTIFIER,
    "ArchiveDirectory"                            :     MONITOR_IDENTIFIER,
    "PercentUserTime"                             :     MONITOR_PERCENT,
    "PercentSystemTime"                           :     MONITOR_PERCENT,
    "PercentCpuTime"                              :     MONITOR_PERCENT,
    "EffectiveVersion"                            :     MONITOR_NUMBER,
    "ActualVersion"                               :     MONITOR_NUMBER,
    "ProcessId"                                   :     MONITOR_NUMBER,
    "NodeId"                                      :     MONITOR_NUMBER,
    "ClientCncts"                                 :     MONITOR_NUMBER,
    "CurrentCommittedTransactions"                :     MONITOR_NUMBER,
    "CurrentActiveTransactions"                   :     MONITOR_NUMBER,
    "CurrentPurgedTransactions"                   :     MONITOR_NUMBER,
    "OldestActiveTransaction"                     :     MONITOR_NUMBER,
    "OldestCommittedTransaction"                  :     MONITOR_NUMBER,
    "SnapshotAlbumsClosed"                        :     MONITOR_DELTA,
    "SnapshotAlbumsClosedForGC"                   :     MONITOR_DELTA,
    "SnapshotAlbumTime"                           :     MONITOR_NUMBER,
    "SnapshotAlbumSize"                           :     MONITOR_NUMBER,
    "SendQueueSize"                               :     MONITOR_NUMBER,
    "SendSortingQueueSize"                        :     MONITOR_NUMBER,
    "SocketBufferBytes"                           :     MONITOR_NUMBER,
    "RemoteCommitTime"                            :     MONITOR_MILLISECONDS,
    "IdleTime"                                    :     MONITOR_MILLISECONDS,
    "ActiveTime"                                  :     MONITOR_MILLISECONDS,
    "ClientThreadBacklog"                         :     MONITOR_MILLISECONDS,
    "AtomProcessingThreadBacklog"                 :     MONITOR_MILLISECONDS,
    "HTTPProcessingThreadBacklog"                 :     MONITOR_MILLISECONDS,
    "ArchiveReadTime"                             :     MONITOR_MILLISECONDS,
    "ArchiveWriteTime"                            :     MONITOR_MILLISECONDS,
    "ArchiveFsyncTime"                            :     MONITOR_MILLISECONDS,
    "ArchiveDirectoryTime"                        :     MONITOR_MILLISECONDS,
    "JournalReadTime"                             :     MONITOR_MILLISECONDS,
    "JournalWriteTime"                            :     MONITOR_MILLISECONDS,
    "JournalFsyncTime"                            :     MONITOR_MILLISECONDS,
    "JournalDirectoryTime"                        :     MONITOR_MILLISECONDS,
    "BackupReadTime"                              :     MONITOR_MILLISECONDS,
    "BackupWriteTime"                             :     MONITOR_MILLISECONDS,
    "BackupFsyncTime"                             :     MONITOR_MILLISECONDS,
    "BackupDirectoryTime"                         :     MONITOR_MILLISECONDS,
    "SpillFileReadTime"                           :     MONITOR_MILLISECONDS,
    "SpillFileWriteTime"                          :     MONITOR_MILLISECONDS,
    "SpillFileDirectoryTime"                      :     MONITOR_MILLISECONDS,
    "MiscellaneousReadTime"                       :     MONITOR_MILLISECONDS,
    "MiscellaneousWriteTime"                      :     MONITOR_MILLISECONDS,
    "MiscellaneousDirectoryTime"                  :     MONITOR_MILLISECONDS,
    "LoadObjectTime"                              :     MONITOR_MILLISECONDS,
    "ArchiveSyncThrottleTime"                     :     MONITOR_MILLISECONDS,
    "MemoryThrottleTime"                          :     MONITOR_MILLISECONDS,
    "PruneAtomsThrottleTime"                      :     MONITOR_MILLISECONDS,
    "ArchiveBandwidthThrottleTime"                :     MONITOR_MILLISECONDS,
    "JournalBandwidthThrottleTime"                :     MONITOR_MILLISECONDS,
    "CreatePlatformRecordsTime"                   :     MONITOR_MILLISECONDS,
    "PendingEventsCommitTime"                     :     MONITOR_MILLISECONDS,
    "DependentCommitWaits"                        :     MONITOR_NUMBER,
    "ObjectFootprint"                             :     MONITOR_NUMBER,
    "WriteLoadLevel"                              :     MONITOR_NUMBER,
    "WriteThrottleTime"                           :     MONITOR_MILLISECONDS,
    "LocalCommitOrderTime"                        :     MONITOR_MILLISECONDS,
    "CheckCompleteOptimized"                      :     MONITOR_DELTA,
    "CheckCompleteFull"                           :     MONITOR_DELTA,
    "ChairmanMigration"                           :     MONITOR_DELTA,
    "CycleTime"                                   :     MONITOR_MILLISECONDS,
    "RecordsGCTime"                               :     MONITOR_MILLISECONDS,
    "JournalAge"                                  :     MONITOR_NUMBER,
    "JournalCheckpointAge"                        :     MONITOR_NUMBER,
    "JournalSize"                                 :     MONITOR_NUMBER,
    "PendingMessages"                             :     MONITOR_COUNT,
    "ArchiveReadQueueLow"                         :     MONITOR_COUNT,
    "ArchiveReadQueueMedium"                      :     MONITOR_COUNT,
    "ArchiveReadQueueHigh"                        :     MONITOR_COUNT,
    "MutationsArchivedMasterCatalog"              :     MONITOR_COUNT,
    "MutationsArchivedTransactionManager"         :     MONITOR_COUNT,
    "MutationsArchivedTable"                      :     MONITOR_COUNT,
    "MutationsArchivedRecords"                    :     MONITOR_COUNT,
    "MutationsArchivedData"                       :     MONITOR_COUNT,
    "MutationsArchivedIndex"                      :     MONITOR_COUNT,
    "MutationsArchivedDatabase"                   :     MONITOR_COUNT,
    "MutationsArchivedSchema"                     :     MONITOR_COUNT,
    "MutationsArchivedCatalog"                    :     MONITOR_COUNT,
    "MutationsArchivedBlobs"                      :     MONITOR_COUNT,
    "MutationsArchivedSequence"                   :     MONITOR_COUNT,
    "MutationsArchived"                           :     MONITOR_NUMBER,
    "SyncCurrentStorageGroup"                     :     MONITOR_NUMBER,
    "SyncCurrentTableMigration"                   :     MONITOR_NUMBER,
    "SyncTotalCatalogs"                           :     MONITOR_COUNT,
    "SyncCatalogsStarted"                         :     MONITOR_COUNT,
    "SyncTotalAtoms"                              :     MONITOR_COUNT,
    "SyncAtomsUpToDate"                           :     MONITOR_DELTA,
    "SyncAtomsCopied"                             :     MONITOR_DELTA,
    "SyncAtomBytesCopied"                         :     MONITOR_COUNT
}

def format(values):
    # metric,<identity tags> <fields> timestamp
    if 'TimeStamp' not in values:
        return
    
    timestamp = values['TimeStamp']
    # timestamp is in milliseconds -> nanoseconds
    timestamp = int(timestamp*1000000)
    nodetype  = values['NodeType']
    hostname  = values['Hostname']
    processid = values['ProcessId']
    nodeid    = values['NodeId']
    database  = values['Database']
    region    = "<unknown>"
    if 'Region' in values:
        region    = values['Region']
    startid   = values['StartId'] if 'StartId' in values else processid

    header = ["TimeStamp","NodeType","Hostname","ProcessId","StartId","NodeId","Database","Region"]
    tags = "host=%s,nodetype=%s,pid=%s,nodeid=%s,startid=%s,db=%s,region=%s" % (hostname,nodetype,processid,nodeid,startid,database,region)

    with closing(StringIO()) as buffer:
        for k in values:
            value_formatter = metrics[k] if k in metrics else None
            if value_formatter:
                rvalues = metrics[k](k,values)
                print >> buffer,"%s,%s %s %s" % (k,tags,rvalues,timestamp)
            elif k not in metrics and k not in header:
                # catch all if new metric added
                try:
                    rvalues = "raw=%di" % (int(values[k]))
                    print >> buffer,"%s,%s %s %s" % (k,tags,rvalues,timestamp)
                except:
                    pass
        summary_map = summary(values)
        for key,rvalues in summary_map.iteritems():
            print >> buffer,"%s,%s %s %s" % (key,tags,rvalues,timestamp)
        toinflux = buffer.getvalue()

    return ("text/plain; charset=us-ascii", toinflux)
