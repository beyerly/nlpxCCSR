#!/usr/bin/python


# Debug script for nlpx: we read lines from stdin and pass them to nlpx
# This script is not used by CCSR; instead nlpx will receive text from
# voice recognition engine (google)

import sys
import getopt
import re
from pattern.en import parse
from pattern.en import pprint
from pattern.en import parsetree
from pattern.en import wordnet
from pattern.en import pluralize, singularize
from pattern.en import conjugate, lemma, lexeme

from nlpx import ccsrNlpClass

loop = True

def main(argv):
   try:
      opts, args = getopt.getopt(argv,"hn",["help","noloop"])
   except getopt.GetoptError:
      print 'nlp.py -h -l'
      sys.exit(2)
   for opt, arg in opts:
      if opt == '-h':
         print 'nlp.py'
         sys.exit()
      elif opt in ("-n"):
         loop = False

if __name__ == "__main__":
   main(sys.argv[1:])

appID = 'xxx'        # Fill in your own Wolfram AppID here
useFifos = False     # Only set True if integrated with CCSR robot platform
s = ccsrNlpClass(useFifos, appID)
#debug = False
debug = True

print 'nplxCCSR v0.1: type a question...'
while (1):
   line = sys.stdin.readline()
   s.nlpParse(line, debug)
   if not loop:
      break
