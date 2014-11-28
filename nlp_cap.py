# CCSR capabilites class
# This class contains information about what commands we can give the CCSR
# hardware through the telemetry command interface. If the NLP module detects
# the voice audio is a command, we convert is into an actual
# CCSR robot command

import sys
import re

from pattern.en import parse
from pattern.en import pprint
from pattern.en import parsetree
from pattern.en import wordnet
from pattern.en import pluralize, singularize
from pattern.en import conjugate, lemma, lexeme


class capabilitiesClass:
   def __init__(self):
      # List of verbs that are translated into CCSR robot commands
      self.c = ('turn',
                'find',
                'extend',
                'pick',
                'put',
                'look',
                'analyze')


   # Return True if verb is in CCSR capabilities list
   def capable(self, s):
      return (s in self.c)

   # Construct an actual CCSR command list from a sentence Analysis class instance
   # The commands in this list can be passed diretly to the CCSR telementry fifo
   def constructCmd(self, sa):
      if sa.getSentenceHead('VP') == 'turn': 
          
          return ['turnto ' + sa.getFirstWord('CD').string]
      elif sa.getSentenceHead('VP') == 'pick':
          return ['pickup']
      elif sa.getSentenceHead('VP') == 'put':
          return ['putdown']
      elif sa.getSentenceHead('VP') == 'look':
          return ['orient fwd']
      elif sa.getSentenceHead('VP') == 'analyze':
          return ['analyseobj']
      elif sa.getSentenceHead('VP') == 'find':
          return ['set track 1',  # Enable object tracking
                  'set state 2']  # Change CCSR state from RC to Orientation
      else:
         return "say I don't know that command"
