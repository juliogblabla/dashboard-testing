import re
import urllib2
import xml.etree.ElementTree
import os
import jinja2
import webapp2
import pytz
import logging
import datetime

JINJA = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

class Repository:
  """Reads MTA's service status URL, parses subway data."""

  def __init__(self):
    self.status = 'nodata'
    self.last_success_utc = None
    self.subways = {}

  def clean_text(self, text):
    if not text:
      return ''
    ret = text.replace('&lt;', '<') \
              .replace('&gt;', '>') \
              .replace('&nbsp;', ' ') \
              .replace('\n', '') \
              .replace('<br/>', '')
    ret = re.sub(r'\s+', ' ', ret)
    ret = re.sub(r'[[{](.)[\]}]', r'<span class="line-\1">\1</span>', ret)
    return ret

  def load(self):
    self.status = 'loading'
    url = urllib2.urlopen('http://web.mta.info/status/serviceStatus.txt')
    tree = xml.etree.ElementTree.parse(url)
    root = tree.getroot()
    responsecode = root.find('responsecode').text
    if responsecode != '0':
      self.status = 'error'
      return
    subway = root.find('subway')
    new_subways = {}
    for line in subway.findall('line'):
      name = line.find('name').text
      name = 'NQRW' if name == 'NQR' else name
      new_subways[name] = {
        'status': line.find('status').text.title(),
        'text': self.clean_text(line.find('text').text),
      }
    self.subways = new_subways
    self.status = 'ok'
    self.last_success_utc = datetime.datetime.utcnow()

class SubwayPage(webapp2.RequestHandler):
  """Main page for MTA subway wall dashboard."""

  def maybe_refresh_repo(self):
    app = webapp2.get_app()
    repo = app.registry.get('repo')
    if not repo:
      repo = Repository()
      app.registry['repo'] = repo
    timeout = datetime.timedelta(minutes=10)
    now = datetime.datetime.utcnow()
    if not repo.last_success_utc or now > repo.last_success_utc + timeout:
      try:
        logging.info('Starting repo load, status=%s' % repo.status)
        repo.load()
        logging.info('Successfully finished repo load, status=%s' % repo.status)
      except:
        logging.exception('Could not reload subway status.')
    return repo

  def status_class(self, status):
    return {
          'Good Service': 'good',
          'Delays': 'delays',
        }.get(status, 'work')

  def render_page(self, repo):
    lines = []
    if repo.status == 'ok':
      for i in ['123', '456', '7', 'ACE', 'BDFM', 'G', 'JZ', 'L', 'NQRW', 'S']:
        lines.append({
          'names': i,
          'status': repo.subways[i]['status'],
          'status_class': self.status_class(repo.subways[i]['status']),
          'info_html': repo.subways[i]['text'],
        })

    tz = pytz.timezone('US/Eastern')

    values = {
      'current_time': datetime.datetime.now(tz).strftime('%I:%M %p'),
      'lines': lines,
    }
    template = JINJA.get_template('dashboard.html')
    return template.render(values)

  def get(self):
    repo = self.maybe_refresh_repo()
    self.response.write(self.render_page(repo))

app = webapp2.WSGIApplication([
    ('/', SubwayPage),
], debug=True)
