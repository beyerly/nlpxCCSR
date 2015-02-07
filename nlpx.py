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
import requests

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
                               "happiness": "happiness",
                               "arousal": "arousal",
                               "battery": "battery level",
                               "power": "power usage",
                               "light": "ambient light level"}

      # Synonymes for certain response forms, to give some natural response
      # variations
      self.responseVariations =  {"yes": ("Yes.",
                                          "Affirmative.",
                                          "Definitely.",
                                          "Sure.",
                                          "Absolutely."),
                                  "acknowledge": ("I see.",
                                                  "OK.",
                                                  "Acknowledged.",
                                                  "If you say so.",
                                                  "Copy that.",
                                                  "I'll remember that."),
                                  "gratitude":   ("Thanks!",
                                                  "I appreciate that.",
                                                  "You are too kind.",
                                                  "Oh stop it."),
                                  "insulted":    ("I'm sorry you feel that way.",
                                                  "Well, you're not too hot either.",
                                                  "Look who's talking.",
                                                  "Can't we just be nice."),
                                  "gratitudeReply": ("You're very welcome!",
                                                     "Sure thing!",
                                                     "No worries!",
                                                     "Don't mention it!"),
                                  "bye": ("See you later.",
                                          "It was a pleasure.",
                                          "Bye bye."),
                                  "hi": ("Hi, how are you.",
                                          "Hey there.",
                                          "What's going on!"),
                                  "no": ("No.",
                                         "Negative.",
                                         "I don't think so.",
                                         "Definitely not.",
                                         "No way.",
                                         "You wish.")
                                  }

      self.positivePhrases = ['smart',
                              'impressive',
                              'cool']
      self.negativePhrases = ['stupid',
                              'annoying',
                              'boring']


      self.emotionMap = [['angry.',
                          'aggrevated',
                          'very excited',
                          'very happy'],
                         ['frustrated',
                          'stressed',
                          'excited',
                          'happy.'],
                         ['sad',
                          'doing OK',
                          'doing well',
                          'doing very well.'],
                         ['depressed',
                          'sleepy',
                          'bored',
                          'relaxed']]
                         


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

   def annaApi(self, text):
      apiString = re.sub(' ', '%20', text)
      url = 'http://droids.homeip.net/RoboticsWeb/SimpleAPI.aspx?API.Key=29c7e1f3-23cf-496a-abd6-34e92e8d670f&Session.Key=New&Robot.Key=59459&Speech.Input=' + apiString
      r = requests.get(url)
      if r:
         # parse query XML file returned by ANNA
         root = ET.fromstring(r.content)
         resp = root.findall('Response.Speech')
         if resp:
            self.response(resp.text)
         else:
            self.response('Sorry, could not get response from Anna')

   # Call WolframAlpha API and return list of strings containing most relevant
   # answers to a query contained in sa.
   # e.g. 'what is the tallest building in the world' =>
   #  ('xxx tower', '3000ft')
   def wolframAlphaAPI(self, sa):
      url = 'http://api.wolframalpha.com/v2/query?input=' + self.createWolframAlphaQuery(sa) + '&appid=' + self.wolframID + '&format=plaintext'
      print url
      r = requests.get(url)
      if r:
         # parse query XML file returned by wolfram alpha
         root = ET.fromstring(r.content)
         for pod in root.findall('pod'):
            title = pod.get('title')
            if title in self.wolframAlphaPodsUsed:
               # pod title is one that most likely yields good answers
               for subpod in pod.findall('subpod'):
                  # retrieve plaintext answers
                  plaintext = subpod.find('plaintext')
                  if plaintext != None:
                     text = subpod.find('plaintext').text
                     text = re.sub('noun ', '', text)
                     # Filter out funny characters
                     text = re.sub('[^A-Z0-9a-z \\n;]', '', text)
                     text = re.sub('; (.)', lambda pat: '. ' + pat.group(1).upper(), text)
                     textlist = re.split('\n', text)
                     # return list of strings representign answer to query
                     return textlist
         # We havent found a known pod, just pick the second pod, a wild
         # guess that is the most useful. Pod title should reflect contents
         pod = root.findall('pod')
         if len(pod) > 0:
            pod = pod[1]
            for subpod in pod.findall('subpod'):
               # retrieve plaintext answers
               plaintext = subpod.find('plaintext')
               if plaintext != None:
                  # Replace a set of known symbols with words
                  text = subpod.find('plaintext').text
                  text = re.sub(' .F', ' degrees', text)
                  text = re.sub('\%', ' percent', text)
                  text = re.sub(' mph', ' miles per hour', text)
                  # Filter out funny characters
                  text = re.sub('[^A-Z0-9a-z \\n]', '', text)
                  textlist = re.split('\n', text)
                  textlist.insert(0,pod.get('title'))
                  # return list of strings representign answer to query
                  return textlist
         else:
            # no pods
            textlist = ['Sorry, I could not find anything']
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
         # Item in cvs file is list of 2 or 3 items: 'name', 'value' and optinally a 'unit' (e.g. power 100 milliwatt)
         self.ccsrmem.concepts['I'].properties[item[0]] = [self.translateStatus[item[0]], item[1] + " " + item[2]] 
      yEmotionMap = 3-(4*(int(self.ccsrmem.concepts['I'].properties['arousal'][1]))/255)
      xEmotionMap = 4*(int(self.ccsrmem.concepts['I'].properties['happiness'][1]) + 255)/511
      self.ccsrmem.concepts['I'].state = self.emotionMap[yEmotionMap][xEmotionMap]
#      if int(self.ccsrmem.concepts['I'].properties['happiness'][1]) > 0:
#         self.ccsrmem.concepts['I'].state = 'not feeling so great'      
#      else:
#         self.ccsrmem.concepts['I'].state = 'great'      

   def getPersonalProperty(self, sa):
      # Question refers back to ccsr: how is 'your' X  
      if sa.getSentenceRole(sa.concept) in self.ccsrmem.concepts['I'].properties:
         self.response("say my " + self.ccsrmem.concepts['I'].properties[sa.getSentenceRole(sa.concept)][0] + " is " + self.ccsrmem.concepts['I'].properties[sa.getSentenceRole(sa.concept)][1])
      else:
         self.response("say I don't know what my " + sa.getSentenceRole(sa.concept) + " is ")
      
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
               if(sa.getSentenceRole(sa.concept) == 'I'):
                  self.updateCCSRStatus()
               if sa.getSentencePhrase('ADJP') == self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].state:
                  self.response("say " + self.randomizedResponseVariation('yes'))
                  self.response("facial 14") # Nod Yes 
               else:
                  self.response("say " + self.randomizedResponseVariation('no'))
                  self.response("facial 15") # Shake no 
                  self.response("say " + sa.getSentencePhrase(sa.concept) + " " + conjugate('be', self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].person) + " " + self.ccsrmem.concepts[sa.getSentenceRole(sa.concept)].state)
                  print self.ccsrmem.concepts['I'].state
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
                     self.response("set mood 50 50 ") 
                     self.response("say " + self.randomizedResponseVariation('gratitude')) 
                  else:
                     self.response("set mood -50 50 ") 
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
            self.response("say " + self.randomizedResponseVariation('hi')) 
         elif st == 'bye':
            self.response("say " + self.randomizedResponseVariation('bye')) 
         elif st == 'gratitude':
            self.response("say " + self.randomizedResponseVariation('gratitudeReply')) 
         elif st == 'adverbPhrase':
            if sa.getSentenceHead('ADJP') == 'further':
               for cmd in self.cap.lastCmd:
                  self.response(cmd)
         else:
            self.response("say sorry, I don't understand")
         self.cap.lastCmd = self.cap.constructCmd(sa)
