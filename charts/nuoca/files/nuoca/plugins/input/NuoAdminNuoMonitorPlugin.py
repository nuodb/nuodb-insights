# (C) Copyright NuoDB, Inc. 2017-2018
#
# This source code is licensed under the MIT license found in the LICENSE
# file in the root directory of this source tree.

import logging
import os
import re
import socket
import threading
import time
import datetime

from copy import deepcopy
from nuoca_plugin import NuocaMPInputPlugin
from nuoca_util import nuoca_log

import nuodb_mgmt

# NuoAdminNuoMonitor plugin
#
# NOTE: This is an Alpha version of a NuoCA plugin that can collect NuoDB
# Engine metrics (NuoMon) from the NuoDB new Admin layer (which is a Beta
# feature for NuoDB release 3.2). This NuoCA plugin has minimal testing and
# is expected to change (or be incorporated into the NuoCA NuoMon plugin)
#
# Example NuoAdminNuoMonitor plugin configuration:
#
# - NuoAdminNuoMonitor:
#    description : Collection from internal nuoAdminNuoMonitor tool
#    database_regex_pattern: dbt2
#    api_server: localhost:8888
#    client_key: /opt/nuodb/tls-config/keys/nuocmd.pem
#    server_cert: None
#    server_id: nuoadmin0

class BaseCollector(object):

    def message_received(self, root):
        pass

    def invalid_message(self, message):
        pass

    def closed(self):
        pass


class BaseMetricsCollector(BaseCollector):
  def __init__(self):
    super(BaseMetricsCollector, self).__init__()
    self.__first = True
    self.__process = None

  @property
  def process(self):
    return self.__process

  @process.setter
  def process(self, p):
    self.__process = p

  def __get_item(self, attrs):
    units = ["COUNT", "MILLISECONDS", "STATE",
             "NUMBER", "PERCENT", "IDENTIFIER",
             "DELTA"]
    return {"unit": units[int(attrs['units']) - 1],
            "description": attrs['header']}

  # @trace
  def message_received(self, root):
    def parseStr(x):
      try:
        return int(x)
      except:
        return x

    items = {}
    if root.tag == "Items":
      for child in root:
        items[child.attrib['name']] = self.__get_item(child.attrib)
      items['Database'] = dict(unit="IDENTIFIER", description="Database Name")
      items['Region'] = dict(unit="IDENTIFIER", description="Region Name")
      items['StartId'] = dict(unit="IDENTIFIER", description="Unique Process Identifier")
      self.onStart(items)
      return None
    elif root.tag == 'Status':
      new_values = dict([(k, parseStr(v)) for k, v in root.attrib.iteritems()])
      if self.__first:
        new_values['Database'] = self.process.db_name
        new_values['Region'] = self.process.region_name
        new_values['StartId'] = self.process.start_id
        new_values['TimeStamp'] = int(time.time() * 1000.0)
        self.__first = False
      else:
        expected_change = new_values['Milliseconds']
        expected_time = self.values['TimeStamp'] + expected_change
        now_time      = int(time.time() * 1000.0)
        drift_time    = now_time - expected_time
        new_values['Time.Received'] = now_time
        new_values['Time.Drift'] = drift_time
        # use now time if within 5 ms toleration or it looks like
        # we missed a time window.  This should allow for a slow
        # buffer read by nuoca since TimeStamp is done in nuoca
        # instead of in engine.  We can only guess at what engine
        # time is.
        if drift_time > expected_change or abs(drift_time) < 5:
          new_values['TimeStamp' ] = now_time
        else:
          new_values['TimeStamp' ] = expected_time
      self.onChange(new_values)
      return None

  def closed(self):
    self.onEnd()
    pass


class MetricsCollector(BaseMetricsCollector):
  """ Base class for metrics collection.
  Remembers previous values"""

  def __init__(self):
    super(MetricsCollector, self).__init__()
    self.__metrics = {}
    self.__values = {}
    pass

  @property
  def metrics(self):
    return self.__metrics

  @property
  def values(self):
    return self.__values

  def init(self, args):
    return self

  def onStart(self, metrics):
    """ remembers metrics  """
    self.__metrics = metrics

  def onChange(self, metrics):
    """ remembers previous values """
    self.__values.update(metrics)

  def onEnd(self):
    """ zero all values """
    zeroMetrics = {}
    for k, v in self.__values.iteritems():
      if v != 0 and type(v) is int:
        zeroMetrics[k] = 0
    zeroMetrics['TimeStamp'] = int(time.time() * 1000.0)
    self.onChange(zeroMetrics)
    pass



class NuoAdminNuoMonMessageConsumer(object):
  """ NuoAdminNuoMonMessageConsumer"""

  _conn = None
  _nuo_monitor_obj = None

  def __init__(self, conn, nuo_monitor_obj):
    self._conn = conn
    self._nuo_monitor_obj = nuo_monitor_obj
    self._process_metrics_dict = {}

  def get_stats(self, db_name=None, start_id=None, server_id=None):
    while self._nuo_monitor_obj._enabled:
      try:
        for process_msg in self._get_messages(None, db_name,
                                              start_id, server_id):
          if process_msg and 'msg' in process_msg:
            self._nuo_monitor_obj.nuoAdminNuoMonitor_collect_queue.append(
              deepcopy(process_msg['msg']))
      except Exception as e:
        nuoca_log(logging.ERROR, "Exception in NuoAdminNuoMonMessage"
                                 "ConsumerNuoAdminNuoMon.get_stats: %s"
                  % str(e))
      time.sleep(10)

  def _get_messages(self, log_options, db_name, start_id, server_id,
                    include_process=False):

    # message generator is for a single process if `start_id` is specified;
    # otherwise, it is aggregated
    if start_id is not None:
      msg_stream = self._conn.monitor_process(start_id, log_options)
    else:
      msg_stream = self._conn.monitor_database(db_name, log_options,
                                              keep_open=True)
    # filter messages by name based on whether we are streaming stats or
    # log messages
    message_name = 'Status' if log_options is None else 'LogMessage'
    for process, xml_message in msg_stream:
      if server_id:
        if process.server_id != server_id:
          continue
      if process.start_id not in self._process_metrics_dict:
        mc = MetricsCollector()
        self._process_metrics_dict[process.start_id] = mc
        mc.process = process
      else:
        mc = self._process_metrics_dict[process.start_id]
      mc.message_received(xml_message)
      # shouldn't we include mc.metrics also. They are redundant but
      # currently there is no means to pass this info to output plugin
      # and might be needed for formatting data.
      items = mc.values
      json_msg = items
      if len(json_msg) != 0:
        # add timestamp to message attributes; TODO: in the future, we
        # may want to include timestamp on the sending side
        if 'Time' not in json_msg:
          json_msg['Time'] = self._get_timestamp()
        # combine process and message; if `include_process`, return all
        # process attributes; otherwise just return start ID

        if include_process:
          process._dict['msg'] = json_msg
          yield process
        else:
          yield dict(startId=process.start_id, msg=json_msg)


  @staticmethod
  def _get_timestamp(time_sec=None):
    if time_sec is None:
      time_sec = time.time()
    dt = datetime.datetime.fromtimestamp(time_sec)
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')


class NuoAdminNuoMonitorPlugin(NuocaMPInputPlugin):

  DEFAULT_API_SERVER = 'localhost:8888'

  def __init__(self, parent_pipe):
    super(NuoAdminNuoMonitorPlugin, self).__init__(parent_pipe, 'NuoAdminNuoMon')
    self._config = None
    self._nuocaCollectionName = None
    self._api_server = NuoAdminNuoMonitorPlugin.DEFAULT_API_SERVER
    self._server_id = None
    self._client_key = None
    self._server_cert = None
    self._enabled = False
    self._numon_handler_ready = False
    self._domain = None
    self._domain_metrics = None
    self._domain_metrics_host = None
    self._database_regex_pattern = '.*'
    self._host_uuid_shortname = False
    self._thread = None
    self._nuoAdminNuoMonitor_collect_queue = []
    self._collection_interval = 30

  def _get_admin_conn(self):
    client_key = self._client_key
    if client_key is not None and ',' in client_key:
      client_key = client_key.split(',')
      if len(client_key) != 2:
        raise ValueError(
          'Expected at most two tokens for --client-key')
    server_cert = self._server_cert
    api_server = self._api_server
    if (not api_server.startswith('http://') and
          not api_server.startswith('https://')):  # noqa
      if client_key is None and server_cert is None:
        api_server = 'http://' + api_server
      else:
        api_server = 'https://' + api_server
    verify = server_cert
    if not verify:
      verify = False

    return nuodb_mgmt.AdminConnection(api_server, client_key, verify)

  def wait_for_terminate(self):
    if self._domain:
      self._domain.waitForTerminate()

  @property
  def nuoAdminNuoMonitor_collect_queue(self):
    return self._nuoAdminNuoMonitor_collect_queue

  def _NuoAdminNuoMon_handler_thread(self):
    self._numon_handler_ready = True
    self._domain_metrics.get_stats(server_id=self._server_id)

  def startup_NuoAdminNuoMon(self):
    try:
      self._numon_handler_ready = False
      self._conn = self._get_admin_conn()
      self._enabled = True
      self._domain_metrics = NuoAdminNuoMonMessageConsumer(self._conn, self)
      self._thread = threading.Thread(target=self._NuoAdminNuoMon_handler_thread)
      self._thread.daemon = True
      self._thread.start()
      try_count = 0
      while not self._numon_handler_ready and try_count < 5:
        try_count += 1
        time.sleep(1)
      return self._numon_handler_ready
    except Exception as e:
      nuoca_log(logging.ERROR, "NuoAdminNuoMon Startup error: %s" % str(e))
      return False

  def startup(self, config=None):
    try:
      self._config = config

      # Validate the configuration.
      required_config_items = ['api_server']
      if not self.has_required_config_items(config, required_config_items):
        return False

      # Don't reveal the domain password in the NuoCA log file.
      display_config = {}
      display_config.update(config)
      display_config['domain_password'] = ''
      nuoca_log(logging.INFO, "NuoAdminNuoMon: plugin config: %s" %
                str(display_config))

      self._api_server = os.path.expandvars(config['api_server'])
      if 'server_id' in config:
        self._server_id = os.path.expandvars(config['server_id'])
      if 'client_key' in config:
        self._client_key = os.path.expandvars(config['client_key'])
      if 'server_cert' in config:
        self._server_cert = os.path.expandvars(config['server_cert'])
      if 'nuocaCollectionName' in config:
        self._nuocaCollectionName = config['nuocaCollectionName']
      if 'domain_metrics_host' in config:
        self._domain_metrics_host = os.path.expandvars(config['domain_metrics_host'])
        if self._domain_metrics_host == 'localhost':
          self._domain_metrics_host = socket.gethostname()
      if 'database_regex_pattern' in config:
        self._database_regex_pattern = config['database_regex_pattern']
      if 'host_uuid_shortname' in config:
        self._host_uuid_shortname = config['host_uuid_shortname']
      self.startup_NuoAdminNuoMon()
      return self._numon_handler_ready
    except Exception as e:
      nuoca_log(logging.ERROR, "NuoAdminNuoMon Plugin Startup error: %s" % str(e))
      return False

  def shutdown(self):
    self._enabled = False
    pass

  def collect(self, collection_interval):
    uuid_hostname_regex = \
      '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-'
    rval = None
    self._collection_interval = collection_interval
    try:
      nuoca_log(logging.DEBUG, "NuoAdminNuoMon: collect()")
      base_values = super(NuoAdminNuoMonitorPlugin, self).collect(collection_interval)
      collection_count = len(self._nuoAdminNuoMonitor_collect_queue)
      nuoca_log(logging.DEBUG, "NuoAdminNuoMon: collection_count %s" %
                str(collection_count))
      if not collection_count:
        return rval

      rval = []
      for i in range(collection_count):
        collected_dict = self._nuoAdminNuoMonitor_collect_queue.pop(0)
        if self._domain_metrics_host and 'Hostname' in collected_dict:
          if collected_dict['Hostname'] != self._domain_metrics_host:
            continue
        if self._nuocaCollectionName:
          collected_dict['nuocaCollectionName'] = self._nuocaCollectionName
        if 'Database' in collected_dict:
          m = re.search(self._database_regex_pattern, collected_dict['Database'])
          if m:
            if self._host_uuid_shortname:
              m2 = re.search(uuid_hostname_regex, collected_dict['Hostname'])
              if m2:
                shortid = collected_dict['Hostname'][37:]
                if 'NodeType' in collected_dict:
                  if collected_dict['NodeType'] == 'Transaction':
                    shortid += "(TE)"
                  elif collected_dict['NodeType'] == 'Storage':
                    shortid += "(SM)"
                shortid_with_pid = shortid + str(collected_dict['ProcessId'])
                collected_dict['HostShortID'] = shortid
                collected_dict['HostShortIDwithPID'] = shortid_with_pid
            rval.append(collected_dict)
        else:
          rval.append(collected_dict)

    except Exception as e:
      nuoca_log(logging.ERROR, str(e))
    return rval
