from math import *
from os.path import *
import json, sys

class user_manager:
    def __init__( self, db_connection ):
        self.db = db_connection
    
    def ProcessUser(self, user):
        l = len(user.name)
        O = user.email.split("@")
        if user.is_active == True:
            if user.age>18:
                if user.status != None:
                    # Very long line that will definitely exceed the 79 characters limit imposed by the PEP-8 style guide
                    return {"name":user.name,"email":user.email,"domain":O[1],"length":l}
        return None
