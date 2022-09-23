#####################################################
# Camada Física da Computação
#Carareto
#11/08/2022
#Aplicação
####################################################
from enlace import *
import time, platform, serial.tools.list_ports
import numpy as np
from comandos import *
from img import *

class Client:
    def __init__(self):
        self.HANDSHAKE = b'\x01'
        self.ACK = b'\x02'
        self.EOP = b'\xAA\xBB\xCC\xDD'
        self.ERROR = b'\x03'
        self.FINAL = b'\x04'
        self.IMG = "img/olhos_fitao.png"

        self.os = platform.system().lower()
        self.serialName = self._findArduino()
        self.com1 = enlace(self.serialName)
        self.com1.enable()

        self.status = 0
        
        self.t0 = 0
        self.t1 = 0
        self.t2 = 0
        self.t3 = 0
        self.packetId = 0
        self.lastpacketId = 0
        self.lenPackets = 0 

        
    # ----- Método para a primeira porta com arduíno
    #       se tiver mais de uma (sozinho, por exemplo)
    def _findArduino(self) -> list:
        result = []
        ports = list(serial.tools.list_ports.comports())
        c = 0
        for p in ports:
            result.append(f'/dev/ttyACM{c}')
            c += 1
        return result[0]

    # ===== MÉTODOS PARA EVITAR REPETIÇÃO DE CÓDIGO =====
    def waitBufferLen(self):
        rxLen = self.com1.rx.getBufferLen()
        while rxLen == 0:
        
            if self.status==1:
                break
            rxLen = self.com1.rx.getBufferLen()
            self.t1 = calcula_tempo(time.ctime())
            if variacao_tempo(self.t0, self.t1) > 5 and self.status == 0:
                res = input("Tentar reconexção?(s/n) ")

                if res.lower() == "s":
                    self.t0 = calcula_tempo(time.ctime())
                    self.send_handshake(len_packets=self.lenPackets.to_bytes(1,'big'))
                    rxLen = self.waitBufferLen()
                else:
                    raise Exception('Time out. Servidor não respondeu.')
            if rxLen != 0:
                break
        return rxLen

    def waitStatus(self):
        txSize = self.com1.tx.getStatus()
        while txSize == 0:
            txSize = self.com1.tx.getStatus()
        return txSize
    # ====================================================

    # ========= MÉTODOS PARA ADMINISTRAR PACOTES =========

    # ----- Quebrar os dados em payloads de até 114 bytes
    def make_payload_list(self, data):
        limit = 114
        payload_list = []
        cont = 0 

        while len(data) > 0:
            if limit > len(data):
                limit = len(data)
            payload_list.append(data[:limit])
            data = data[limit:]
        #print(len(payload_list))
        return payload_list, len(payload_list)

    # ----- Cria o head do pacote
    def make_head(self, type=b'\x00', h1=b'\x00', h2=b'\x00', len_packets=b'\x00', packet_id=b'\x00', h5=b'\x00', h6=b'\x00', last_packet=b'\x00', h8=b'\x00', h9=b'\x00'):
        return (type + h1 + h2 +len_packets + packet_id + h5 + h6 + last_packet + h8 + h9)

    # ----- Lê o payload (só para reduzir a complexidade do entendimento do main)
    def read_payload(self, n): # n = head[5]
        rxBuffer, nRx = self.com1.getData(n)
        return rxBuffer, nRx

    # ----- Cria o pacote de fato
    def make_packet(self, type=b'\x00', payload:bytes=b'', len_packets=b'\x00', h5:bytes=b'\x00') -> bytes:

        head = self.make_head(type=type, len_packets=len_packets, packet_id=self.packetId.to_bytes(1,'big'), h5=h5, last_packet=self.lastpacketId.to_bytes(1,'big'))
        return (head + payload + self.EOP)

    # ----- Envia o handshake (só para reduzir a complexidade do entendimento do main)
    def send_handshake(self,len_packets):     
        self.com1.sendData(np.asarray(self.make_packet(type=self.HANDSHAKE, len_packets=len_packets)))
        
    
    # ----- Verifica se o pacote recebido é um handshake
    # verify_handshake = lambda self, rxBuffer: True if rxBuffer[0] == self.HANDSHAKE else False
    def verify_handshake(self, rxBuffer:bytes) -> bool:
        
        self.status = 1
       
        if  rxBuffer[0].to_bytes(1,'big') == self.HANDSHAKE:
            return True

        return False

    # ----- Envia o acknowledge (reduzir a complexidade do main)
    def send_ack(self):
        self.com1.sendData(np.asarray(self.make_packet(type=self.ACK)))

    # ----- Verifica se o pacote recebido é um acknowledge
    # verify_ack = lambda self, rxBuffer: True if rxBuffer[0] == self.ACK else False
    def verify_ack(self, rxBuffer:bytes) -> bool:
        
        if rxBuffer[0] == self.ACK:
            return True
        
        return False
    # ====================================================

    def get_type(self, rxBuffer:bytes):

        head = rxBuffer[:10] # 10 primeiros itens são o head
     
        h0 = head[0].to_bytes(1,'big')
  
        return h0


    def main(self):
        try:
            print('Iniciou o main')
  

       
            print('Abriu a comunicação')

            self.t0 = calcula_tempo(time.ctime())
            with open(self.IMG, 'rb') as arquivo:
                m= arquivo.read()
            
            
            print('Enviando Handshake:')
   
            payloads, self.lenPackets = self.make_payload_list(m)
            
            self.com1.rx.clearBuffer()
            
            self.send_handshake(self.lenPackets.to_bytes(1,'big'))
   
            rxLen = self.waitBufferLen()
            rxBuffer, nRx = self.com1.getData(rxLen)
            

            if not self.verify_handshake(rxBuffer):

                raise Exception('O Handshake não é um Handshake.')
            else:
                print('*'*98)
                print('\033[92mHandshake recebido\033[0m')

            

            #print(f'quantidade de comandos {n}') 
          
            print(f'quantidade de payloads {len(payloads)}')
         
      
            
       
            #self.com1.sendData(np.asarray(self.make_packet(payload=payloads[self.packetId], len_packets=hex(len_packets))))
            while self.packetId < self.lenPackets:
                susi = len(payloads[self.packetId]).to_bytes(1,'big')
                
           
                #envio de pacotes
                self.com1.sendData(np.asarray(self.make_packet(payload=payloads[self.packetId], len_packets=self.lenPackets.to_bytes(1,'big'),h5=susi)))


                #=========== Erro induzido ===========
                #self.com1.sendData(np.asarray(self.make_packet(payload=payloads[self.packetId+1], len_packets=self.lenPackets.to_bytes(1,'big'),h5=susi)))
                time.sleep(0.1)
                #recebe a resposta do servidor
                rxLen = self.waitBufferLen()
                rxBuffer, nRx = self.com1.getData(rxLen)
              
                self.t2 = calcula_tempo(time.ctime())
                while not rxBuffer.endswith(self.EOP):
                    self.t3 = calcula_tempo(time.ctime())
                    if variacao_tempo(self.t2, self.t3) > 1:
                        break
                    rxLen = self.waitBufferLen()
                    a = self.com1.getData(rxLen)[0]
                    rxBuffer += a
                    time.sleep(0.05)
                    
                    

                

                #--------------- Verifica resposta do server ACK ou Error ---------------
                h0 = self.get_type(rxBuffer)

                if h0 == self.FINAL:
                    print('uhul')
                    break                

                if h0 == self.ERROR:
                    print(f'\033[93mERRO: reenviando pacote {rxBuffer[6]}\033[0m')
                    self.com1.sendData(np.asarray(self.make_packet(payload=payloads[rxBuffer[6]], len_packets=self.lenPackets.to_bytes(1,'big'))))
                    time.sleep(0.1)
                    self.packetId = rxBuffer[6] 
                    rxLen = self.waitBufferLen()
                    rxBuffer, nRx = self.com1.getData(rxLen)
                    time.sleep(0.1)

                #---------------Verifica o Ack enviado pelo servidor para continuar a transmissão---------------------
                if h0 == self.ACK:
                    print('\n\033[92mACK CONFIRMADO\033[0m')
                    self.packetId += 1

                    txSize = self.waitStatus()
                    
                    self.lastpacketId = self.packetId - 1
                
                    # Acknowledge
                    rxLen = self.waitBufferLen()
                    rxBuffer, nRx = self.com1.getData(rxLen)
                    time.sleep(0.1)
            
                    
                    print(f'\033[1mEnviando pacote {self.packetId}\033[0m')
                    print(f'\033[1mPayload tamanho {txSize-14}\033[0m\n')


        # except Exception as erro:
        #     print("ops! :-\\")
        #     print(erro)
        finally:
            print('Comunicação encerrada')
            self.com1.disable()

       

            
    #so roda o main quando for executado do terminal ... se for chamado dentro de outro modulo nao roda
if __name__ == "__main__":
    client = Client()
    client.main()