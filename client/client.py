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
from binascii import crc32
from img import *

class Client:
    def __init__(self):
        self.HANDSHAKE_CLIENT = b'\x01' #----- HandShake do Cliente
        self.HANDSHAKE_SERVER = b'\x02' #----- Confirmação do HandShake pelo Servidor
        self.DATA = b'\x03'             #----- Head para envio de pacotes
        self.ACK = b'\x04'              #----- Confirmação do Pacote pelo Servidor
        self.TIMEOUT = b'\x05'          #----- Cancela a transmissão de dados caso tempo > 20
        self.ERROR = b'\x06'            #----- Mensagem de Erro no head
        self.FINAL = b'\x07'            #----- Confirmação do Servidor que tudo foi enviado
        self.EOP = b'\xAA\xBB\xCC\xDD'  #----- Final da mensagem do pacote
        self.ADDRESS = b'\xf3'          #----- Endereço a ser enviado

        self.timeout2 = False           #----- Para o processo do Cliente

        self.IMG = "img/olhos_fitao.png"#----- Imagem a ser transmitid

        self.os = platform.system().lower()
        self.serialName = '/dev/ttyACM1'#self._findArduino()#-- Encontra a porta do Arduino
        self.com1 = enlace(self.serialName)
        self.com1.enable()

        self.status = 0 #------------ Status do Cliente para calculo do Time Out do HANDSHAKE!
        
        self.t0 = 0 #---------------- Tempo inicial do HandShake
        self.t1 = 0 #---------------- Tempo Final do HandShake
        self.t2 = 0 #---------------- Tempo inicial de comunicação
        self.t3 = 0 #---------------- Tempo Final de Comunicação

        self.crc1 = b'\x00'
        self.crc2 = b'\x00'

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


            if variacao_tempo(self.t0, self.t1) > 5 and self.status == 0:
                if variacao_tempo(self.t2, self.t3)>20:
                    self.logs.write(self._getNow() + '/' + " TIME OUT\n")
                    self.timeout2 = True
                    break
                self.logs.write(self._getNow() + "/" + ' Tentar Reconexão?\n')
                res = input("Tentar reconexão?(s/n) ")
                self.logs.write(self._getNow() + '/' + " sim\n")

                if res.lower() == "s":
                    self.t0 = calcula_tempo(time.ctime())
                    self.send_handshake(num_packets=self.lenPacket.to_bytes(1,'big'))
                    rxLen = self.waitBufferLen()
        return rxLen

    def waitStatus(self):
        txSize = self.com1.tx.getStatus()
        while txSize == 0:
            txSize = self.com1.tx.getStatus()
        return txSize


    def _getNow(self) -> str:
        return datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]

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
    def make_head(self, type=b'\x00', h1=b'\x00', h2=b'\x00', num_packets=b'\x00', packet_id=b'\x00', h5=b'\x00', h6=b'\x00', last_packet=b'\x00'):
        match type:
            case self.DATA:
                return type + h1 + h2 + num_packets + packet_id + h5 + h6 + last_packet + self.crc1 + self.crc2
        return type + h1 + h2 + num_packets + packet_id + h5 + h6 + last_packet + b'\x00' + b'\x00'

    def get_head_info(self, rxBuffer:bytes):
        head = rxBuffer[:10] # 10 primeiros itens são o head

        type_packet = head[0]
        num_packets = head[3] # quantidade de pacotes (int)
        packet_id   = head[4] # id do pacote (int)
        h5          = head[5] # se o tipo for handshake, id do arquivo, senão, tamanho do payload (int)
        h6          = head[6] # pacote para recomeçar quando há erro (int)
        last_packet = head[7] # id do último pacote recebido com sucesso (int)

        return type_packet, num_packets, packet_id, h5, h6, last_packet

    # ----- Cria o pacote de fato
    def make_packet(self, type=b'\x00', payload:bytes=b'', num_packets=b'\x00', h5:bytes=b'\x00') -> bytes:
        if payload:
            crc = crc32(payload).to_bytes(8, 'big')
            crc1 = crc[-2].to_bytes(1, 'big')
            crc2 = crc[-1].to_bytes(1, 'big')
        head = self.make_head(type=type, num_packets=num_packets, packet_id=self.packetId.to_bytes(1,'big'), h5=h5, last_packet=self.lastpacketId.to_bytes(1,'big'))
        return (head + payload + self.EOP)

    # ----- Envia o pacote de dados
    def send_data(self, payloads:list):
        h5 = len(payloads[self.packetId]).to_bytes(1, 'big')
        self.check_sum(payloads[self.packetId])
        data = self.make_packet(type=self.DATA, payload=payloads[self.packetId], num_packets=self.lenPacket.to_bytes(1,'big'),h5=h5)
        self.logs.write(f'{self._getNow()} / Enviado  / {self.get_head_info(data)[0]} / {self.get_head_info(data)[3]+14} / {self.get_head_info(data)[2]+1} / {self.get_head_info(data)[1]} / {self.crc1.hex().split("b")[-1]}{self.crc2.hex().split("b")[-1]}\n')
        self.com1.sendData(np.asarray(data))

    # ----- Envia o timeout
    def send_timeout(self):
        timeout = self.make_packet(type=self.TIMEOUT)
        self.logs.write(f'{self._getNow()} / Enviado  / {self.get_head_info(timeout)[0]} / {self.get_head_info(timeout)[3]+14}\n')
        self.com1.sendData(np.asarray(timeout))

    # ----- Envia o handshake (só para reduzir a complexidade do entendimento do main)
    def send_handshake(self,num_packets):
        hs = self.make_packet(type=self.HANDSHAKE_CLIENT, num_packets=num_packets, h5=self.ADDRESS)
        self.logs.write(f'{self._getNow()} / Enviado  / {self.get_head_info(hs)[0]} / {self.get_head_info(hs)[3]+14}\n')
        self.com1.sendData(np.asarray(hs))
    
    # ----- Verifica se o pacote recebido é um handshake
    def verify_handshake(self, rxBuffer:bytes) -> bool:
        self.status = 1
        if  rxBuffer[0].to_bytes(1,'big') == self.HANDSHAKE_SERVER:
            return True
        return False

    # ----- Cria o CRC do pacote
    def check_sum(self, payload:bytes):
        crc_client = crc32(payload).to_bytes(8, 'big')
        self.crc1 = crc_client[-2].to_bytes(1, 'big')
        self.crc2 = crc_client[-1].to_bytes(1, 'big')
    # ====================================================

    def get_type(self, rxBuffer:bytes):
        if  len(rxBuffer):
            h0 = rxBuffer[0].to_bytes(1,'big')
                
            self.t2 = calcula_tempo(time.ctime())
            while not len(rxBuffer):
                self.t3 = calcula_tempo(time.ctime())
                if variacao_tempo(self.t2, self.t3) > 20:
                    self.timeout2 = True

            return h0
        pass


    def main(self):
        try:
            print('Iniciou o main')
            self.logs.write(f'{self._getNow()} / Iniciou o main\n')

            print('Abriu a comunicação')
            self.logs.write(f'{self._getNow()} / Abriu a comunicação\n')

            self.t0 = calcula_tempo(time.ctime())
            self.t2 = calcula_tempo(time.ctime())
            with open(self.IMG, 'rb') as arquivo:
                m = arquivo.read()
            
            
            print('Enviando Handshake:')
   
            payloads, self.lenPacket = self.make_payload_list(m)
            
            self.com1.rx.clearBuffer()
            
            self.send_handshake(self.lenPacket.to_bytes(1,'big'),)

            rxLen = self.waitBufferLen()
            rxBuffer, nRx = self.com1.getData(rxLen)
            

            if self.verify_handshake(rxBuffer):
                print('*'*98)
                print('\033[92mHandshake recebido\033[0m')
                self.logs.write(f'{self._getNow()} / Recebido / {self.get_head_info(rxBuffer)[0]} / {self.get_head_info(rxBuffer)[3]+14}\n')

            while self.packetId < self.lenPacket:
                self.send_data(payloads)
                time.sleep(0.05)
                txSize = self.waitStatus()

                #=========== Erro induzido ===========
                # self.com1.sendData(np.asarray(self.make_packet(payload=payloads[self.packetId+1], num_packets=self.lenPacket.to_bytes(1,'big'),h5=h5)))
                time.sleep(0.05)
                #recebe a resposta do servidor
                rxLen = self.waitBufferLen()
                rxBuffer, nRx = self.com1.getData(rxLen)
                time.sleep(0.05)

                self.t2 = calcula_tempo(time.ctime())
                while not rxBuffer.endswith(self.EOP):
                    self.t3 = calcula_tempo(time.ctime())
                    if variacao_tempo(self.t2, self.t3) > 20:
                        self.send_timeout()
                        break
                    rxLen = self.waitBufferLen()
                    a = self.com1.getData(rxLen)[0]
                    rxBuffer += a
                    time.sleep(0.05)
                    
                #--------------- Verifica resposta do server ACK ou Error ---------------
                h0 = self.get_type(rxBuffer)
                self.logs.write(f'{self._getNow()} / Recebido / {self.get_head_info(rxBuffer)[0]} / {self.get_head_info(rxBuffer)[3]+14}\n')

                match h0:
                    case self.ERROR:
                        print(f'\033[93mERRO: reenviando pacote {rxBuffer[6]}\033[0m')

                        self.packetId = rxBuffer[6]

                        rxLen = self.waitBufferLen()
                        rxBuffer, nRx = self.com1.getData(rxLen)
                        time.sleep(0.05)
                    
                    case self.ACK:
                        self.lastpacketId = self.packetId
                        self.packetId += 1
                        
                        rxLen = self.waitBufferLen()
                        rxBuffer, nRx = self.com1.getData(rxLen)
                        time.sleep(0.05)
                
                        
                        print(f'\033[1mEnviando pacote {self.packetId}\033[0m')
                        
                        print(f'\033[1mPayload tamanho {txSize-14}\033[0m\n')

                    case _:
                        break

                if self.timeout2:
                    self.send_timeout()
                    break
        
        # except:
        #     pass

        finally:
            self.com1.disable()

            print("-------------------------")
            self.logs.write(f'{self._getNow()} / -------------------------\n')
            print('Comunicação encerrada')
            self.logs.write(f'{self._getNow()} / Comunicação encerrada')

            self.logs.close()
            
    #so roda o main quando for executado do terminal ... se for chamado dentro de outro modulo nao roda
if __name__ == "__main__":
    client = Client()
    client.main()