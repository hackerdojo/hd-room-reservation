# Handles a REST api for the backend.

import datetime
import json
import webapp2

from google.appengine.api import users
from google.appengine.ext import ndb

from models import Slot

# Converts iso formatted dates to a date object.
def make_date(date_string):
  elems = date_string.split("-")
  year = int(elems[0])
  month = int(elems[1])
  day = int(elems[2])
  return datetime.date(year, month, day)

# Handler that allows the user to authenticate, thus allowing the same client to
# perform api requests.
class LoginHandler(webapp2.RequestHandler):
  def get(self):
    # First, authenticate with google.
    user = users.get_current_user()
    if not user:
      url = users.create_login_url("/login")
      self.redirect(url)
      # We'll end up back here after they authenticate.
      return

    if "@hackerdojo.com" not in user.email():
      # Not a hackerdojo member.
      self.redirect(users.create_logout_url("/login"))

# Superclass for all API calls.
class ApiHandler(webapp2.RequestHandler):
  # Checks that there is a properly authenticated user.
  def _check_authentication(self):
    user = users.get_current_user()
    if not user:
      self.response.set_status(401)
      return False
    # if "@hackerdojo.com" not in user.email():
    #  self.response.set_status(401)
    #  return False
    return True
  
  # Helper for getting parameters from reqests.
  def _get_parameters(self, *args):
    ret = []
    for arg in args:
      value = self.request.get(arg)
      if not value:
        self.response.out.write("Error: Requires parameters: " + str(args))
        return None
      ret.append(value)
    return ret

# Handler for schedule requests.
class ScheduleHandler(ApiHandler):
  def get(self):
    if not self._check_authentication():
      return
    
    params = self._get_parameters("date", "room")
    if not params:
      return
    date = make_date(params[0])
    room = params[1]
   
    slots = Slot.query(ndb.AND(Slot.date == date, Slot.room == room))
   
    response = []
    for slot in slots:
      # data = {"date": slot.date, "slot": slot.slot, "owner": slot.owner}
      data = {"slot": slot.slot, "owner": slot.owner}

      response.append(data)

    self.response.out.write(json.dumps(response))

# Hander for booking a slot.
class BookingHandler(ApiHandler):
  # The length in hours of one slot.
  slot_length = 0.5
  # The number of hours required between non-consecutive reservations.
  empty_time = 2
  # The number of days someone can book a slot in advance.
  advance_booking = 30

  def post(self):
    if not self._check_authentication():
      return
    
    params = self._get_parameters("slot", "date", "room")
    if not params:
      return
    slot = int(params[0])
    date = make_date(params[1])
    room = params[2]

    # Make sure they're not booking too far in advance.
    advance = date - datetime.datetime.now().date()
    advance = advance.days
    if advance > self.advance_booking:
      self.response.out.write(False)
      return

    # Make sure we're not double-booking.
    if Slot.query(ndb.AND(Slot.date == date, Slot.room == room,
        Slot.slot == slot)).get():
      self.response.out.write(False)
      return

    name = users.get_current_user().nickname()
    name = name.replace(".", " ").title()
   
    # Slots reserved by the same user must be at least 2 hours apart.
    empty = self.empty_time / self.slot_length
    slots = Slot.query(ndb.AND(Slot.date == date, Slot.owner == name,
        Slot.room == room))
    for prop in slots:
      if (abs(int(prop.slot) - slot) != 1 and \
          abs(int(prop.slot) - slot) <= empty):
        self.response.out.write(False)
        return

    slot = Slot(owner = name, slot = slot, date = date, room = room)
    slot.put()

    self.response.out.write(True)

# Handler for removing a reservation on a slot.
class RemoveHandler(ApiHandler):
  def post(self):
    if not self._check_authentication():
      return

    params = self._get_parameters("slot", "date")
    if not params:
      return
    slot = int(params[0])
    date = make_date(params[1])
    
    prop = Slot.query(ndb.AND(Slot.date == date, Slot.slot == slot)).get()
    if prop:
      prop.key.delete()
      self.response.out.write(True)
      return

    self.response.out.write(False)

app = webapp2.WSGIApplication([
    ("/login", LoginHandler),
    ("/api/v1/schedule", ScheduleHandler),
    ("/api/v1/add", BookingHandler),
    ("/api/v1/remove", RemoveHandler),
    ], debug = True)
