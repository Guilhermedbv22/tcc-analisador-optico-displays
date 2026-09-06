import pygame
import sys
from collections import deque

pygame.init()
pygame.font.init()

# --- CONFIGURAÇÃO PADRÃO ATUALIZADA ---
vsync_ativado = False
hz_desejado = 180 
# --------------------------------------

def configurar_tela(vsync):
    # Reinicia o módulo de display para garantir que o V-Sync aplique 
    # corretamente sem bugar a janela no Windows
    pygame.display.quit()
    pygame.display.init()
    if vsync:
        return pygame.display.set_mode((0, 0), pygame.FULLSCREEN, vsync=1)
    else:
        return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

screen = configurar_tela(vsync_ativado)
screen_width, screen_height = screen.get_size()
clock = pygame.time.Clock()

font = pygame.font.SysFont("Arial", 36)
font_pequena = pygame.font.SysFont("Arial", 24)

square_size = 400
pos_x = (screen_width - square_size) // 2
pos_y = (screen_height - square_size) // 2
square_rect = pygame.Rect(pos_x, pos_y, square_size, square_size)

is_white = False 
fps_history = deque(maxlen=60)

while True:
    for event in pygame.event.get():
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit()
                
            elif event.key == pygame.K_v:
                vsync_ativado = not vsync_ativado
                screen = configurar_tela(vsync_ativado)
                fps_history.clear()
                
            elif event.key == pygame.K_UP:
                if hz_desejado == 0:
                    hz_desejado = 10
                else:
                    hz_desejado += 10
            elif event.key == pygame.K_DOWN:
                hz_desejado -= 10
                if hz_desejado <= 0:
                    hz_desejado = 0 # No Pygame, 0 significa taxa Ilimitada

    screen.fill((0, 0, 0))

    if is_white:
        color = (255, 255, 255)
    else:
        color = (20, 20, 20) 
        
    pygame.draw.rect(screen, color, square_rect)
    is_white = not is_white
    
    current_fps = clock.get_fps()
    fps_history.append(current_fps)
    
    if len(fps_history) > 0:
        avg_fps = sum(fps_history) / len(fps_history)
    else:
        avg_fps = 0
        
    avg_blink = avg_fps / 2
    
    fps_text = font.render(f"Taxa de Atualização (Média): {int(avg_fps)} Hz", True, (0, 255, 0))
    blink_text = font.render(f"Piscadas por segundo (Média): {int(avg_blink)}", True, (0, 255, 0))
    
    status_vsync = "LIGADO" if vsync_ativado else "DESLIGADO"
    vsync_text = font_pequena.render(f"V-Sync: {status_vsync} | Pressione 'V' para alternar", True, (200, 200, 200))
    
    texto_alvo = "Ilimitado" if hz_desejado == 0 else f"{hz_desejado} Hz"
    alvo_text = font_pequena.render(f"Alvo: {texto_alvo} | Use as setas CIMA/BAIXO para mudar", True, (200, 200, 200))

    screen.blit(fps_text, (20, 20))
    screen.blit(blink_text, (20, 70))
    screen.blit(vsync_text, (20, 130))
    screen.blit(alvo_text, (20, 165))
    
    pygame.display.flip()
    
    # Agora o script sempre respeita a taxa alvo definida, 
    # trabalhando em conjunto com o V-Sync para evitar cortes na imagem.
    clock.tick(hz_desejado)