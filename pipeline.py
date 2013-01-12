import time
import os
import os.path
import functools
import shutil
import glob
import json
import urllib
from distutils.version import StrictVersion

from tornado import gen, ioloop
from tornado.httpclient import AsyncHTTPClient, HTTPRequest

import seesaw
from seesaw.project import *
from seesaw.config import *
from seesaw.item import *
from seesaw.task import *
from seesaw.pipeline import *
from seesaw.externalprocess import *
from seesaw.tracker import *


if StrictVersion(seesaw.__version__) < StrictVersion("0.0.10"):
  raise Exception("This pipeline needs seesaw version 0.0.10 or higher.")


USER_AGENT = "Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US) AppleWebKit/533.20.25 (KHTML, like Gecko) Version/5.0.4 Safari/533.20.27"
VERSION = "20130112.01"

class ConditionalTask(Task):
  def __init__(self, condition_function, inner_task):
    Task.__init__(self, "Conditional")
    self.condition_function = condition_function
    self.inner_task = inner_task
    self.inner_task.on_complete_item += self._inner_task_complete_item
    self.inner_task.on_fail_item += self._inner_task_fail_item

  def enqueue(self, item):
    if self.condition_function(item):
      self.inner_task.enqueue(item)
    else:
      item.log_output("Skipping tasks for this item.")
      self.complete_item(item)

  def _inner_task_complete_item(self, task, item):
    self.complete_item(item)
  
  def _inner_task_fail_item(self, task, item):
    self.fail_item(item)

  def fill_ui_task_list(self, task_list):
    self.inner_task.fill_ui_task_list(task_list)

  def __str__(self):
    return "Conditional(" + str(self.inner_task) + ")"

class PrepareDirectories(SimpleTask):
  def __init__(self):
    SimpleTask.__init__(self, "PrepareDirectories")

  def process(self, item):
    item_name = item["item_name"]
    os.makedirs(item["data_dir"] + "/files")
    item["warc_file_base"] = "punchfork.com-%s-%s" % (item_name, time.strftime("%Y%m%d-%H%M%S"))
    item["zip_file_name"]  = "punchfork.com-%s-%s.zip" % (item_name, time.strftime("%Y%m%d-%H%M%S"))

    open("%(data_dir)s/%(warc_file_base)s.warc.gz" % item, "w").close()
    open("%(data_dir)s/%(zip_file_name)s" % item, "w").close()

class GenerateSeedURL(SimpleTask):
  def __init__(self):
    SimpleTask.__init__(self, "GenerateSeedURL")

  def process(self, item):
    item_name = item["item_name"]
    m = re.match("^date-(.+)$", item_name)
    if m:
      item["punchfork_date"] = True
      item["punchfork_user"] = False
      item["punchfork_seed"] = "http://punchfork.com/api/rc?query=new&size=100&start=%s" % (urllib.quote_plus(m.group(1)))

    m = re.match("^user-(.+)$", item_name)
    if m:
      item["punchfork_date"] = False
      item["punchfork_user"] = True
      item["punchfork_username"] = m.group(1)
      item["punchfork_seed"] = "http://punchfork.com/likes/%s" % m.group(1)

def calculate_item_id(item):
  if item["punchfork_user"]:
    d = {}
    d["username"] = item["punchfork_username"]
    with open("%s/files/punchfork.com/%s" % (item["data_dir"], item["punchfork_username"])) as f:
      m = re.search("<title>([^<]+) \(%s" % item["punchfork_username"], f.read())
      if m:
        d["name"] = m.group(1)
    return d

  else:
    return None


project = Project(
  title = "Punchfork",
  project_html = """
    <img class="project-logo" alt="Punchfork logo" src="http://archiveteam.org/images/4/45/Punchfork_icon.png" />
    <h2>Punchfork <span class="links"><a href="http://punchfork.com/">Website</a> &middot; <a href="http://tracker.archiveteam.org/punchfork/">Leaderboard</a></span></h2>
    <p><i>Punchfork</i> is closing.</p>
  """,
  utc_deadline = datetime.datetime(2013,02,01, 23,59,0)
)

pipeline = Pipeline(
  GetItemFromTracker("http://tracker.archiveteam.org/punchfork", downloader, VERSION),
  PrepareDirectories(),
  GenerateSeedURL(),
  WgetDownload([ "./wget-lua",
      "-U", USER_AGENT,
      "-nv",
      "-o", ItemInterpolation("%(data_dir)s/wget.log"),
      "--lua-script", "punchfork.lua",
      "--no-check-certificate",
      "--directory-prefix", ItemInterpolation("%(data_dir)s/files"),
      "--force-directories",
      "-e", "robots=off",
      "--page-requisites", "--span-hosts",
      "--timeout", "60",
      "--tries", "20",
      "--waitretry", "5",
      "--warc-file", ItemInterpolation("%(data_dir)s/%(warc_file_base)s"),
      "--warc-header", "operator: Archive Team",
      "--warc-header", "punchfork-dld-script-version: " + VERSION,
      "--warc-header", ItemInterpolation("punchfork-item: %(item_name)s"),
      ItemInterpolation("%(punchfork_seed)s")
    ],
    max_tries = 2,
    accept_on_exit_code = [ 0, 3, 4, 6, 8 ],
  ),
  ConditionalTask(lambda item: (item["punchfork_user"]),
    ExternalProcess("ZIP export", [
      "./export-punchfork.py",
      ItemInterpolation("%(punchfork_username)s"),
      ItemInterpolation("%(data_dir)s/%(zip_file_name)s")
    ]),
  ),
  ExternalProcess("User extraction", [
    "./extract-users.sh",
    ItemInterpolation("%(data_dir)s"),
    ItemInterpolation("%(data_dir)s/%(warc_file_base)s.users.txt")
  ]),
  PrepareStatsForTracker(
    defaults = { "downloader": downloader, "version": VERSION },
    file_groups = {
      "warc": [ ItemInterpolation("%(data_dir)s/%(warc_file_base)s.warc.gz") ],
      "zip": [ ItemInterpolation("%(data_dir)s/%(zip_file_name)s") ]
    },
    id_function = calculate_item_id
  ),
  ConditionalTask(lambda item: (item["punchfork_user"]),
    LimitConcurrent(NumberConfigValue(min=1, max=4, default="1", name="shared:rsync_threads", title="Rsync threads", description="The maximum number of concurrent uploads."),
      RsyncUpload(
        target = ConfigInterpolation("fos.textfiles.com::alardland/warrior/punchfork-user/%s/", downloader),
        target_source_path = ItemInterpolation("%(data_dir)s/"),
        files = [
          ItemInterpolation("%(data_dir)s/%(warc_file_base)s.warc.gz"),
          ItemInterpolation("%(data_dir)s/%(zip_file_name)s")
        ],
        extra_args = [
          "--recursive",
          "--partial",
          "--partial-dir", ".rsync-tmp"
        ]
      ),
    ),
  ),
  ConditionalTask(lambda item: (item["punchfork_date"]),
    LimitConcurrent(NumberConfigValue(min=1, max=4, default="1", name="shared:rsync_threads", title="Rsync threads", description="The maximum number of concurrent uploads."),
      RsyncUpload(
        target = ConfigInterpolation("fos.textfiles.com::alardland/warrior/punchfork-date/%s/", downloader),
        target_source_path = ItemInterpolation("%(data_dir)s/"),
        files = [
          ItemInterpolation("%(data_dir)s/%(warc_file_base)s.warc.gz")
        ],
        extra_args = [
          "--recursive",
          "--partial",
          "--partial-dir", ".rsync-tmp"
        ]
      ),
    ),
  ),
  RsyncUpload(
    target = ConfigInterpolation("tracker.archiveteam.org::punchfork-user-lists/%s/", downloader),
    target_source_path = ItemInterpolation("%(data_dir)s/"),
    files = [
      ItemInterpolation("%(data_dir)s/%(warc_file_base)s.users.txt")
    ],
    extra_args = [
      "--recursive"
    ]
  ),
  SendDoneToTracker(
    tracker_url = "http://tracker.archiveteam.org/punchfork",
    stats = ItemValue("stats")
  )
)

