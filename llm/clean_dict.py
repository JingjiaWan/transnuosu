import os

lines = []
with open("data/english_yi_dictionary.txt", 'r', encoding='utf-8') as f:
    for line in f :
     if "|" in line and "not found" not in line : 
         if line.strip()[0] == '-' : 
             lines.append(line.strip()[1:].strip()) 

with open("data/english_yi_dictionary_clean.txt", 'w', encoding='utf-8') as f:
    for line in lines :
        f.write(line + "\n")