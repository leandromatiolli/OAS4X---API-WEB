import numpy as np
import pickle
import matplotlib.pyplot as plt
import os
import glob
import mkf
from datetime import datetime

def carregar_arquivo_pkl(caminho=None):
    """Carrega o arquivo de dados mais recente ou o especificado"""
    if caminho is None:
        # Encontrar o arquivo .pkl mais recente na pasta atual
        arquivos = glob.glob("vazamento_sensor_*.pkl")
        if not arquivos:
            print("Nenhum arquivo de dados encontrado!")
            return None
        caminho = max(arquivos, key=os.path.getctime)
    
    print(f"Carregando arquivo: {caminho}")
    with open(caminho, 'rb') as f:
        dados = pickle.load(f)
    
    return dados

def get_calibration_params(wv, figure_n=100, plot=True):
    """Realiza o fit da elipse nos dados brutos e retorna os parâmetros da calibração"""
    plt.figure(figure_n)
    plt.cla()
    
    # Se o formato do waveform for 3D, ajusta para 2D
    if len(wv.shape) == 3:
        wv = wv[:,:,0].T
    
    # Realizar o fit da elipse
    ellipse_param = mkf.fit_ellipse(*wv)
    
    if plot:
        # Gerar pontos para plotar a elipse ajustada
        t = np.linspace(0, 2*np.pi, 200)
        fitted_ellipse = mkf.rescale(np.sin(t), np.cos(t), ellipse_param, invert=True)
        
        # Converter pontos para o sistema de coordenadas normalizado
        x, y = mkf.rescale(*wv, ellipse_param)
        
        # Plotar pontos e elipse ajustada
        plt.scatter(*wv, s=1, alpha=0.3)
        plt.plot(*fitted_ellipse, color='red')
        plt.title('Ajuste de Elipse para Demodulação')
        plt.axis('equal')
        
        # Exibir parâmetros da elipse
        y_inc = 1000/2**13
        print(f"CH1 DC = {ellipse_param[0]*y_inc:.0f} mV - min={min(wv[0])} max={max(wv[0])} DRU={100*max(wv[0])/2**13:.0f}%")
        print(f"CH2 DC = {ellipse_param[1]*y_inc:.0f} mV - min={min(wv[1])} max={max(wv[1])} DRU={100*max(wv[1])/2**13:.0f}%")
        print(f"Raio = {ellipse_param[3]*y_inc:.0f} mV")
        print(f"Excentricidade = {ellipse_param[2]:.2f}")
        print(f"Ângulo = {ellipse_param[4]*360/(2*np.pi):.1f} graus")
    
    return ellipse_param

def demodular_sinal(dados, ellipse_param=None, plot_result=True):
    """Demodula o sinal usando os parâmetros da elipse"""
    waveforms = dados['waveforms']
    
    # Se não foram fornecidos parâmetros da elipse, calcula-os
    if ellipse_param is None:
        print("Calculando parâmetros da elipse...")
        ellipse_param = get_calibration_params(waveforms, plot=plot_result)
    
    # Realizar a demodulação
    print("Demodulando sinal...")
    demodulated = mkf.demodulate(waveforms, ellipse_param)
    
    # Criar cópia dos dados originais e adicionar dados demodulados
    dados_demodulados = dados.copy()
    dados_demodulados['demodulated'] = demodulated
    dados_demodulados['ellipse_params'] = ellipse_param
    
    # Plotar o sinal demodulado se solicitado
    if plot_result:
        plt.figure(figsize=(12, 6))
        
        # Determinar o número máximo de pontos a plotar (limitar para visualização)
        n_pontos = len(demodulated)
        max_pontos = 100000  # Limitar para não sobrecarregar o gráfico
        
        if n_pontos > max_pontos:
            passo = n_pontos // max_pontos
            tempo_plot = dados['t'][::passo]
            sinal_plot = demodulated[::passo]
        else:
            tempo_plot = dados['t']
            sinal_plot = demodulated
        
        plt.plot(tempo_plot, sinal_plot)
        plt.title('Sinal Demodulado')
        plt.xlabel('Tempo (s)')
        plt.ylabel('Fase (rad)')
        plt.grid(True)
    
    return dados_demodulados

def salvar_dados_demodulados(dados, filename=None):
    """Salva os dados demodulados em um arquivo pickle"""
    if filename is None:
        # Criar nome de arquivo com timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"vazamento_demodulado_{timestamp}.pkl"
    
    with open(filename, 'wb') as f:
        pickle.dump(dados, f)
    
    print(f"Dados demodulados salvos em {filename}")
    return filename

def main():
    print("Processador de Demodulação de Sinais OAS")
    print("---------------------------------------")
    
    # Carregar dados brutos
    dados_brutos = carregar_arquivo_pkl()
    if dados_brutos is None:
        return
    
    # Mostrar informações sobre os dados carregados
    print("\nInformações sobre os dados brutos:")
    print(f"Timestamp: {dados_brutos.get('timestamp', 'Desconhecido')}")
    print(f"Canais: {dados_brutos['channels']}")
    print(f"Forma de onda: {dados_brutos['waveforms'].shape}")
    print(f"Taxa de amostragem: {dados_brutos['sample_frequency_effective']/1e6:.2f} MHz")
    print(f"Duração: {dados_brutos['acquisition_time']} segundos")
    
    # Realizar o ajuste da elipse e demodular o sinal
    print("\nRealizando ajuste de elipse e demodulação...")
    dados_demodulados = demodular_sinal(dados_brutos)
    
    # Salvar os dados demodulados
    print("\nSalvando dados demodulados...")
    arquivo_salvo = salvar_dados_demodulados(dados_demodulados)
    
    print(f"\nProcessamento concluído! Os dados demodulados foram salvos em {arquivo_salvo}")
    
    # Manter os gráficos abertos
    plt.show()

if __name__ == "__main__":
    main() 