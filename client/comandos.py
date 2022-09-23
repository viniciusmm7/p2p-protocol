import random
import numpy as np
import time
c1 = b"\x00\xFA\x00\x00"
c2 = b"\x00\x00\xFA\x00"
c3 = b"\xFA\x00\x00"
c4 = b"\x00\xFA\x00"
c5 = b"\x00\x00\xFA"
c6 = b"\x00\xFA"
c7 = b"\xFA\x00"
c8 = b"\x00"
c9 = b"\xFA"

lista = [c1, c2,c3,c4,c5,c6,c7,c8,c9]

def quantidade():
    return random.randint(50,100)


def comando(n, lista):

    # bit final de verificação
    transicao = b'\xFF'
    i = 0 #Contador
    ref = b''
    while i < n:

        # Randomizador 
        num = random.randint(0,8)


        # Seleciona o comando na lista de acordo com o numero random
        com = lista[num]

        # Salva o comando em uma lista
        ref+= com

        # incrementa o contador
        i+=1
    return ref



def calcula_tempo(tempo):
    t = []

    hora = int(tempo.split()[3][:2]) * 3600
    minuto = int(tempo.split()[3][3:5]) * 60
    segundo = int(tempo.split()[3][6:])

    t.append(hora)
    t.append(minuto)
    t.append(segundo)
    
    return t
   

def variacao_tempo(t1,t2):
    variacao = (t2[0] - t1[0]) + (t2[1] - t1[1]) + (t2[2] - t1[2]) 
    return variacao
