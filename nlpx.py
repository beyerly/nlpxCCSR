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

from pattern.en import parse
from pattern.en import pprint
from pattern.en import parsetree
from pattern.en import wordnet
from pattern.en import pluralize, singularize
from pattern.en import conjugate, lemma, lexeme

from nlp_sa  import sentenceAnalysisClass
from nlp_cap import capabilitiesClass
from nlp_mem import memoryClass

# main CCSR NLP Class
class ccsrNlpClass:

   def __init__(self):
      self.cap       = capabilitiesClass()   # CCSR capabilities
      self.ccsrmem   = memoryClass()         # memory of concepts

      # Add a concept 'I', defining CCSR identity
      self.ccsrmem.add('I')
      self.ccsrmem.concepts['I'].state = 'great'      # should reflect CCSR mood by telemetry, static for now
      self.ccsrmem.concepts['I'].person = '1sg'       # 2st person singular
      self.ccsrmem.concepts['I'].isProperNoun = True 

      # This is a list of useful 'pod names' in an XML file returned by Wolfram Alpha API
      # as a result of a query.
      self.wolframAlphaPodsUsed = ('Notable facts', 'Result')

#      self.fifo = open('/home/root/ccsr/nlp_fifo_in', 'w')
      self.wolframID = ''  # Need to fill in your Wolfram App ID
      
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
      # parse query XML file returned by wolfram alpha
      tree = ET.parse('./query.xml')
      root = tree.getroot()
      for pod in root.findall('pod'):
         title = pod.get('title')
         if title in self.wolframAlphaPodsUsed:
            # pod title os one that most likely yields good answers
            for subpod in pod.findall('subpod'):
               # retrieve plaintext answers
               plaintext = subpod.find('plaintext')
               if plaintext != None:
                  text = subpod.find('plaintext').text
                  textlist = re.split('\n', text)
                  # return list of strings representign answer to query
                  return textlist
      return None

   # Respone to voice input back to CCSR process as telemetry through nlp fifo
   def response(self, s):
#      self.fifo.write(s + '#')
      print s

   # Main function: generate a CCSR command as response to input text.
   # Text will be from google speech2text service.
   # 'how are you' => 'say I am great'
   # 'can you look left => 'say sure', 'set pantilt 180 0 20'
   def nlpParse(self, line):
      text = parsetree(line, relations=True, lemmata=True)
      for sentence in text:
         sa = sentenceAnalysisClass(sentence)
         st = sa.sentenceType()
         # Question state: 'how is X'
         if st == 'questionState':
            concept = sa.getSentenceRole('OBJ')
            if self.ccsrmem.known(concept):
               # if we know anything about the concept, we rely on CCSR memory
               if self.ccsrmem.concepts[concept].state == 'none':
                  self.response("say Sorry, I don't know how " + sa.getSentencePhrase('OBJ') + ' ' + conjugate('be', self.ccsrmem.concepts[concept].person))
               else:   
                  self.response("say " + sa.getSentencePhrase('OBJ') + " " + conjugate('be', self.ccsrmem.concepts[concept].person) + " " + self.ccsrmem.concepts[concept].state)
            else:
               if sa.complexQuery():
                  # Nothing is knows about the concept, and the query is 'complex', let's ask the cloud
                  self.response("say let me look that up for you")
                  for result in self.wolframAlphaAPI(sa):
                     self.response("say " + result)              
               else:
                  self.response("say Sorry, I don't know " + sa.getSentencePhrase('OBJ'))
         # Confirm state: 'is X Y'
         elif st == 'confirmState':
            concept = sa.getSentenceRole('OBJ')
            if self.ccsrmem.known(concept):
               if sa.getSentencePhrase('ADJP') == self.ccsrmem.concepts[concept].state:
                  self.response("say yes") 
               else:
                  self.response("say no, " + sa.getSentencePhrase('OBJ') + " " + conjugate('be', self.ccsrmem.concepts[concept].person) + " " + self.ccsrmem.concepts[concept].state)
            else:
               self.response("say Sorry, I don't know " + sa.getSentencePhrase('OBJ'))
         # Question definition: 'what/who is X'
         elif st == 'questionDefinition':
            concept = sa.getSentenceRole('OBJ')
            if sa.is2ndPersonalPronounPosessive('OBJ'): 
               # Question refers back to ccsr: what is 'your' X  
               if concept in self.ccsrmem.concepts['I'].properties:
                  self.response("say my " + sa.getSentenceRole('OBJ') + " is " + self.ccsrmem.concepts['I'].properties[concept])
               else:
                  self.response("say I don't know what my " + sa.getSentenceRole('OBJ') + " is ")
            else:
               # Question about person, object or thing
               if sa.complexQuery():
                  self.response("say let me look that up for you")
                  for result in self.wolframAlphaAPI(sa):
                     self.response("say " + result)              
               else:
                  wordnetQuery = wordnet.synsets(concept)
                  if len(wordnetQuery) > 0:
                     self.response("say " + re.split(";",wordnetQuery[0].gloss)[0])
                  else:
                     # wordnet doesn't know, ask WolframAlpha
                     self.response("say let me look that up for you")
                     for result in self.wolframAlphaAPI(sa):
                        self.response("say " + result)              
         # State: 'X is Y'
         elif st == 'statement':
            concept = sa.getSentenceRole('SBJ')
            if sa.is2ndPersonalPronounPosessive('SBJ'): 
               # Refers back to ccsr: 'your' X is Y 
               if concept not in self.ccsrmem.concepts['I'].properties:
                  self.ccsrmem.concepts['I'].properties[concept] = sa.getSentencePhrase('OBJ')
            else:
               if not self.ccsrmem.known(concept):
                  self.ccsrmem.add(concept)  
               self.ccsrmem.concepts[concept].state = sa.getSentencePhrase('ADJP')
            self.response("say I see") 
         # State locality: 'X is in Y'
         elif st == 'stateLocality':
            concept = sa.getSentenceRole('SBJ')
            if not self.ccsrmem.known(concept):
               self.ccsrmem.add(concept)  
            self.ccsrmem.concepts[concept].locality = sa.getSentencePhrase('PNP')
            self.response("say I see") 
         # Question locality: 'Where is X'
         elif st == 'questionLocality':
            concept = sa.getSentenceRole('OBJ')
            if self.ccsrmem.known(concept):
               if self.ccsrmem.concepts[concept].locality == 'none':
                  self.response("say Sorry, I don't know where " + sa.getSentencePhrase('OBJ') + ' ' + conjugate('be', self.ccsrmem.concepts[concept].person))
               else:   
                  self.response(sa.getSentencePhrase('OBJ') + " " + conjugate('be', self.ccsrmem.concepts[concept].person) + " " + self.ccsrmem.concepts[concept].locality)
            else:
               self.response("say Sorry, I don't know " + sa.getSentencePhrase('OBJ'))
         # Command
         elif st == 'command':
            if self.cap.capable(sa.getSentenceHead('VP')):
               # Command is a prefixed CCSR command to be given through telemetry
               self.response("say yes I can") 
               self.response(self.cap.constructCmd(sa))
            elif sa.getSentenceHead('VP') == 'tell':
               # This is a request to tell something about a topic
               if len(sa.s.pnp) > 0:
                  # We have a prepositional phrase: 'tell me about X'
                  concept = sa.reflectObject(sa.s.pnp[0].head.string)
                  if self.ccsrmem.known(concept):
                     if  len(self.ccsrmem.concepts[concept].properties) > 0:
                        for p in self.ccsrmem.concepts[concept].properties:
                           self.response("say " + self.ccsrmem.posessivePronouns[self.ccsrmem.concepts[concept].person] + " " + p + " is " + self.ccsrmem.concepts[concept].properties[p])            
                     else:
                        self.response("say sorry, I can't tell you much about " + sa.reflectObject(sa.s.pnp[0].head.string))
                  else:
                     self.response("say let me look that up for you")
                     self.response("say " + self.wolframAlphaAPI(sa))              
            else:
               self.response("say sorry, I don't know how to " + sa.getSentenceHead('VP'))
         # State locality: 'X is in Y'
         elif st == 'greeting':
            self.response("say Hi, how are you") 
         else:
            self.response("say sorry, I don't understand")
