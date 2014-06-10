from google.appengine.ext import ndb

class Slot(ndb.Model):
  owner = ndb.StringProperty()
  room = ndb.StringProperty(default="4c")  # we have one room only for now
  date = ndb.DateProperty() 
  slot = ndb.IntegerProperty()

