#!/usr/bin/env python
import os.path
import random
import re
from time import gmtime, strftime
import sys
import urlparse
import zipfile

import requests
from bs4 import BeautifulSoup



class PunchforkExporter(object):
  USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.97 Safari/537.11"

  def __init__(self, username):
    self._load_templates()

    self.headers = { "User-Agent": self.USER_AGENT,
                     "Referer": "http://punchfork.com/likes/%s/new" % username }

    self._images_cache = {}
    self.data = {}
    self.username = username

  def load_user(self, zipfile):
    self._progress("Downloading user profile... ")
    r = requests.get("http://punchfork.com/%s" % self.username, headers=self.headers)
    r.raise_for_status()
    self._progress("done.\n")

    # parse
    html = BeautifulSoup(r.text, "lxml")
    data = self.data
    data["page_title"] = html.title.string
    marquee_title = html.find(id="marquee-title")
    data["marquee_title_name"] = marquee_title.h1.a.string
    data["marquee_title_avatar"] = marquee_title.span.img["src"]

  def load_recipe_index(self, zipfile):
    self._progress("Downloading recipe index:\n")
    start_date = "2013-12-12T00:00:00"
    recipe_cards = self.recipe_cards = []
    while start_date:
      self._progress("\r - %d cards" % len(recipe_cards))

      r = requests.get("http://punchfork.com/api/rc",
                       params={ "query": "likes/%s/new" % username,
                                "start": start_date,
                                "size": "100",
                                "_": "%0.10f" % random.random() },
                       headers=self.headers)
      r.raise_for_status()

      recipe_cards.extend(r.json["cards"])

      if len(r.json["cards"]) < 100:
        start_date = None
      else:
        start_date = r.json["next"]

    self._progress("\r - Found %d cards.\n" % len(recipe_cards))

    # generate html
    soup = BeautifulSoup(self._index_template, "lxml")
    soup.title.string = self.data["page_title"]
    marquee_title = soup.find(id="marquee-title")
    marquee_title.h1.string = self.data["marquee_title_name"]
    marquee_title.img["src"] = self.image_to_file(self.data["marquee_title_avatar"], zipfile)
    if len(self.recipe_cards) == 1:
      recipe_notice = "%d recipe" % len(self.recipe_cards)
    else:
      recipe_notice = "%d recipes" % len(self.recipe_cards)
    end_marker = soup.find(id="end-marker")
    end_marker.find("div", "notice").string = recipe_notice 
    soup.find("div", "meta").string = "This recipe list was archived on %s." % (strftime("%d %B %Y, %H:%M:%S UTC", gmtime()))


    self._progress("Building index page:\n")
    i = 0
    recipe_cards_div = end_marker.parent
    for recipe_card in self.recipe_cards:
      self._progress("\r - Added %d cards to index." % i)
      i += 1
      card_el = BeautifulSoup(recipe_card, "lxml")
      likes_a = card_el.find("a", "svc")
      likes_span = soup.new_tag("span")
      likes_span["class"] = "metric svc"
      likes_span.string = likes_a.string
      likes_a.replace_with(likes_span)
      for img in card_el.find_all("img"):
        img["src"] = self.image_to_file(img["src"], zipfile)
      a = card_el.find("a")
      a["href"] = "recipe/" + a["href"].split("/")[2] + ".html"
      del a["target"]
      end_marker.insert_before(card_el)
    self._progress("\r - Added %d cards to index.\n" % i)

    zipfile.writestr("%s/index.html" % self.username, soup.prettify(formatter="minimal").encode("utf-8"))

  def load_recipes(self, zipfile):
    self._progress("Downloading recipes:\n")

    i = 0
    for recipe_card in self.recipe_cards:
      self._progress("\r - Saved %d recipes." % i)
      i += 1

      recipe_href = BeautifulSoup(recipe_card, "lxml").div.a["href"]
      recipe_name = recipe_href.split("/")[2]

      r = requests.get("http://punchfork.com/recipe/%s" % recipe_name,
                       headers=self.headers)
      r.raise_for_status()

      # replace some parts
      t = r.text
      soup = BeautifulSoup(re.sub("<script(.|\n)+?</script>", "", t, re.DOTALL), "lxml")
      for tag in soup.find_all("script"):
        tag.extract()
      for tag in soup.find_all("link", rel="stylesheet"):
        tag.extract()
      for tag_id in ("announcement-banner", "action-buttons", "sharing-block", "footer", "fb-root"):
        tag = soup.find(id=tag_id)
        if tag:
          tag.extract()

      who_likes = soup.find("div", id="who-likes")
      if who_likes:
        for tag in who_likes.find_all("div", "tiny-user-card"):
          tag.extract()
      publisher_card = soup.find("div", id="publisher-card")
      if publisher_card:
        for tag in publisher_card.find_all("a", href=re.compile("^/from/")):
          del tag["href"]

      inner_header = soup.find("div", id="inner-header")
      del inner_header.find("a", "logo")["href"]
      for tag in inner_header.find_all("ul", "dropdown-menu"):
        tag.extract()
      for source_a in soup.find_all("a", href=re.compile("^/r\?url=")):
        del source_a["onclick"]
        source_a["href"] = urlparse.parse_qs(urlparse.urlparse(source_a["href"]).query)["url"]
      ul = soup.new_tag("ul") ; ul["class"] = "left dropdown-menu dark"
      li = soup.new_tag("li") ; li["class"] = "menu dropdown-item"
      a  = soup.new_tag("a", href="../index.html")
      a.string = "Back to index"
      li.append(a)
      ul.append(li)
      inner_header.append(ul)

      for img in soup.find_all("img"):
        img["src"] = "../"+self.image_to_file(img["src"], zipfile)
      for img in soup.find_all("link", rel="apple-touch-icon"):
        img["href"] = "../"+self.image_to_file(img["href"], zipfile)
      for img in soup.find_all("link", rel="shortcut icon"):
        img["href"] = "../"+self.image_to_file(img["href"], zipfile)
      for img in soup.find_all("meta", property="og:image"):
        img["content"] = "../"+self.image_to_file(img["content"], zipfile)

      footer = soup.new_tag("div")
      footer["class"] = "footer"
      soup.body.append(footer)

      soup.head.append(soup.new_tag("link", rel="stylesheet", type="text/css", href="../css/punchfork-81HpuHrf7cX.css"))
      new_script_tag = soup.new_tag("script", type="text/javascript", src="../js/punchfork-export.js")
      new_script_tag.string = '// '
      soup.body.append(new_script_tag)

      zipfile.writestr("%s/recipe/%s.html" % (self.username, recipe_name), soup.prettify(formatter="minimal").encode("utf-8"))

    self._progress("\r - Saved %d recipes.\n" % i)

  def copy_assets(self, zipfile):
    for root, dirs, files in os.walk(os.path.join(os.path.abspath(os.path.dirname(__file__)), "templates/css")):
      for name in files:
        zipfile.write(os.path.join(root, name), os.path.join(self.username, "css", name))

    for root, dirs, files in os.walk(os.path.join(os.path.abspath(os.path.dirname(__file__)), "templates/js")):
      for name in files:
        zipfile.write(os.path.join(root, name), os.path.join(self.username, "js", name))

  def image_to_file(self, href, zipfile):
    if re.match("^//", href):
      href = "http:"+href
    if not href in self._images_cache:
      r = requests.get(href, headers=self.headers)
      r.raise_for_status()

      filename = os.path.basename(href)
      zipfile.writestr("%s/img/%s" % (self.username, filename), r.content)
      self._images_cache[href] = "img/%s" % filename

    return self._images_cache[href]



  def _path_to_template(self, template_name):
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), "templates", template_name)

  def _load_templates(self):
    with open(self._path_to_template("index.html")) as f:
      self._index_template = f.read()

  def _progress(self, s):
    sys.stderr.write(s)
    sys.stderr.flush()


if len(sys.argv) < 2:
  sys.stderr.write("No username given.\n")
  sys.exit(1)

username = sys.argv[1]
if len(sys.argv) == 2:
  zipfilename = "%s.zip" % username
else:
  zipfilename = sys.argv[2]

sys.stderr.write("Archiving %s to %s\n" % (username, zipfilename))

zf = zipfile.ZipFile(zipfilename, "w")
pfe = PunchforkExporter(username)
pfe.copy_assets(zf)
pfe.load_user(zf)
pfe.load_recipe_index(zf)
pfe.load_recipes(zf)
zf.close()
sys.stderr.write("Archived %s to %s\n" % (username, zipfilename))

