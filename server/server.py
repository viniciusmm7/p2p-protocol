#####################################################
#            Camada Física da Computação            #
#                     Carareto                      #
#                    23/09/2022                     #
#                      Server                       #
#####################################################


from enlace import *
from datetime import datetime
import time, platform
import numpy as np
from binascii import crc32

# para saber a sua porta, execute no terminal :
# python3 -m serial.tools.list_ports

# para autorizar:
# sudo chmod a+rw /dev/ttyACM0
# serialName = "/dev/ttyACM0"           # Ubuntu (variacao de)

class Server:
    def __init__(self):
        self.HANDSHAKE_CLIENT = b'\x01' # Cliente  -> Servidor
        self.HANDSHAKE_SERVER = b'\x02' # Servidor -> Cliente
        self.DATA = b'\x03'             # Cliente  -> Servidor
        self.ACK = b'\x04'              # Servidor -> Cliente
        self.TIMEOUT = b'\x05'          # Cliente  -> Servidor
        self.ERROR = b'\x06'            # Servidor -> Cliente
        self.FINAL = b'\x07'            # Servidor -> Cliente
        self.EOP = b'\xAA\xBB\xCC\xDD'
        self.ADDRESS = b'\xf3' # Um endereço qualquer para identificação do servidor

        self.os = platform.system().lower()
        self.serialName = '/dev/ttyACM0'
        self.com1 = enlace(self.serialName)
        self.com1.enable()

        self.offline = True
        self.timeout2 = False

        self.data = b''
        self.crc1 = b'\x00'
        self.crc2 = b'\x00'
        
        self.packetId = 0
        self.lastpacketId = 0
        self.numPackets = 0
        self.h5 = 0

        self.t1 = None # Timer longo para reenvio de ack (2 segundos)
        self.t3 = None # suporte de t1

        self.t2 = None # Timer curto para timeout de ack (20 segundos)
        self.t4 = None # suporte de t2

        # Arquivo de logs aberto e pronto para escrever
        self.logs = open('serverLogs.txt', 'w')

    # ----- Método para calcular os tempos
    def _calcTime(self, ctime:str) -> list:
        """
        private method to convert hours, minutes and
        seconds to a time list in seconds

        ATTRIBUTES: ctime: str (current time)

        RETURNS: t: list
        """
        t = []

        hour = int(ctime.split()[3][:2]) * 3600
        minute = int(ctime.split()[3][3:5]) * 60
        second = int(ctime.split()[3][6:])

        t.append(hour)
        t.append(minute)
        t.append(second)
        
        return t

    # ----- Método para calcular a variação de tempo
    def _timeVar(self, first:list, second:list) -> int:
        """
        private method to calculate the time variation

        ATTRIBUTES: first: list (return of _calcTime)
                    second: list (return of _calcTime)

        RETURNS: var: int
        """
        var = (second[0] - first[0]) + (second[1] - first[1]) + (second[2] - first[2]) 
        return var

    def _getNow(self) -> str:
        return datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]

    # ===== MÉTODOS PARA EVITAR REPETIÇÃO DE CÓDIGO =====
    def waitBufferLen(self, first=False) -> int:
        """
        method used in order to reduce the
        amount of code repetition

        ATTRIBUTES: void

        RETURNS: rxLen: int
        """

        if self.t1 is None:
            self.t1 = self._calcTime(time.ctime())
        if self.t2 is None:
            self.t2 = self._calcTime(time.ctime())

        rxLen = self.com1.rx.getBufferLen()
        while not rxLen:
            rxLen = self.com1.rx.getBufferLen()
            self.t3 = self._calcTime(time.ctime())
            self.t4 = self._calcTime(time.ctime())

            if not first:
                if self._timeVar(self.t2, self.t4) > 20:
                    self.offline = True
                    self.timeout2 = True
                    self.send_timeout()
                    return -1
                    # raise Exception('Timeout')

                elif self._timeVar(self.t1, self.t3) > 2:
                    self.send_ack(num_packets=self.numPackets, h5=self.h5)
                    self.t1 = self._calcTime(time.ctime())
            # time.sleep(1)
        return rxLen

    # ====================================================

    # ========= MÉTODOS PARA ADMINISTRAR PACOTES =========

    # ----- Quebrar os dados em payloads de até 114 bytes
    def make_payload_list(self, data) -> list:
        """
        method that creates a payload list whose
        items are multiple payloads divided into
        up to 114 bytes

        ATTRIBUTES: data (the complete data)

        RETURNS: payload_list: list
                 len(payload_list): int
        """
        limit = 114
        payload_list = []

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

    # ----- Lê o payload (só para reduzir a complexidade do entendimento do main)
    def read_payload(self, rxBuffer:bytes):
        h5 = rxBuffer[5]+10
        payload = rxBuffer[10:h5]
        self.data += payload
        return payload

    def get_head_info(self, rxBuffer:bytes):
        head = rxBuffer[:10] # 10 primeiros itens são o head

        type_packet = head[0]
        num_packets = head[3] # quantidade de pacotes (int)
        packet_id   = head[4] # id do pacote (int)
        h5          = head[5] # se o tipo for handshake, id do arquivo, senão, tamanho do payload (int)
        h6          = head[6] # pacote para recomeçar quando há erro (int)
        last_packet = head[7] # id do último pacote recebido com sucesso (int)
        crc1, crc2  = head[8], head[9] # dois bytes de crc32

        return type_packet, num_packets, packet_id, h5, h6, last_packet, crc1, crc2

    # ----- Cria o pacote de fato
    def make_packet(self, type=b'\x00', payload:bytes=b'', num_packets=b'\x00', h5=b'\x00', h6=b'\x00') -> bytes:
        if payload:
            self.check_sum(payload)
        head = self.make_head(type=type, num_packets=num_packets, packet_id=self.packetId.to_bytes(1, 'big'), h5=h5, h6=h6, last_packet=self.lastpacketId.to_bytes(1, 'big'))
        return head + payload + self.EOP

    # ----- Envia o handshake (só para reduzir a complexidade do entendimento do main)
    def send_handshake(self):
        hs = self.make_packet(type=self.HANDSHAKE_SERVER)
        self.logs.write(f'{self._getNow()} / Enviado  / {self.get_head_info(hs)[0]} / {self.get_head_info(hs)[3]+14}\n')
        self.com1.sendData(np.asarray(hs))

    # ----- Verifica se o pacote recebido é um handshake
    def verify_handshake(self, rxBuffer:bytes) -> bool:
        if rxBuffer[0].to_bytes(1, 'big') == self.HANDSHAKE_CLIENT and rxBuffer[5].to_bytes(1, 'big') == self.ADDRESS:
            return True
        return False

    # ----- Cria o CRC do pacote
    def check_sum(self, payload:bytes):
        crc_server = crc32(payload).to_bytes(8, 'big')
        self.crc1 = crc_server[-2].to_bytes(1, 'big')
        self.crc2 = crc_server[-1].to_bytes(1, 'big')

    # ----- Envia o acknowledge (reduzir a complexidade do main)
    def send_ack(self, num_packets:int, h5:int):
        ack = self.make_packet(type=self.ACK, num_packets=num_packets.to_bytes(1, 'big'), h5=h5.to_bytes(1, 'big'))
        print('ACK:', ack)
        self.logs.write(f'{self._getNow()} / Enviado  / {self.get_head_info(ack)[0]} / {self.get_head_info(ack)[3]+14}\n')
        self.com1.sendData(np.asarray(ack))

    # ----- Envia o timeout
    def send_timeout(self):
        timeout = self.make_packet(type=self.TIMEOUT)
        self.logs.write(f'{self._getNow()} / Enviado  / {self.get_head_info(timeout)[0]} / {self.get_head_info(timeout)[3]+14}\n')
        self.com1.sendData(np.asarray(timeout))
        # print('TIMEOUT ENVIADO')

    # ----- Envia o erro
    def send_error(self, h6:int=None):
        error = self.make_packet(type=self.ERROR, h6=h6.to_bytes(1, 'big'))
        self.logs.write(f'{self._getNow()} / Enviado  / {self.get_head_info(error)[0]} / {self.get_head_info(error)[3]+14}\n')
        self.com1.sendData(np.asarray(error))
        # print('ERRO ENVIADO')

    # ----- Envia mensagem final
    def send_final(self):
        final = self.make_packet(type=self.FINAL)
        txSize = self.com1.tx.getStatus()
        while not txSize or txSize != 14:
            txSize = self.com1.tx.getStatus()
        final = self.make_packet(type=self.FINAL)
        # print('FINAL:', final)
        self.com1.sendData(np.asarray(final))

    # ====================================================

    def main(self):
        try:
            print('Iniciou o main')
            self.logs.write(f'{self._getNow()} / Iniciou o main\n')
            
            print('Abriu a comunicação')
            self.logs.write(f'{self._getNow()} / Abriu a comunicação\n')

            # ===== HANDSHAKE
            # enquanto não recebe nada, fica esperando com sleeps de 1 sec
            rxLen = self.waitBufferLen(first=True) # <recebeu msg t1>
            
            rxBuffer, nRx = self.com1.getData(rxLen)

            # verifica se a mensagem termina com EOP
            while not rxBuffer.endswith(self.EOP):
                rxLen = self.waitBufferLen()
                a = self.com1.getData(rxLen)[0]
                rxBuffer += a
                time.sleep(0.05)
            
            while not self.verify_handshake(rxBuffer):
                # dentro do verify_handshake ele já verifica o endereço
                time.sleep(1)

            self.offline = False # [ocioso = false]
            time.sleep(1) # [sleep 1 sec]

            print('Handshake recebido')
            self.logs.write(f'{self._getNow()} / Recebido / {self.get_head_info(rxBuffer)[0]} / {self.get_head_info(rxBuffer)[3]+14}\n')

            # Quantidade de pacotes de payload
            self.numPackets = self.get_head_info(rxBuffer)[1]

            # [envia msg t2]
            self.send_handshake()
            time.sleep(0.05)
            print('Enviou o Handshake\n')
            # ===== END HANDSHAKE

            # ===== DADOS
            while self.packetId < self.numPackets and not self.offline: # se self.offline, encerra
                
                rxLen = self.waitBufferLen()
                if rxLen < 0:
                    break

                rxBuffer, nRx = self.com1.getData(rxLen)
                # Enquanto o pacote não estiver completo, concatena
                while not rxBuffer.endswith(self.EOP):
                    rxLen = self.waitBufferLen()
                    a = self.com1.getData(rxLen)[0]
                    rxBuffer += a
                    time.sleep(0.05)
                    print('\033[93mAguardando EOP...\033[0m\n')

                self.check_sum(self.read_payload(rxBuffer))

                # Recebendo dados calcula o t1, usado para reenvio
                self.t1 = self._calcTime(time.ctime())
                # Recebendo dados calcula o t2, usado para timeout
                self.t2 = self._calcTime(time.ctime())

                packet_type, num_packets, packet_id, self.h5, _, last_packet, crc1, crc2 = self.get_head_info(rxBuffer)
                
                match packet_type.to_bytes(1, 'big'):
                    case self.DATA:
                        self.logs.write(f'{self._getNow()} / Recebido / {packet_type} / {self.h5+14} / {packet_id+1} / {num_packets} / {crc1.to_bytes(1, "big").hex().split("b")[-1]}{crc2.to_bytes(1, "big").hex().split("b")[-1]}\n')
                    
                    case self.TIMEOUT:
                        self.logs.write(f'{self._getNow()} / Recebido / {packet_type} / {self.h5+14}\n')
                        break

                    case _:
                        self.logs.write(f'{self._getNow()} / Recebido / {packet_type} / {self.h5+14}\n')

                # ===== ERROS
                h6 = self.packetId
                # Verificação de id de pacote, se for True, é um erro
                if packet_id != self.packetId:
                    # ENVIAR ERRO
                    print('\033[91m[ERRO] PACOTE INCORRETO\033[0m')
                    print('id do cliente:', packet_id)
                    print('id esperado do server:', self.packetId)
                    print()
                    self.send_error(h6)

                # Verificando se o tamanho do payload está correto
                elif self.h5 != rxLen - 14:
                    # ENVIAR ERRO
                    print('\033[91m[ERRO] TAMANHO INCORRETO DO PAYLOAD\033[0m')
                    print('h5 do cliente:', self.h5)
                    print('tamanho do payload calculado:', rxLen-14)
                    print()
                    self.send_error(h6)

                elif self.crc1 != crc1.to_bytes(1, 'big') or self.crc2 != crc2.to_bytes(1, 'big'):
                    # ENVIAR ERRO
                    print('\033[91m[ERRO] CHECKSUM INCORRETO\033[0m')
                    print()
                    self.send_error(h6)
                # ===== END ERROS

                elif self.h5 == rxLen - 14 and self.packetId == packet_id and packet_type.to_bytes(1, 'big') == self.DATA:
                    # ENVIAR ACK
                    print('\033[92mRecebimento correto\033[0m\n')
                    self.send_ack(num_packets=self.numPackets, h5=self.h5)
                    self.read_payload(rxBuffer)
                    self.packetId += 1
                    self.t1 = self._calcTime(time.ctime())
                
                self.lastpacketId = h6

            # ===== MENSAGEM FINAL
            self.send_final()
            # ===== END MSG FINAL

        # except:
        #     pass

        finally:
            print("-------------------------")
            self.logs.write(f'{self._getNow()} / -------------------------\n')
            print("Comunicação encerrada")
            self.logs.write(f'{self._getNow()} / Comunicação encerrada')

            self.com1.disable()

            copia = 'olhos_fitaocopia.png'
            with open(copia, 'wb') as f:
                f.write(self.data)
                f.close()

            self.logs.close()


if __name__ == "__main__":
    server = Server()
    server.main()