"""Protocolo v4. Importar este modulo nao abre a porta serial."""
from dataclasses import dataclass
import json
import time
import zlib
import numpy as np

REGISTRO = np.dtype([('t_us', '<u4'), ('adc', '<u2'), ('leitura_us', '<u2')])


def validar_configuracao(fonte, periodo_us, janela_ms, canal=0, spi_hz=1000000):
    """Contrato comum; valida antes de abrir UART ou alterar o firmware."""
    if periodo_us not in (50, 100, 200) or not np.isfinite(janela_ms):
        raise ValueError('Use 5, 10 ou 20 kS/s e janela finita.')
    n = round(janela_ms * 1000 / periodo_us)
    if not 200 <= n <= 6000 or n * periodo_us > 600000:
        raise ValueError('Use 200..6000 amostras e janela ate 600 ms.')
    if fonte not in ('MCP3208', 'INTERNO') or not 0 <= canal <= 7 or spi_hz not in (500000, 1000000):
        raise ValueError('Fonte/canal/clock invalidos.')
    if fonte == 'INTERNO' and canal != 0:
        raise ValueError('INTERNO usa somente GPIO34: indique canal 0.')
    if fonte == 'MCP3208' and periodo_us == 50 and spi_hz == 500000:
        raise ValueError('20 kS/s no MCP3208 exige SPI de 1 MHz; 500 kHz nao deixa margem.')
    return n


class ErroProtocolo(RuntimeError):
    def __init__(self, mensagem, wire=b''):
        super().__init__(mensagem)
        self.wire = wire


@dataclass
class Captura:
    t_us: np.ndarray
    adc: np.ndarray
    leitura_us: np.ndarray
    meta: dict
    wire: bytes = b''


def validar_payload(meta, payload, fim, identificador, configuracao=None):
    """Valida estrutura, CRC, identidade, limites e cronologia; nunca completa dados."""
    if meta.get('protocol') != 4 or meta.get('id') != identificador:
        raise ErroProtocolo('Versao ou identificador de captura incorreto.')
    for nome in ('n', 'period_us', 'channel', 'spi_hz', 'missed', 'bytes', 'max_late_us'):
        if type(meta.get(nome)) is not int or meta[nome] < 0:
            raise ErroProtocolo(f'Metadado invalido: {nome}')
    n = meta['n']
    if not 200 <= n <= 6000 or len(payload) != n * 8 or meta['bytes'] != n * 8:
        raise ErroProtocolo('Quantidade/tamanho do pacote incorreto.')
    if meta['period_us'] not in (50, 100, 200) or n * meta['period_us'] > 600000:
        raise ErroProtocolo('Periodo ou janela fora do contrato.')
    if meta['source'] not in ('MCP3208', 'INTERNO') or meta['channel'] > 7:
        raise ErroProtocolo('Fonte ou canal invalido.')
    if meta['spi_hz'] not in (500000, 1000000):
        raise ErroProtocolo('Clock SPI invalido.')
    try:
        validar_configuracao(meta['source'], meta['period_us'], n * meta['period_us'] / 1000,
                             meta['channel'], meta['spi_hz'])
    except ValueError as exc:
        raise ErroProtocolo(str(exc)) from exc
    if configuracao:
        for nome, valor in configuracao.items():
            if meta.get(nome) != valor:
                raise ErroProtocolo(f'Configuracao retornada diverge: {nome}')
    esperado = f'END {identificador} {zlib.crc32(payload):08X}'
    if fim != esperado:
        raise ErroProtocolo('Marcador END ausente/incorreto ou CRC32 divergente.')
    x = np.frombuffer(payload, dtype=REGISTRO)
    t = x['t_us'].astype(np.int64)
    if np.any(np.diff(t) <= 0) or t[0] > 1000000 or t[-1] > 10000000:
        raise ErroProtocolo('Timestamps invalidos, repetidos ou fora de ordem.')
    if np.any(x['adc'] > 4095) or np.any(x['leitura_us'] == 0):
        raise ErroProtocolo('Leitura ADC ou duracao invalida.')
    return Captura(t, x['adc'].copy(), x['leitura_us'].copy(), dict(meta))


class Dispositivo:
    def __init__(self, porta, transporte=None):
        self.seq = 0
        self.config = None
        self.wire = bytearray()
        if transporte is None:
            import serial
            self.ser = serial.Serial()
            self.ser.port = porta
            self.ser.baudrate = 115200
            self.ser.timeout = 0.02
            self.ser.write_timeout = 3
            self.ser.dtr = False
            self.ser.rts = False
            self.ser.open()
            time.sleep(2)  # algumas placas reiniciam ao abrir a UART.
            self.ser.reset_input_buffer()
        else:
            self.ser = transporte
        try:
            self.hello = json.loads(self.comando('HELLO', 'HELLO ')[6:])
            if self.hello.get('protocol') != 4 or self.hello.get('board') != 'ESP32_CLASSIC':
                raise ErroProtocolo('Grave o medidor.ino v4 no ESP32 classico.')
        except BaseException:
            self.ser.close()
            raise

    def fechar(self):
        self.ser.close()

    def _enviar(self, texto):
        self.ser.write((texto + '\n').encode('ascii'))
        self.ser.flush()

    def _exato(self, n, limite, pump=None):
        b = bytearray()
        while len(b) < n:
            if pump:
                pump()
            if time.monotonic() > limite:
                raise ErroProtocolo('Tempo esgotado: pacote incompleto.', bytes(self.wire))
            trecho = self.ser.read(min(n-len(b), 4096))
            b.extend(trecho)
            self.wire.extend(trecho)
        return bytes(b)

    def _linha(self, limite, pump=None):
        linha = bytearray()
        while True:
            c = self._exato(1, limite, pump)
            if c == b'\n':
                try:
                    return linha.decode('ascii').rstrip('\r')
                except UnicodeError as exc:
                    raise ErroProtocolo('Cabecalho nao ASCII.', bytes(self.wire)) from exc
            linha.extend(c)
            if len(linha) > 2048:
                raise ErroProtocolo('Cabecalho excessivo; protocolo dessincronizado.', bytes(self.wire))

    def comando(self, texto, prefixo, timeout=3):
        self.wire = bytearray()
        self._enviar(texto)
        linha = self._linha(time.monotonic()+timeout)
        if not linha.startswith(prefixo):
            raise ErroProtocolo(f'Resposta inesperada a {texto}: {linha}')
        return linha

    def configurar(self, fonte='MCP3208', periodo_us=100, janela_ms=300, canal=0, spi_hz=1000000):
        n = validar_configuracao(fonte, periodo_us, janela_ms, canal, spi_hz)
        cmd = f'CFG {fonte} {periodo_us} {n} {canal} {spi_hz}'
        if self.comando(cmd, 'OK CFG ') != 'OK '+cmd:
            raise ErroProtocolo('Firmware nao confirmou a configuracao exata.')
        self.config = dict(source=fonte, period_us=periodo_us, n=n, channel=canal, spi_hz=spi_hz)

    def capturar(self, ao_armar=None, pump=None, degrau=None, apos_coleta=None):
        if self.config is None:
            raise RuntimeError('Configure a captura primeiro.')
        self.seq += 1
        self.wire = bytearray()
        cmd = f'CAP {self.seq}' if degrau is None else f'STEP {self.seq} ' + ' '.join(map(str,degrau))
        try:
            self._enviar(cmd)
            linha = self._linha(time.monotonic()+3, pump)
            if linha != f'ARMED {self.seq}':
                raise ErroProtocolo(f'Aquisicao nao armada: {linha}')
            host_arm = time.monotonic()
            extras = ao_armar() if ao_armar else {}
            # 8 bytes/amostra, UART 8N1: 10 bits por byte. Folga para sistema/USB.
            prazo = time.monotonic() + 5 + self.config['n']*80/115200
            linha = self._linha(prazo, pump)
            if not linha.startswith('BEGIN '):
                raise ErroProtocolo('Cabecalho BEGIN ausente.')
            meta = json.loads(linha[6:])
            if type(meta.get('bytes')) is not int or not 1600 <= meta['bytes'] <= 48000:
                raise ErroProtocolo('Tamanho anunciado invalido.')
            # BEGIN só é enviado pelo firmware depois da aquisição em RAM.
            if apos_coleta:
                apos_coleta()
            payload = self._exato(meta['bytes'], prazo, pump)
            if self._exato(1, prazo, pump) != b'\n':
                raise ErroProtocolo('Separador do payload ausente.')
            fim = self._linha(prazo, pump)
            cap = validar_payload(meta,payload,fim,self.seq,self.config)
            cap.meta.update(host_arm_monotonic_s=host_arm, **(extras or {}))
            cap.wire = bytes(self.wire)
            return cap
        except (ValueError, KeyError, ErroProtocolo) as exc:
            raise ErroProtocolo(str(exc),bytes(self.wire)) from exc
        except BaseException as exc:
            exc.wire=bytes(self.wire)  # preserva recebimento parcial inclusive no ESC.
            raise

    def estatica(self):
        return json.loads(self.comando('STAT', 'STAT ')[5:])
