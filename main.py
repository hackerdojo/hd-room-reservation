import os
import datetime
import webapp2
import jinja2
from google.appengine.ext import ndb
from google.appengine.api import users

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

#-- Handlers ------------------------------------------------------------------

class HomePage(webapp2.RequestHandler):
  def get(self):
    # Get logged in user.
    user = users.get_current_user()
    
    # If the user is not logged in, ask them to.
    if not user:
      html = '<a href="%s">Sign In</a>' % users.create_login_url('/')
      self.response.write(html)
      return

    # As an example, create and save one slot that starts now.
    slot = Slot(user=user, start=datetime.datetime.now())
    slot.put()
    
    # Load last 10 slots.
    slots = Slot.query().order(-Slot.start).fetch(10)
    
    # Set values to pass to HTML template.
    template_values = {
      'user': user,
      'slots': slots,
    }
    template = JINJA_ENVIRONMENT.get_template('index.html')
    self.response.write(template.render(template_values))

# Route URL Requests to handlers.
app = webapp2.WSGIApplication([
  # Home page
  ('/?', HomePage),
  ], debug=True)

