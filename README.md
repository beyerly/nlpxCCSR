nlpxCCSR
========
nlpxCCSR provides the class ccsrNlpClass, a basic, expirimental Natural Language Processing and Machine Learning 
engine. It is currently used by the CCSR robot platform (http://www.letsmakerobots.com/robot/project/ccsr)

The class provides a parser that interprets basic natural language, generates responses and executes commands,
kind of like a chatbot or Apple's Siri. Normally, the class is instantiated by the CCSR robot software, which passes 
strings generated by Google speech2text service from audio files captured by the robot. ccsrNlpClass is integrated with
WolframAplha API for queries. The class will generate basic verbal responses, or a CCSR-platform specific command if 
it interprets the sentence as a specific robot-command like 'pick up the ball'. THe CCSR platform will synthesize the
text-based ccsrNlpClass responses back into speech using espeak.

By running the dubug script nlpcmd.py, you get a cmd-line interface, and we can interact with the engine by typing questions 
or comamnds.
