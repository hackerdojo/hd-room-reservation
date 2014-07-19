# Handles a REST api for the backend.

import datetime
import logging
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

# Converts a date object to YYYY-MM-DD
def convert_date_to_string(dateObj):
  dateString = str(dateObj.year) + "-" + str(dateObj.month) + "-" + str(dateObj.day)
  return dateString


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

    logging.info("User %s logged in." % (user.nickname()))
    if "@hackerdojo.com" not in user.email():
      # Not a hackerdojo member.
      self.redirect(users.create_logout_url("/login"))
    else:
      self.redirect("/")

# Shortcut for logging out.
class LogoutHandler(webapp2.RequestHandler):
  def get(self):
    url = users.create_logout_url("/")
    self.redirect(url)

# Superclass for all API calls.
class ApiHandler(webapp2.RequestHandler):
  # Checks that there is a properly authenticated user.
  def _check_authentication(self):
    user = users.get_current_user()
    logging.info("User: " + str(user))
    if not user:
      self.response.set_status(401)
      return False
    if "@hackerdojo.com" not in user.email():
      self.response.set_status(401)
      return False
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

    logging.debug("Got parameters: %s." % (str(ret)))
    return ret

  # Gets the full name of the user.
  def _get_name(self):
    name = users.get_current_user().nickname()
    name = name.replace(".", " ").title()
    return name

  # Find booked slots that are on the edges of blocks of booked slots.
  # Props is a query object.
  def _find_block_edges(self, props):
    props = props.order(Slot.slot).fetch()

    block_edges = []
    block_started = False

    for prop in props:
      # Non-contiguous.
      if (not block_edges or prop.slot != block_edges[-1] + 1):
        if block_started:
          # If we have a singleton block, we just duplicate it at the end.
          block_edges.append(block_edges[-1])

        # The beginning of a new block.
        block_edges.append(prop.slot)
        block_started = True
      
      # Contiguous.
      else:
        if block_started:
          block_started = False
          block_edges.append(prop.slot)
        else:
          block_edges[-1] = prop.slot

    logging.info("Block edges: %s" % (str(block_edges)))
    return block_edges

  # Allows a request write its status.
  def _exit_handler(self, error = None):
    response = {}
    if error:
      response["status"] = False
      response["message"] = error

      logging.warning(error)
    else:
      response["status"] = True

    self.response.out.write(json.dumps(response))

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
      dateParam = convert_date_to_string(slot.date)
      data = {"date": dateParam, "slot": slot.slot, "owner": slot.owner}
      # data = {"slot": slot.slot, "owner": slot.owner}

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
  # The maximum amount of consecutive slots someone can book.
  max_slots = 4

  def get(self):
    self.post()

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
      self._exit_handler("User booked too far in advance.")
      return

    # Make sure we're not double-booking.
    if Slot.query(ndb.AND(Slot.date == date, Slot.room == room,
        Slot.slot == slot)).get():
      self._exit_handler("User double-booked slot %d." % (slot))
      return

    name = self._get_name()
       
    # Slots reserved by the same user must be at least 2 hours apart.
    empty = self.empty_time / self.slot_length
    slots = Slot.query(ndb.AND(Slot.date == date, Slot.owner == name,
        Slot.room == room))

    block_edges = self._find_block_edges(slots)

    # Make sure we're not booking too large a block.
    failed = False
    for i in range(0, len(block_edges)):
      edge = block_edges[i]
      if i % 2 != 0:
        # Rising edge.
        if edge - slot == 1:
          if block_edges[i + 1] - slot >= self.max_slots:
            failed = True
        else:
          # Falling edge.
          if slot - block_edges[i - 1] >= self.max_slots:
            failed = True

    if failed:
      self._exit_handler("User cannot book this many slots.")
      return

    # Only worth doing this if there are other slots booked.
    if len(block_edges) != 0:
      # Find the edges that are closest to our slot and get rid of everything
      # else.
      block_edges.append(slot)
      block_edges.sort()
      position = block_edges.index(slot)
      if position == 0:
        # This is a special case.
        block_edges = [block_edges[1]]
      else:
        block_edges = block_edges[(position - 1):]
        block_edges = block_edges[:3]
        block_edges.remove(slot)
      
      for booked_slot in block_edges:
        logging.info("Booked slot: %d." % (booked_slot))
        if (abs(int(booked_slot) - slot) != 1 and \
            abs(int(booked_slot) - slot) <= empty):
          self._exit_handler("User did not leave enough space between blocks.")
          return

    slot = Slot(owner = name, slot = slot, date = date, room = room)
    slot.put()
    logging.info("Saved slot.")

    self._exit_handler()

# Handler for removing a reservation on a slot.
class RemoveHandler(ApiHandler):
  def get(self):
    self.post()

  def post(self):
    if not self._check_authentication():
      return

    params = self._get_parameters("slot", "date")
    if not params:
      return
    slot = int(params[0])
    date = make_date(params[1])
    
    name = self._get_name()

    # Find the room we're looking for.
    to_delete = Slot.query(ndb.AND(Slot.date == date, Slot.slot == slot)).get()
    if not to_delete:
      self._exit_handler("Slot not reserved.")
      return
    room = to_delete.room

    props = Slot.query(ndb.AND(Slot.date == date, Slot.owner == name,
        Slot.room == room))
    block_edges = self._find_block_edges(props)
    
    if to_delete.slot not in block_edges:
      self._exit_handler("Cannot delete slot in middle of block.")
      return
      
    to_delete.key.delete()
    logging.info("Deleted slot.")

    self._exit_handler()
    return

app = webapp2.WSGIApplication([
    ("/login", LoginHandler),
    ("/logout", LogoutHandler),
    ("/api/v1/schedule", ScheduleHandler),
    ("/api/v1/add", BookingHandler),
    ("/api/v1/remove", RemoveHandler),
    ], debug = True)
