#####################################################
# ----------Camada Física da Computação-------------#
#------------------Carareto-------------------------#
#-----------------23/09/2022------------------------#
#------------------Cliente--------------------------#
#####################################################


from enlace import *
from datetime import datetime
import time, platform, serial.tools.list_ports
import numpy as np
from comandos import *
from img import *

class Client:
    def __init__(self):
        self.HANDSHAKE_CLIENT = b'\x01' #----- HandShake do Cliente
        self.HANDSHAKE_SERVER = b'\x02' #----- Confirmação do HandShake pelo Servidor
        self.DATA = b'\x03'             #----- Head para envio de pacotes
        self.ACK = b'\x04'              #----- Confirmação do Pacote pelo Servidor
        self.TIMEOUT = b'\x05'          #----- Cancela a transmissão de dados caso tempo > 20
        self.EOP = b'\xAA\xBB\xCC\xDD'  #----- Final da mensagem do pacote
        self.ERROR = b'\x06'            #----- Mensagem de Erro no head
        self.FINAL = b'\x07'            #----- Confirmação do Servidor que tudo foi enviado
        self.ADDRESS = b'\xf3'          #----- Endereço a ser enviado

        self.TIMEOUT2 = False          #----- Para o processo do Cliente

        self.IMG = "img/olhos_fitao.png"#----- Imagem a ser transmitid

        self.os = platform.system().lower()
        self.serialName = self._findArduino()#-- Encontra a porta do Arduino
        self.com1 = enlace(self.serialName)
        self.com1.enable()

        self.status = 0 #------------ Status do Cliente para calculo do Time Out do HANDSHAKE!
        
        self.t0 = 0 #---------------- Tempo inicial do HandShake
        self.t1 = 0 #---------------- Tempo Final do HandShake
        self.t2 = 0 #---------------- Tempo inicial de comunicação
        self.t3 = 0 #---------------- Tempo Final de Comunicação


        self.packetId = 0 #--------- Id do pacote enviado
        self.lastpacketId = 0 #----- Id anterior do pacote enviado
        self.lenPacket = 0 #------- Tamanho do Pacote

        
        self.logs = open('clientLogs.txt', 'w') #------- Arquivo de logs aberto e pronto para escrever

        
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
            self.t3 = calcula_tempo(time.ctime())


            print(variacao_tempo(self.t2, self.t3)) #---Time OUT


            if variacao_tempo(self.t0, self.t1) > 5 and self.status == 0:
                if variacao_tempo(self.t2, self.t3)>20:
                    print("TIME OUT")
                    self.TIMEOUT2 = True
                    break
                res = input("Tentar reconexção?(s/n) ")
                

                if res.lower() == "s":
                    self.t0 = calcula_tempo(time.ctime())
                    self.send_handshake(len_packets=self.lenPacket.to_bytes(1,'big'))
                    rxLen = self.waitBufferLen()
                else:
                    raise Exception('Time out. Servidor não respondeu.')
            if rxLen != 0 or variacao_tempo(self.t2, self.t3)>20:
                print("TIME OUT")
                self.TIMEOUT2 = True
                break
        return rxLen

    def waitStatus(self):
        txSize = self.com1.tx.getStatus()
        while txSize == 0:
            txSize = self.com1.tx.getStatus()
        return txSize

    def write_log(self, rxBuffer:bytes):
        self.logs.write(f'{datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]} / ')

        sended = [self.HANDSHAKE_CLIENT, self.DATA, self.TIMEOUT]
        received = [self.HANDSHAKE_SERVER, self.ACK, self.ERROR, self.FINAL]

        if rxBuffer[0] in received:
            self.logs.write(f'receb / {int.from_bytes(rxBuffer[0], "big")} / {len(rxBuffer)}')
            if rxBuffer[0] == self.DATA:
                self.logs.write(f' / {self.packetId} / {self.lenPacket}')

        elif rxBuffer[0] in sended:
            self.logs.write(f'envio / {int.from_bytes(rxBuffer[0], "big")} / {len(rxBuffer)}')

        self.logs.write('\n')

    # ====================================================

    # ========= MÉTODOS PARA ADMINISTRAR PACOTES =========

    # ----- Quebrar os dados em payloads de até 114 bytes



    #------- Divide o arquivo em pacotes com 114 bytes de tamanho
    def make_payload_list(self, data):  
        limit = 114
        payload_list = []
        cont = 0 

        while len(data) > 0:
            if limit > len(data):
                limit = len(data)
            payload_list.append(data[:limit])
            data = data[limit:]
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
        self.com1.sendData(np.asarray(self.make_packet(type=self.HANDSHAKE_CLIENT, len_packets=len_packets)))
        
    
    # ----- Verifica se o pacote recebido é um handshake
    # verify_handshake = lambda self, rxBuffer: True if rxBuffer[0] == self.HANDSHAKE else False
    def verify_handshake(self, rxBuffer:bytes) -> bool:
        
        self.status = 1
       
        if  rxBuffer[0].to_bytes(1,'big') == self.HANDSHAKE_SERVER:
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
        print(rxBuffer)
        h0 = rxBuffer[0].to_bytes(1,'big')

        self.t3 = calcula_tempo(time.ctime())
        while rxBuffer== b'':
            print('Timing')
            self.t4 = calcula_tempo(time.ctime())
            if variacao_tempo(self.t3,self.t4) > 20:
                self.TIMEOUT2 == True

        return h0


    def main(self):
        try:
            print('Iniciou o main')
  

       
            print('Abriu a comunicação')

            self.t0 = calcula_tempo(time.ctime())
            self.t2 = calcula_tempo(time.ctime())
            with open(self.IMG, 'rb') as arquivo:
                m = arquivo.read()
            
            
            print('Enviando Handshake:')
   
            payloads, self.lenPacket = self.make_payload_list(m)
            
            self.com1.rx.clearBuffer()
            
            self.send_handshake(self.lenPacket.to_bytes(1,'big'))
   
            rxLen = self.waitBufferLen()
            rxBuffer, nRx = self.com1.getData(rxLen)
            

            if not self.verify_handshake(rxBuffer):

                raise Exception('O Handshake não é um Handshake.')
            else:
                print('*'*98)
                print('\033[92mHandshake recebido\033[0m')
                self.logs.write('Handshake recebido\n')  

            

            #print(f'quantidade de comandos {n}') 
          
            print(f'quantidade de payloads {len(payloads)}')
            self.logs.write(f'quantidade de payloads {len(payloads)}\n')
         
      
            
       
            #self.com1.sendData(np.asarray(self.make_packet(payload=payloads[self.packetId], len_packets=hex(len_packets))))
            while self.packetId < self.lenPacket:
                susi = len(payloads[self.packetId]).to_bytes(1,'big')
                
           
                #envio de pacotes
                self.com1.sendData(np.asarray(self.make_packet(payload=payloads[self.packetId], len_packets=self.lenPacket.to_bytes(1,'big'),h5=susi)))


                #=========== Erro induzido ===========
                #self.com1.sendData(np.asarray(self.make_packet(payload=payloads[self.packetId+1], len_packets=self.lenPacket.to_bytes(1,'big'),h5=susi)))
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
                    self.logs.write(f'ERRO: reenviando pacote {rxBuffer[6]}\n')
                    self.com1.sendData(np.asarray(self.make_packet(payload=payloads[rxBuffer[6]], len_packets=self.lenPacket.to_bytes(1,'big'))))
                    time.sleep(0.1)
                    self.packetId = rxBuffer[6] 
                    rxLen = self.waitBufferLen()
                    rxBuffer, nRx = self.com1.getData(rxLen)
                    time.sleep(0.1)

                #---------------Verifica o Ack enviado pelo servidor para continuar a transmissão---------------------
                if h0 == self.ACK:
                    print('\n\033[92mACK CONFIRMADO\033[0m')
                    self.logs.write('ACK CONFIRMADO\n')
                    self.packetId += 1

                    txSize = self.waitStatus()
                    
                    self.lastpacketId = self.packetId - 1
                
                    # Acknowledge
                    rxLen = self.waitBufferLen()
                    rxBuffer, nRx = self.com1.getData(rxLen)
                    time.sleep(0.1)
            
                    
                    print(f'\033[1mEnviando pacote {self.packetId}\033[0m')
                    self.logs.write(f'Enviando pacote {self.packetId}')
                    print(f'\033[1mPayload tamanho {txSize-14}\033[0m\n')
                    self.logs.write(f'Payload tamanho {txSize-14}')
                
                if self.TIMEOUT2 == True:
                    break


        # except Exception as erro:
        #     print("ops! :-\\")
        #     print(erro)
        
        finally:
            print('Comunicação encerrada')
            self.logs.write('Comunicação encerrada')
            self.com1.disable()
            self.logs.close()
            
    #so roda o main quando for executado do terminal ... se for chamado dentro de outro modulo nao roda
if __name__ == "__main__":
    client = Client()
    client.main()