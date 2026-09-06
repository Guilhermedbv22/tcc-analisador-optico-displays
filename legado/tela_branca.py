import tkinter as tk

def fechar_tela(evento):
    # Função para fechar a janela quando a tecla for pressionada
    janela.destroy()

# Cria a janela principal
janela = tk.Tk()

# Define a cor de fundo como branco
janela.configure(bg='black')

# Coloca a janela em modo tela cheia (fullscreen)
janela.attributes('-fullscreen', True)

# Oculta o cursor do mouse (opcional, remova a linha abaixo se quiser ver o mouse)
janela.config(cursor="none")

# Vincula a tecla 'Esc' à função de fechar a tela
janela.bind('<Escape>', fechar_tela)

# Mantém a janela aberta e rodando
janela.mainloop()