#!/usr/bin/python


# NLPX provides the ccsrNlpClass, the Natural Language Processing engine for CCSR robot
# The main interface is ccsrNlpClass.nlpParse('sentence'), which will interpret the sentence
# and reply by giving a command to the CCSR process through the nlp telemetry fifo interface.
# If the reply is pure verbal answer to voice input, the CCSR command 'say' will be used
# IF the result of the voice input is a CCSR action, the appropriate cmd will be synthesized
# e.g. 'turnto <angle>' or 'set pantilt <X> <Y>'

# nlpx will try to answer queries based on its own knowledge (memory class), but if unable,
# it will pass the full query to WolframAlpha API (cloud service), and pass the most appropriate
# 'pod' (wolfram answer), back to CCSR



import sys
import getopt
import re
import subprocess
import xml.etree.ElementTree as ET
import csv
import random
import os

from pattern.en import parse
from pattern.en import pprint
from pattern.en import parsetree
from pattern.en import wordnet
from pattern.en import pluralize, singularize
from pattern.en import conjugate, lemma, lexeme

from nlp_sa  import sentenceAnalysisClass
from nlp_cap import capabilitiesClass
from nlp_mem import memoryClass

ccsrStateDumpFile      = '../data/ccsrState_dump.csv'
ccsrStateDumpFileDebug = 'ccsrState_dump.csv'

# main CCSR NLP Class
class ccsrNlpClass:

   def __init__(self, useFifos, appID):
      self.cap       = capabilitiesClass()   # CCSR capabilities
      self.ccsrmem   = memoryClass()         # memory of concepts

      # Add a concept 'I', defining CCSR identity
      self.ccsrmem.add('I')
      self.ccsrmem.concepts['I'].state = 'great'      # dynamically reflect CCSR mood by telemetry
      self.ccsrmem.concepts['I'].person = '1sg'       # 2st person singular
      self.ccsrmem.concepts['I'].isProperNoun = True 

      # This is a list of useful 'pod names' in an XML file returned by Wolfram Alpha API
      # as a result of a query.
      self.wolframAlphaPodsUsed = ('Notable facts', 'Result', 'Definition')

      # translate CCSR status dump items to concepts for ccsrmem
      self.translateStatus =  {"compass": "compass heading",
                               "temperature": "temperature",
                               "stress": "stress level",
                               "battery": "battery level",
                               "power": "power usage",
                               "light": "ambient light level"}

      # Synonymes for certain response forms, to give some natural response
      # variations
      self.responseVariations =  {"yes": ("yes",
                                          "affirmative",
                                          "definitely",
                                          "sure",
                                          "absolutely"),
                                  "acknowledge": ("I see",
                                                  "OK",
                                                  "acknowledged",
                                                  "if you say so",
                                                  "copy that",
                                                  "I'll remember that"),
                                  "gratitude":   ("Thanks",
                                                  "I appreciate that",
                                                  "You are too kind",
                                                  "Oh stop it"),
                                  "insulted":    ("I'm sorry you feel that way",
                                                  "well, you're not too hot either",
                                                  "look who's talking",
                                                  "can't we just be nice"),
                                  "gratitudeReply": ("you're very welcome",
                                                     "sure thing",
                                                     "no worries",
                                                     "don't mention it"),
                                  "bye": ("see you later",
                                          "it was a pleasure",
                                          "bye bye"),
                                  "no": ("no",
                                         "negative",
                                         "I don't think so",
                                         "definitely not",
                                         "no way",
                                         "you wish")
                                  }

      self.positivePhrases = ['smart',
                              'impressive',
                              'cool']
      self.negativePhrases = ['stupid',
                              'annoying',
                              'boring']

      if useFifos:
         self.wfifo = open('/home/root/ccsr/nlp_fifo_in', 'w')
         self.rfifo = open('/home/root/ccsr/nlp_fifo_out', 'r')

      self.wolframID = appID     # Wolfram API App ID
      self.useFifos = useFifos   # IF True, we pipe responses to CCSR. False in debg mode
      self.cmdResponse = ''      # We store CCSR command response here, unused for now

   def randomizedResponseVariation(self, response):
       idx = random.randint(0, len(self.responseVariations[response])-1)
       return self.responseVariations[response][idx]

   # If nlpx can;t determine the answer to a question based on its own knowledge
   # this function synthesises a wolframAlpha query from the sentence
   # e.g. 'what is the weather today' => 'what+is+the+weather+today'
   def createWolframAlphaQuery(self, sa):
      query = ''
      for word in sa.s.words:
         query = query + word.string
         if sa.s.words.index(word) != len(sa.s.words) - 1:
            query = query + '+'
      return query

   # Call WolframAlpha API and return list of strings containing most relevant
   # answers to a query contained in sa.
   # e.g. 'what is the tallest building in the world' =>
   #  ('xxx tower', '3000ft')
   def wolframAlphaAPI(self, sa):
      # Call wolfram API as subprocess, 
      call = 'curl "http://api.wolframalpha.com/v2/query?input=' + self.createWolframAlphaQuery(sa) + '&appid=' + self.wolframID + '&format=plaintext" -o query.xml'
      p = subprocess.Popen(call, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
      retval = p.wait()
      if retval == 0:
         # parse query XML file returned by wolfram alpha
         tree = ET.parse('./query.xml')
         root = tree.getroot()
         for pod in root.findall('pod'):
            title = pod.get('title')
            if title in self.wolframAlphaPodsUsed:
               # pod title is one that most likely yields good answers
               for subpod in pod.findall('subpod'):
                  # retrieve plaintext answers
                  plaintext = subpod.find('plaintext')
                  if plaintext != None:
                     text = subpod.find('plaintext').text
                     textlist = re.split('\n', text)
                     # return list of strings representign answer to query
                     return textlist
         # We havent found a known pod, just pick the second pod, a wild
         # guess that is the most useful
         pod = root.findall('pod')[1]
         for subpod in pod.findall('subpod'):
            # retrieve plaintext answers
            plaintext = subpod.find('plaintext')
            if plaintext != None:
               text = subpod.find('plaintext').text
               textlist = re.split('\n', text)
               # return list of strings representign answer to query
               print textlist
	       return textlist
      else:
         print 'Error: curl command failed, only runs on linux. Query not successful'
         return ('none')

   # Respone to voice input back to CCSR process as telemetry through nlp fifo
   def response(self, s):
      m = s + '*'
      print s
      if self.useFifos:
         self.wfifo.write(m)
         self.wfifo.flush()
         # This should block untill cmd response is received. Used to sync.
         self.cmdResponse = self.rfifo.readline();  

   # This function updates nlpxCCSR with the current state of the CCSR process
   # Send cmd to CCSR to dump status in CSV file. Parse this CVS
   # file and update the 'I' concept in ccsrmem accordinly
   # This function is run everytime a query is done about 'I' (e.g. how are you)
   def updateCCSRStatus(self):
      self.response("dump csv")
      if os.path.isfile(ccsrStateDumpFile): 
         statusDump = open(ccsrStateDumpFile, 'r')
      else:
         print "Can't open " + ccsrStateDumpFile + ", using static debug file"
         statusDump = open(ccsrStateDumpFileDebug, 'r')
      csvfile = csv.reader(statusDump)
      for item in csvfile:
         self.ccsrmem.concepts['I'].properties[item[0]] = [self.translateStatus[item[0]], item[1] + " " + item[2]] 
      if int(self.ccsrmem.concepts['I'].properties['stress'][1]) > 0:
         self.ccsrmem.concepts['I'].state = 'not feeling so great'      
      else:
         self.ccsrmem.concepts['I'].state = 'great'      

   def getPersonalProperty(self, sa):
      # Question refers back to ccsr: how is 'your' X  
      if sa.getSentenceRole(sa.concept) in self.ccsrmem.concepts['I'].properties:
         self.response("say my " + self.ccsrmem.concepts['I'].properties[sa.getSentenceRole(sa.concept)][0] + " is " + self.ccsrmem.concepts['I'].properties[sa.getSentenceRole(sa.concept)][1])
      else:
         self.response("say I don't know how my " + sa.getSentenceRole(sa.concept) + " is ")
      
   # Main function: generate a CCSR command as response to input text.
   # Text will be from google speech2text service.
   # 'how are you' => 'say I am great'
   # 'can you look left => 'say sure', 'set pantilt 180 0 20'
   def nlpParse(self, line, debug=0):
      text = parsetree(line, relations=True, lemmata=True)
      for sentence in text:
         sa = sentenceAnalysisClass(sentence, debug)
         st = sa.sentenceType()
         if sa.debug:
            print st
            print 'concept: ' + sa.concept
         # Question state: 'how is X'
         if st == 'questionState':
            self.updateCCSRStatus()
            if sa.is2ndPersonalPronounPosessive('OBJ'):
               # Question refers back to ccsr: how is 'your' X. Look up CCSR's personal property
               self.getPersonalProperty(sa)
            elif self.ccsrmem.known(sa.getSentenceRole(sa.concept)):
               # if we know anything about the concept, we rely on CCSR memory
               if self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].state == 'none':
                  self.response("say Sorry, I don't know how " + sa.getSentencePhrase(sa.concept) + ' ' + conjugate('be', self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].person))
               else:   
                  self.response("say " + sa.getSentencePhrase(sa.concept) + " " + conjugate('be', self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].person) + " " + self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].state)
            else:
               if sa.complexQuery():
                  # Nothing is knows about the concept, and the query is 'complex', let's ask the cloud
                  self.response("say let me look that up for you")
                  for result in self.wolframAlphaAPI(sa):
                     self.response("say " + result)              
               else:
                  self.response("say Sorry, I don't know " + sa.getSentencePhrase(sa.concept))
         # Confirm state: 'is X Y'
         elif st == 'confirmState':
            if self.ccsrmem.known(sa.getSentenceRole(sa.concept)):
               if sa.getSentencePhrase('ADJP') == self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].state:
                  self.response("say " + self.randomizedResponseVariation('yes')) 
               else:
                  self.response("say " + self.randomizedResponseVariation('no') + " " + sa.getSentencePhrase(sa.concept) + " " + conjugate('be', self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].person) + " " + self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].state)
            else:
               self.response("say Sorry, I don't know " + sa.getSentencePhrase(sa.concept))
         # Question definition: 'what/who is X'
         elif st == 'questionDefinition':
            if sa.is2ndPersonalPronounPosessive('OBJ'): 
               # Question refers back to ccsr: what is 'your' X. Look up CCSR's personal property
               self.updateCCSRStatus()
               self.getPersonalProperty(sa)
            else:
               # Question about person, object or thing
               if sa.complexQuery():
                  self.response("say let me look that up for you")
                  for result in self.wolframAlphaAPI(sa):
                     self.response("say " + result)              
               else:
                  wordnetQuery = wordnet.synsets(sa.getSentenceRole(sa.concept))
                  if len(wordnetQuery) > 0:
                     self.response("say " + re.split(";",wordnetQuery[0].gloss)[0])
                  else:
                     # wordnet doesn't know, ask WolframAlpha
                     self.response("say let me look that up for you")
                     for result in self.wolframAlphaAPI(sa):
                        self.response("say " + result)              
         # State: 'X is Y'
         elif st == 'statement':
            if sa.is2ndPersonalPronounPosessive('SBJ'): 
               # Refers back to ccsr: 'your' X is Y 
               if sa.getSentenceRole(sa.concept) not in self.ccsrmem.concepts['I'].properties:
                  self.ccsrmem.concepts['I'].properties[sa.getSentenceRole(sa.concept)] = [sa.getSentenceRole(sa.concept), sa.getSentencePhrase('OBJ')]
               self.response("say " + self.randomizedResponseVariation('acknowledge')) 
            else:
               if sa.getSentenceRole(sa.concept) == 'I':
                  # Statement about CCSR, do not memorize this (CCSR maintains its own state based on CCSR telemetry
                  # but instead react to statement
                  print 'ww ' + sa.getSentenceRole('ADJP')
                  if sa.getSentenceRole('ADJP') in self.positivePhrases:
                     self.response("say " + self.randomizedResponseVariation('gratitude')) 
                  else:
                     self.response("say " + self.randomizedResponseVariation('insulted')) 
               else:
                  if not self.ccsrmem.known(sa.getSentenceRole(sa.concept)):
                     self.ccsrmem.add(sa.getSentenceRole(sa.concept))  
                  self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].state = sa.getSentencePhrase('ADJP')
                  self.response("say " + self.randomizedResponseVariation('acknowledge')) 
         # State locality: 'X is in Y'
         elif st == 'stateLocality':
            if not self.ccsrmem.known(sa.getSentenceRole(sa.concept)):
               self.ccsrmem.add(sa.getSentenceRole(sa.concept))  
            self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].locality = sa.getSentencePhrase('PNP')
            self.response("say " + self.randomizedResponseVariation('acknowledge')) 
         # Question locality: 'Where is X'
         elif st == 'questionLocality':
            if self.ccsrmem.known(sa.getSentenceRole(sa.concept)):
               if self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].locality == 'none':
                  self.response("say Sorry, I don't know where " + sa.getSentencePhrase(sa.concept) + ' ' + conjugate('be', self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].person))
               else:   
                  self.response("say " + sa.getSentencePhrase(sa.concept) + " " + conjugate('be', self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].person) + " " + self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].locality)
            else:
               self.response("say Sorry, I don't know " + sa.getSentencePhrase(sa.concept))
         # Command
         elif st == 'command':
            if self.cap.capable(sa.getSentenceHead('VP')):
               # Command is a prefixed CCSR command to be given through telemetry
               self.response("say " + self.randomizedResponseVariation('yes') + " I can") 
               for cmd in self.cap.constructCmd(sa):
                  self.response(cmd)
            elif sa.getSentenceHead('VP') == 'tell':
               # This is a request to tell something about a topic
               if len(sa.s.pnp) > 0:
                  # We have a prepositional phrase: 'tell me about X'
                  concept = sa.reflectObject(sa.s.pnp[0].head.string)
                  if self.ccsrmem.known(concept):
                     if  len(self.ccsrmem.concepts[concept].properties) > 0:
                        for p in self.ccsrmem.concepts[concept].properties:
                           self.response("say " + self.ccsrmem.posessivePronouns[self.ccsrmem.concepts[concept].person] + " " + self.ccsrmem.concepts[concept].properties[p][0] + " is " + self.ccsrmem.concepts[concept].properties[p][1])            
                     else:
                        self.response("say sorry, I can't tell you much about " + sa.reflectObject(sa.s.pnp[0].head.string))
                  else:
                     self.response("say let me look that up for you")
                     self.response("say " + self.wolframAlphaAPI(sa))              
            else:
               self.response("say I'm afraid I can't do that. I don't know how to " + sa.getSentenceHead('VP'))
         # State locality: 'X is in Y'
         elif st == 'greeting':
            self.response("say Hi, how are you") 
         elif st == 'bye':
            self.response("say " + self.randomizedResponseVariation('bye')) 
         elif st == 'gratitude':
            self.response("say " + self.randomizedResponseVariation('gratitudeReply')) 
         else:
            self.response("say sorry, I don't understand")
