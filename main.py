import requests
import json
import time
from flask import Flask, jsonify, send_from_directory
from threading import Thread, Lock
import logging
import os
from datetime import datetime

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Inicialização
app = Flask(__name__)

# Estado global
estado_lock = Lock()
analise_sinal = False
entrada = 0
max_gale = 2
resultado = []
check_resultado = []
cor_sinal = ''
cores = []

# Placar
placar = {
    'win_primeira': 0,
    'win_gale1': 0,
    'win_gale2': 0,
    'win_branco': 0,
    'loss': 0,
    'consecutivas': 0,
    'max_consecutivas': 0,
    'sinais_hoje': 0
}

# Estado para o site
estado_site = {
    'sinal_ativo': False,
    'ultimo_sinal': None,
    'online': True,
    'historico_sinais': [],
    'ultima_atualizacao': None,
    'placar': placar.copy()
}

# Servir arquivos estáticos
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# API endpoints para o site
@app.route('/api/status')
def get_status():
    with estado_lock:
        # Calcular sinais de hoje
        hoje = datetime.now().strftime('%d/%m/%Y')
        sinais_hoje = len([s for s in estado_site['historico_sinais'] 
                          if s.get('data_completa', '').startswith(hoje.split('/')[0])])
        estado_site['placar']['sinais_hoje'] = sinais_hoje
        
        return jsonify({
            'online': estado_site['online'],
            'sinal_ativo': estado_site['sinal_ativo'],
            'ultimo_sinal': estado_site['ultimo_sinal'],
            'ultima_atualizacao': estado_site['ultima_atualizacao'],
            'placar': estado_site['placar'],
            'historico_sinais': estado_site['historico_sinais'],
            'timestamp': time.time()
        })

@app.route('/api/historico_sinais')
def get_historico_sinais():
    with estado_lock:
        return jsonify(estado_site['historico_sinais'][-10:])

@app.route('/api/ultimos_resultados')
def get_ultimos_resultados():
    try:
        # SUA API ORIGINAL DA BLAZE
        req = requests.get('https://blaze.bet.br/api/singleplayer-originals/originals/roulette_games/recent/1', timeout=10)
        a = json.loads(req.content)
        resultados = []
        
        for jogo in a:
            numero = jogo['roll']
            if numero >= 1 and numero <= 7:
                cor = 'V'
                emoji = '🔴'
            elif numero >= 8 and numero <= 14:
                cor = 'P'
                emoji = '⚫'
            else:
                cor = 'B'
                emoji = '⚪'
            
            resultados.append({
                'numero': numero,
                'cor': cor,
                'emoji': emoji,
                'hora': jogo.get('created_at', '')[:19] if 'created_at' in jogo else datetime.now().strftime('%H:%M:%S')
            })
        
        return jsonify(resultados)
    except Exception as e:
        logger.error(f"Erro ao buscar resultados: {e}")
        return jsonify([])

# SUAS FUNÇÕES ORIGINAIS - MODIFICADAS PARA INTEGRAR COM O SITE
def reset():
    global analise_sinal, entrada
    entrada = 0
    analise_sinal = False
    
    with estado_lock:
        estado_site['sinal_ativo'] = False
    logger.info("Sistema resetado")

def martingale():
    global entrada
    entrada += 1
    
    if entrada <= max_gale:
        logger.info(f"Martingale {entrada} ativado")
        
        # ATUALIZAR MARTINGALE NO SITE
        with estado_lock:
            if estado_site['ultimo_sinal']:
                estado_site['ultimo_sinal']['martingale'] = entrada
                estado_site['ultima_atualizacao'] = datetime.now().strftime('%H:%M:%S')
        
        logger.info(f"Martingale {entrada} registrado")
    else:
        loss()
        reset()
    return

def api():
    global resultado
    try:
        # SUA API ORIGINAL
        req = requests.get('https://blaze.bet.br/api/singleplayer-originals/originals/roulette_games/recent/1', timeout=10)
        a = json.loads(req.content)
        jogo = [x['roll'] for x in a]
        resultado = jogo
        return jogo
    except Exception as e:
        logger.error(f"Erro na API: {e}")
        return []

def calcular_assertividade():
    total = placar['win_primeira'] + placar['win_gale1'] + placar['win_gale2'] + placar['win_branco'] + placar['loss']
    if total == 0:
        return 0.00
    return ((placar['win_primeira'] + placar['win_gale1'] + placar['win_gale2'] + placar['win_branco']) / total) * 100

def atualizar_placar_site():
    """Atualizar placar no estado do site"""
    with estado_lock:
        estado_site['placar'] = placar.copy()

def win(tipo="primeira"):
    if tipo == "branco":
        placar['win_branco'] += 1
        logger.info("⚪️ Win no Branco")
    elif tipo == "gale1":
        placar['win_gale1'] += 1
        logger.info("✅ Win Gale 1")
    elif tipo == "gale2":
        placar['win_gale2'] += 1
        logger.info("✅ Win Gale 2")
    else:
        placar['win_primeira'] += 1
        logger.info("✅ Win Primeira Entrada")
    
    placar['consecutivas'] += 1
    
    # Atualizar máximo de consecutivas
    if placar['consecutivas'] > placar['max_consecutivas']:
        placar['max_consecutivas'] = placar['consecutivas']
    
    atualizar_placar_site()
    
    # ATUALIZAR RESULTADO NO SITE
    with estado_lock:
        estado_site['sinal_ativo'] = False
        if estado_site['ultimo_sinal']:
            estado_site['ultimo_sinal']['resultado'] = f'WIN_{tipo.upper()}'
            estado_site['ultimo_sinal']['finalizado'] = True
            estado_site['ultima_atualizacao'] = datetime.now().strftime('%H:%M:%S')
    
    logger.info(f"WIN - Sinal finalizado - Tipo: {tipo}")
    return 

def loss():
    placar['loss'] += 1
    placar['consecutivas'] = 0
    
    logger.info("❌ Loss")
    atualizar_placar_site()
    
    # ATUALIZAR RESULTADO NO SITE
    with estado_lock:
        estado_site['sinal_ativo'] = False
        if estado_site['ultimo_sinal']:
            estado_site['ultimo_sinal']['resultado'] = 'LOSS'
            estado_site['ultimo_sinal']['finalizado'] = True
            estado_site['ultima_atualizacao'] = datetime.now().strftime('%H:%M:%S')
    
    logger.info("LOSS - Sinal finalizado")
    return

def correcao(results, color):
    # SE BRANCO SAIU - WIN IMEDIATO (PROTEÇÃO)
    if results[0:1] == ['B']:
        win("branco")
        reset()
        return
    
    if results[0:1] == ['P'] and color == '⚫️':
        if entrada == 0:
            win("primeira")
        elif entrada == 1:
            win("gale1")
        elif entrada == 2:
            win("gale2")
        reset()
        return
    
    elif results[0:1] == ['V'] and color == '🛑':
        if entrada == 0:
            win("primeira")
        elif entrada == 1:
            win("gale1")
        elif entrada == 2:
            win("gale2")
        reset()
        return
    
    elif results[0:1] == ['P'] and color == '🛑':
        martingale()
        return
    
    elif results[0:1] == ['V'] and color == '⚫️':
        martingale()
        return

def enviar_sinal(cor, padrao):
    """Função modificada para enviar apenas para o site"""
    global analise_sinal, cor_sinal
    
    # Atualizar estado para o site
    sinal_data = {
        'id': len(estado_site['historico_sinais']) + 1,
        'padrao': padrao,
        'cor': cor,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'data_completa': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        'martingale': 0,  # Iniciar com 0
        'resultado': None,  # Iniciar sem resultado
        'finalizado': False,
        'status': 'ATIVO'
    }
    
    with estado_lock:
        estado_site.update({
            'sinal_ativo': True,
            'ultimo_sinal': sinal_data,
            'ultima_atualizacao': datetime.now().strftime('%H:%M:%S')
        })
        estado_site['historico_sinais'].append(sinal_data)
        placar['sinais_hoje'] = len([s for s in estado_site['historico_sinais'] 
                                   if s.get('data_completa', '').startswith(datetime.now().strftime('%d/%m/%Y').split('/')[0])])
    
    analise_sinal = True
    cor_sinal = cor
    logger.info(f"🚨 SINAL ENCONTRADO - Padrão: {padrao}, Cor: {cor}")
    return

def estrategy(resultado):
    global analise_sinal, cor_sinal, cores
    
    cores = []
    for x in resultado:
        if x >= 1 and x <= 7:
            color = 'V'
            cores.append(color)
        elif x >= 8 and x <= 14:
            color = 'P'
            cores.append(color)
        else:
            color = 'B'
            cores.append(color)
    
    logger.info(f"Últimas cores: {cores}")
    
    if analise_sinal == True:
        correcao(cores, cor_sinal)
    else:
        # ESTRATÉGIAS ORIGINAIS
        if len(cores) >= 6 and cores[0:6] == ['P','P','P','P','P','P']:
            cor_sinal = '🛑'
            padrao = '👻Ghost👻'
            enviar_sinal(cor_sinal, padrao)
            print('sinal enviado - Ghost')
        
        elif len(cores) >= 6 and cores[0:6] == ['V','V','V','V','V','V']:
            cor_sinal = '⚫️'
            padrao = '👑King👑'
            enviar_sinal(cor_sinal, padrao)
            print('sinal enviado - King')  
        
        elif len(cores) >= 4 and cores[0:4] == ['V','V','V','P']:
            cor_sinal = '⚫️'
            padrao = '🥷🏽Samurai🥷🏽'
            enviar_sinal(cor_sinal, padrao)
            print('sinal enviado - Samurai')
        
        # NOVAS ESTRATÉGIAS VERMELHO (3)
        elif len(cores) >= 5 and cores[0:5] == ['P','V','P','V','P']:
            cor_sinal = '🛑'
            padrao = '🔥Red Dragon🔥'
            enviar_sinal(cor_sinal, padrao)
            print('sinal enviado - Red Dragon')
        
        elif len(cores) >= 4 and cores[0:4] == ['V','P','V','P']:
            cor_sinal = '🛑'
            padrao = '🎯Red Sniper🎯'
            enviar_sinal(cor_sinal, padrao)
            print('sinal enviado - Red Sniper')
        
        elif len(cores) >= 3 and cores[0:3] == ['P','P','V']:
            cor_sinal = '🛑'
            padrao = '⚡Red Thunder⚡'
            enviar_sinal(cor_sinal, padrao)
            print('sinal enviado - Red Thunder')
        
        # NOVA ESTRATÉGIA PRETO (1)
        elif len(cores) >= 4 and cores[0:4] == ['V','V','P','V']:
            cor_sinal = '⚫️'
            padrao = '🕶️Black Panther🕶️'
            enviar_sinal(cor_sinal, padrao)
            print('sinal enviado - Black Panther')
        
        # ESTRATÉGIAS BRANCO (2)
        elif len(cores) >= 1 and cores[0:1] == ['B']:
            cor_sinal = '⚪️'
            padrao = '❄️Triple White❄️'
            enviar_sinal(cor_sinal, padrao)
            print('sinal enviado - Triple White')
        
        elif len(cores) >= 4 and cores[0:4] == ['P','V','V','V']:
            cor_sinal = '⚫️'
            padrao = '🌪️Double White🌪️'
            enviar_sinal(cor_sinal, padrao)
            print('sinal enviado - Double White')

def monitorar_blaze():
    """Função principal de monitoramento"""
    logger.info("Iniciando monitoramento da Blaze...")
    
    while True:
        try:
            api()
            
            if resultado != check_resultado:
                check_resultado[:] = resultado
                estrategy(resultado)
            
            # Atualizar timestamp do site
            with estado_lock:
                estado_site['ultima_atualizacao'] = datetime.now().strftime('%H:%M:%S')
                estado_site['online'] = True
            
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"Erro no monitoramento: {e}")
            with estado_lock:
                estado_site['online'] = False
            time.sleep(10)

def iniciar_tudo():
    """Iniciar servidor e monitoramento"""
    print("=" * 60)
    print("🤖 IA HACKER - SISTEMA INICIADO")
    print("=" * 60)
    print("✅ API Blaze conectada")
    print("✅ 9 Estratégias ativas")
    print("✅ Monitoramento 24/7")
    print("✅ Site online")
    print("=" * 60)
    
    # Iniciar monitoramento em thread separada
    monitor_thread = Thread(target=monitorar_blaze)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    # Configurar porta para Render
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Servidor iniciando na porta {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == "__main__":
    iniciar_tudo()
