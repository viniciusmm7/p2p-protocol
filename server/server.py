#####################################################
#            Camada Física da Computação            #
#                     Carareto                      #
#                    23/09/2022                     #
#                      Server                       #
#####################################################


from enlace import *
import time, platform, serial.tools.list_ports
import numpy as np

# para saber a sua porta, execute no terminal :
# python3 -m serial.tools.list_ports

# para autorizar:
# sudo chmod a+rw /dev/ttyACM0
# serialName = "/dev/ttyACM0"           # Ubuntu (variacao de)

class Server:
    def __init__(self):
        self.HANDSHAKE_CLIENT = b'\x01'
        self.HANDSHAKE_SERVER = b'\x02'
        self.DATA = b'\x03'
        self.ACK = b'\x04'
        self.TIMEOUT = b'\x05'
        self.ERROR = b'\x06'
        self.FINAL = b'\x07'
        self.EOP = b'\xAA\xBB\xCC\xDD'
        self.ADDRESS = b'\xf3' # Um endereço qualquer para identificação do servidor

        self.os = platform.system().lower()
        self.serialName = '/dev/ttyACM0'#self._findArduino()
        self.com1 = enlace(self.serialName)
        self.com1.enable()

        self.offline = True

        self.data = b''
        
        self.packetId = 0
        self.lastpacketId = 0
        self.lenPacket = 0
        self.h5 = 0

        self.t1 = 0 # Timer longo para reenvio de ack (2 segundos)
        self.t3 = 0 # suporte de t1

        self.t2 = 0 # Timer curto para timeout de ack (20 segundos)
        self.t4 = 0 # suporte de t2

        # Arquivo de logs aberto e pronto para escrever
        self.logs = open('serverLogs.txt', 'w')


    # ----- Método para a primeira porta com arduíno
    #       se tiver mais de uma (sozinho, por exemplo)
    def _findArduino(self) -> str:
        """
        private method to finding Arduino port
        it was not working properly, so it's hard coded

        ATTRIBUTES: void

        RETURNS: result[0]: str (list item)
        """
        result = []
        ports = list(serial.tools.list_ports.comports())
        c = 1
        for p in ports:
            result.append(f'/dev/ttyACM{c}')
            c += 1
        return result[0]

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
    def _timeVar(first:list, second:list) -> int:
        """
        private method to calculate the time variation

        ATTRIBUTES: first: list (return of _calcTime)
                    second: list (return of _calcTime)

        RETURNS: var: int
        """
        var = (second[0] - first[0]) + (second[1] - first[1]) + (second[2] - first[2]) 
        return var

    # ===== MÉTODOS PARA EVITAR REPETIÇÃO DE CÓDIGO =====
    def waitBufferLen(self) -> int:
        """
        method used in order to reduce the
        amount of code repetition

        ATTRIBUTES: void

        RETURNS: rxLen: int
        """
        rxLen = self.com1.rx.getBufferLen()
        while rxLen == 0:
            rxLen = self.com1.rx.getBufferLen()
            self.t4 = self._calcTime(time.ctime())
            if self._timeVar(self.t2, self.t4) > 20:
                self.offline = True
                self.send_timeout()
                pass
            if self._timeVar(self.t1, self.t3) > 2:
                self.send_ack(len_packets=self.lenPacket, h5=self.h5)
                self.t1 = self._calcTime(time.ctime())
            time.sleep(1)
        return rxLen

    def waitStatus(self) -> int:
        """
        method used in order to reduce the
        amount of code repetition

        ATTRIBUTES: void

        RETURNS: txSize: int
        """
        txSize = self.com1.tx.getStatus()
        while txSize == 0:
            txSize = self.com1.tx.getStatus()
        return txSize
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
    def make_head(self, type=b'\x00', h1=b'\x00', h2=b'\x00', len_packets=b'\x00', packet_id=b'\x00', h5=b'\x00', h6=b'\x00', last_packet=b'\x00', h8=b'\x00', h9=b'\x00'):
        return type + h1 + h2 + len_packets + packet_id + h5 + h6 + last_packet + h8 + h9

    # ----- Lê o payload (só para reduzir a complexidade do entendimento do main)
    def read_payload(self, rxBuffer:bytes):
        h5 = rxBuffer[5]+10
        payload = rxBuffer[10:h5]
        # print('HEAD DO READPAYLOAD::', rxBuffer[:10])
        self.data += payload
        return payload

    def get_head_info(self, rxBuffer:bytes):
        head = rxBuffer[:10] # 10 primeiros itens são o head

        len_packets = head[3] # quantidade de pacotes (int)
        packet_id   = head[4] # id do pactote (int)
        h5          = head[5] # se o tipo for handshake, id do arquivo, senão, tamanho do payload (int)
        h6          = head[6] # pacote para recomeçar quando há erro (int)
        last_packet = head[7] # id do último pacote recebido com sucesso (int)

        return len_packets, packet_id, h5, h6, last_packet

    # ----- Cria o pacote de fato
    def make_packet(self, type=b'\x00', payload:bytes=b'', len_packets=b'\x00', h5=b'\x00', h6=b'\x00') -> bytes:
        head = self.make_head(type=type, len_packets=len_packets, packet_id=self.packetId.to_bytes(1, 'big'), h5=h5, h6=h6, last_packet=self.lastpacketId.to_bytes(1, 'big'))
        return head + payload + self.EOP

    # ----- Envia o handshake (só para reduzir a complexidade do entendimento do main)
    def send_handshake(self):
        hs = self.make_packet(type=self.HANDSHAKE_SERVER)
        self.com1.sendData(np.asarray(hs))

    # ----- Verifica se o pacote recebido é um handshake
    # verify_handshake = lambda self, rxBuffer: True if rxBuffer[0] == self.HANDSHAKE_CLIENT else False
    def verify_handshake(self, rxBuffer:bytes) -> bool:
        if rxBuffer[0].to_bytes(1, 'big') == self.HANDSHAKE_CLIENT and rxBuffer[5] == self.ADDRESS:
            return True
        return False

    # ----- Envia o acknowledge (reduzir a complexidade do main)
    def send_ack(self, len_packets:int, h5:int):
        ack = self.make_packet(type=self.ACK, len_packets=len_packets.to_bytes(1, 'big'), h5=h5.to_bytes(1, 'big'))
        print('ACK:', ack)
        self.logs.write(f'ACK: {ack}\n\n')
        self.com1.sendData(np.asarray(ack))

    # ----- Verifica se o pacote recebido é um acknowledge
    # verify_ack = lambda self, rxBuffer: True if rxBuffer[0] == self.ACK else False
    def verify_ack(self, rxBuffer:bytes) -> bool:
        if rxBuffer[0].to_bytes(1, 'big') == self.ACK:
            return True
        return False

    # ----- Envia o timeout
    def send_timeout(self):
        timeout = self.make_packet(type=self.TIMEOUT)
        self.com1.sendData(np.asarray(timeout))

    # ----- Envia o erro
    def send_error(self, h6:int=None):
        error = self.make_packet(type=self.ERROR, h6=h6.to_bytes(1, 'big'))
        self.com1.sendData(np.asarray(error))

    # ----- Envia mensagem final
    def send_final(self):
        final = self.make_packet(type=self.FINAL)
        txSize = self.com1.tx.getStatus()
        while txSize == 0 or txSize != 14:
            txSize = self.com1.tx.getStatus()
        final = self.make_packet(type=self.FINAL)
        print('FINAL:', final)
        self.com1.sendData(np.asarray(final))

    # ====================================================

    def main(self):
        try:
            print('Iniciou o main')
            self.logs.write('Iniciou o main\n')
            
            print('Abriu a comunicação')
            self.logs.write('Abriu a comunicação\n')

            # ===== HANDSHAKE
            # enquanto não recebe nada, fica esperando com sleeps de 1 sec
            rxLen = self.waitBufferLen() # <recebeu msg t1>
            
            rxBuffer, nRx = self.com1.getData(rxLen)

            # verifica se a mensagem termina com EOP
            while not rxBuffer.endswith(self.EOP):
                rxLen = self.waitBufferLen()
                a = self.com1.getData(rxLen)[0]
                rxBuffer += a
                time.sleep(0.05)
            
            while not self.verify_handshake(rxBuffer):
                # dentro do verify_handshake ele já verifica o endereço
                print('O Handshake não é um Handshake')
                self.logs.write('O Handshake não é um Handshake\n')

            self.offline = False # [ocioso = false]
            time.sleep(1) # [sleep 1 sec]

            print('Handshake recebido')
            self.logs.write('Handshake recebido\n')

            # Quantidade de pacotes de payload
            self.lenPacket = self.get_head_info(rxBuffer)[0]

            # [envia msg t2]
            self.send_handshake()
            print('Enviou o Handshake\n')
            self.logs.write('Enviou o Handshake\n\n')
            # ===== END HANDSHAKE

            # ===== DADOS
            while self.packetId < self.lenPacket and not self.offline: # se self.offline, encerra
                rxLen = self.waitBufferLen()
                rxBuffer, nRx = self.com1.getData(rxLen)
                # Enquanto o pacote não estiver completo, concatena
                while not rxBuffer.endswith(self.EOP):
                    rxLen = self.waitBufferLen()
                    a = self.com1.getData(rxLen)[0]
                    rxBuffer += a
                    time.sleep(0.05)
                    print('\033[93mAguardando EOP...\033[0m\n')
                    self.logs.write('Aguardando EOP...\n\n')

                # Recebendo dados calcula o t1, usado para reenvio
                self.t1 = self._calcTime(time.ctime())
                # Recebendo dados calcula o t2, usado para timeout
                self.t2 = self._calcTime(time.ctime())

                _, packet_id, self.h5, _, last_packet = self.get_head_info(rxBuffer)
                
                # ===== ERROS
                h6 = self.packetId
                # Verificação de id de pacote, se for True, é um erro
                if packet_id != self.packetId:
                    # ENVIAR ERRO
                    print('\033[91m[ERRO] PACOTE INCORRETO\033[0m')
                    self.logs.write('[ERRO] PACOTE INCORRETO\n')
                    print('id do cliente:', packet_id)
                    self.logs.write(f'id do client: {packet_id}\n')
                    print('id esperado do server:', self.packetId)
                    print()
                    self.logs.write(f'id esperado pelo server: {self.packetId}\n\n')
                    
                    self.send_error(h6)

                # Verificando se o tamanho do payload está correto
                elif self.h5 != rxLen - 14:
                    # ENVIAR ERRO
                    print('\033[91m[ERRO] TAMANHO INCORRETO DO PAYLOAD\033[0m')
                    self.logs.write('[ERRO] TAMANHO INCORRETO DO PAYLOAD\n')
                    print('h5 do cliente:', self.h5)
                    self.logs.write(f'h5 do client: {self.h5}\n')
                    print('tamanho do payload calculado:', rxLen-14)
                    print()
                    self.logs.write(f'tamanho do payload calculado: {rxLen-14}\n\n')
                    
                    self.send_error(h6)
                # ===== END ERROS

                else:
                    # ENVIAR ACK
                    print('\033[92mEnvio correto\033[0m')
                    self.logs.write('Envio correto\n')
                    self.send_ack(len_packets=self.lenPacket, h5=self.h5)
                    self.read_payload(rxBuffer)
                    print()
                    self.packetId += 1
                    self.t1 = self._calcTime(time.ctime())
        

            # ===== MENSAGEM FINAL
            self.send_final()
            # ===== END MSG FINAL


            # Encerra comunicação
            print("-------------------------")
            self.logs.write('-------------------------\n')
            print("Comunicação encerrada")
            self.logs.write('Comunicação encerrada')
 
        # except Exception as erro:
        #     print("ops! :-\\")
        #     print(erro)

        finally:
            self.com1.disable()

            copia = 'olhos_fitaocopia.png'
            with open(copia, 'wb') as f:
                f.write(self.data)
                f.close()

            self.logs.close()


if __name__ == "__main__":
    server = Server()
    server.main()