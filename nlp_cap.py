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
      self.c = ('turn', 'find', 'scan', 'extend', 'pick', 'put')


   # Return True if verb is in CCSR capabilities list
   def capable(self, s):
      return (s in self.c)

   # Construct an actual CCSR command from a sentence Analysis class instance
   # This command can be passed diretly to the CCSR telementry fifo
   def constructCmd(self, sa):
      if sa.getSentenceHead('VP') == 'turn': 
          return 'turnto 180'
      elif sa.getSentenceHead('VP') == 'pick':
          return 'pickup'
      elif sa.getSentenceHead('VP') == 'put':
          return 'putdown'
      else:
         return "say I don't know that command"
